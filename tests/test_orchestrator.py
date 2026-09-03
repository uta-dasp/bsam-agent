from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import ApiError, LocalAgentApi
from bsam_agent.orchestrator import ChatOrchestrator, ConversationState, _summarize_result
from bsam_agent.provider import ProviderConfig, ProviderRequest, ProviderResponse, Usage


def config() -> ProviderConfig:
    return ProviderConfig(
        "cpu-local", "test-model", "http://127.0.0.1:18080", None,
        2.0, 24000, 512, "local-private",
    )


def decision(
    outcome: str, tool: str | None = None, arguments: dict[str, object] | None = None,
    error_code: str | None = None, response: str | None = None,
) -> ProviderResponse:
    return ProviderResponse(
        content=json.dumps({
            "outcome": outcome, "tool": tool, "arguments": arguments or {},
            "error_code": error_code, "response": response,
        }),
        usage=Usage(10, 5),
    )


class FakeProvider:
    def __init__(self, *responses: ProviderResponse) -> None:
        self.responses = list(responses)
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest, cancel=None) -> ProviderResponse:
        self.requests.append(request)
        return self.responses.pop(0)


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def dispatch(self, tool: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((tool, arguments))
        if tool == "inspect_model":
            return {
                "source_set_sha256": "a" * 64,
                "semantic_model": {},
                "summary": {"errors": 0, "warnings": 1},
            }
        if tool == "apply_change":
            if arguments["confirm"] is not True:
                raise ApiError("confirmation_required", "confirm=true required")
            return {
                "plan_id": "plan-1", "destination": arguments["destination"],
                "output_sha256": "b" * 64,
                "validation": {"summary": {"errors": 0, "warnings": 0}},
                "audit": {},
            }
        raise AssertionError(tool)


class OrchestratorTests(unittest.TestCase):
    def test_dispatches_read_only_tool_and_records_digest_only_audit(self) -> None:
        provider = FakeProvider(decision(
            "dispatch", "inspect_model", {"source": "model.in"}, response="invented",
        ))
        api = FakeApi()
        with tempfile.TemporaryDirectory() as directory:
            agent = ChatOrchestrator(
                provider, config(), api, audit_directory=Path(directory)  # type: ignore[arg-type]
            )
            result = agent.turn("Inspect model.in and summarize it")
            records = agent.audit_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
        self.assertEqual("explain", result.phase)
        self.assertEqual(
            "Inspection completed: 0 cluster(s), 0 node(s), 0 element(s); "
            "0 error(s), 1 warning(s).",
            result.message,
        )
        self.assertEqual([("inspect_model", {"source": "model.in"})], api.calls)
        self.assertNotIn("Inspect model.in", records)
        self.assertIn("user_digest", records)
        self.assertNotIn("invented", result.message)

    def test_guarded_action_requires_separate_explicit_confirmation(self) -> None:
        provider = FakeProvider(decision(
            "dispatch", "apply_change",
            {"plan_path": "plan.json", "destination": "changed.in", "confirm": True},
        ))
        api = FakeApi()
        agent = ChatOrchestrator(provider, config(), api)  # type: ignore[arg-type]
        proposed = agent.turn("Apply plan.json to changed.in")
        self.assertTrue(proposed.requires_confirmation)
        self.assertEqual([], api.calls)

        applied = agent.turn("/confirm")
        self.assertEqual("verify", applied.phase)
        self.assertEqual(1, len(provider.requests))
        self.assertIs(api.calls[0][1]["confirm"], True)

    def test_drops_model_invented_optional_arguments(self) -> None:
        provider = FakeProvider(decision(
            "dispatch", "inspect_model", {"source": "model.in"},
        ))
        agent = ChatOrchestrator(provider, config(), FakeApi())  # type: ignore[arg-type]
        result = agent.turn("Analyze model.in")
        self.assertEqual("explain", result.phase)

        provider = FakeProvider(decision(
            "dispatch", "apply_change", {
                "plan_path": "plan.json", "destination": "changed.in", "confirm": False,
                "audit_path": "",
            },
        ))
        api = FakeApi()
        agent = ChatOrchestrator(provider, config(), api)  # type: ignore[arg-type]
        agent.turn("Apply plan.json to changed.in")
        agent.turn("/confirm")
        self.assertNotIn("audit_path", api.calls[0][1])

    def test_cancel_prevents_pending_action(self) -> None:
        provider = FakeProvider(decision(
            "dispatch", "apply_change",
            {"plan_path": "plan.json", "destination": "changed.in", "confirm": False},
        ))
        api = FakeApi()
        agent = ChatOrchestrator(provider, config(), api)  # type: ignore[arg-type]
        agent.turn("Apply plan.json to changed.in")
        cancelled = agent.turn("/cancel")
        self.assertEqual("understand", cancelled.phase)
        self.assertEqual([], api.calls)

    def test_repairs_one_malformed_model_response(self) -> None:
        provider = FakeProvider(
            ProviderResponse(content="not-json"),
            decision("dispatch", "inspect_model", {"source": "model.in"}),
        )
        api = FakeApi()
        agent = ChatOrchestrator(provider, config(), api)  # type: ignore[arg-type]
        result = agent.turn("Analyze model.in")
        self.assertEqual("explain", result.phase)
        self.assertEqual(2, len(provider.requests))
        self.assertLess(len(provider.requests[1].messages), 6)

    def test_repairs_invented_policy_error_code(self) -> None:
        provider = FakeProvider(
            decision("refuse", error_code="unsupported_operation"),
            decision("dispatch", "inspect_model", {"source": "model.in"}),
        )
        agent = ChatOrchestrator(provider, config(), FakeApi())  # type: ignore[arg-type]
        result = agent.turn("Analyze model.in")
        self.assertEqual("explain", result.phase)
        self.assertEqual(2, len(provider.requests))

    def test_audit_can_be_disabled(self) -> None:
        provider = FakeProvider(decision("answer", response="No action needed."))
        agent = ChatOrchestrator(provider, config(), FakeApi())  # type: ignore[arg-type]
        result = agent.turn("Hello")
        self.assertEqual("No action needed.", result.message)
        self.assertIsNone(agent.audit_path)

    def test_provider_failure_is_normalized(self) -> None:
        class FailedProvider:
            def complete(self, request, cancel=None):
                raise RuntimeError("local server unavailable")

        agent = ChatOrchestrator(FailedProvider(), config(), FakeApi())  # type: ignore[arg-type]
        result = agent.turn("Analyze model.in")
        self.assertEqual("provider_error", result.error_code)
        self.assertIn("unavailable", result.message)

    def test_explicit_session_save_and_resume_preserves_pending_confirmation(self) -> None:
        provider = FakeProvider(decision(
            "dispatch", "apply_change",
            {"plan_path": "plan.json", "destination": "changed.in", "confirm": False},
        ))
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "session.json"
            first = ChatOrchestrator(provider, config(), FakeApi())  # type: ignore[arg-type]
            first.turn("Apply plan.json to changed.in")
            first.save_state(session)
            restored = ChatOrchestrator(
                FakeProvider(), config(), FakeApi(),
                state=ChatOrchestrator.load_state(session),  # type: ignore[arg-type]
            )
        self.assertEqual(first.state.conversation_id, restored.state.conversation_id)
        self.assertEqual("apply_change", restored.state.pending_action.tool)  # type: ignore[union-attr]

    def test_existing_session_schema_migrates_without_a_last_plan(self) -> None:
        value = ConversationState().as_dict()
        value["schema_version"] = "0.1.0"
        value.pop("last_plan")
        restored = ConversationState.from_dict(value)
        self.assertIsNone(restored.last_plan)

    def test_end_to_end_preview_confirm_and_apply_with_fake_provider(self) -> None:
        deck = (
            b"INPUT\n3\nEND INPUT\n"
            b"BOUNDARY\n*type\nmechanical\n*convergence\nabsolute=1\nEND BOUNDARY\n"
            b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
            b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
        )
        provider = FakeProvider(
            decision("dispatch", "preview_parameter_change", {
                "source": "model.in", "block": "BOUNDARY", "construct": "CONVERGENCE",
                "parameter": "absolute", "value": "2", "plan_path": "plans/change.json",
                "occurrence": 0,
            }),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck)
            (root / "plans").mkdir()
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            preview = agent.turn("Preview changing absolute to 2 in model.in")
            pending = agent.turn("Apply that change to changed.in")
            applied = agent.turn("/confirm")
            output = (root / "changed.in").read_bytes()
        self.assertEqual("propose", preview.phase)
        self.assertIn("-absolute=1", preview.tool_result["source_diff"])  # type: ignore[index]
        self.assertTrue(pending.requires_confirmation)
        self.assertEqual("verify", applied.phase)
        self.assertIn(b"absolute=2", output)

    def test_natural_registered_parameter_request_uses_defaults_and_confirmation(self) -> None:
        deck = (
            b"INPUT\n3\nEND INPUT\n"
            b"BOUNDARY\n*type\nmechanical\n*convergence\nd_reduction=0.25\nEND BOUNDARY\n"
            b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
            b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
        )
        provider = FakeProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            preview = agent.turn(
                "Change d_reduction in model.in to 0.5 and create a new file. "
                "Do not overwrite the original."
            )
            applied = agent.turn("/confirm")
            output = (root / "model.changed.in").read_bytes()
        self.assertEqual([], provider.requests)
        self.assertEqual("confirm", preview.phase)
        self.assertTrue(preview.requires_confirmation)
        self.assertIn("model.changed.in", preview.message)
        self.assertEqual("verify", applied.phase)
        self.assertIn(b"d_reduction=0.5", output)

    def test_model_routes_high_level_parameter_intent_through_registry(self) -> None:
        deck = (
            b"INPUT\n3\nEND INPUT\n"
            b"BOUNDARY\n*type\nmechanical\n*convergence\nd_reduction=0.25\nEND BOUNDARY\n"
            b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
            b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
        )
        provider = FakeProvider(decision(
            "dispatch", "preview_parameter_change",
            {"source": "model.in", "parameter": "d_reduction", "value": "0.5"},
        ))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Please make the time-increment reduction ratio 0.5 in model.in")
        self.assertEqual("propose", result.phase)
        called_contract = provider.requests[0].messages[0].content
        self.assertIn("d_reduction", called_contract)
        self.assertIn("BOUNDARY/CONVERGENCE", called_contract)
        self.assertIn("d_reduction=0.5", result.tool_result["source_diff"])  # type: ignore[index]

    def test_ambiguous_parameter_request_asks_for_context(self) -> None:
        routed = decision(
            "dispatch", "preview_parameter_change",
            {"source": "model.in", "parameter": "type", "value": "static"},
        )
        provider = FakeProvider(routed, routed)
        agent = ChatOrchestrator(provider, config(), FakeApi())  # type: ignore[arg-type]
        result = agent.turn("Adjust the type to static in model.in")
        self.assertEqual("invalid_arguments", result.error_code)
        self.assertIn("ambiguous", result.message)
        self.assertIn("specify one of these contexts", result.message)

    def test_requested_output_path_is_preserved_for_follow_up(self) -> None:
        deck = (
            b"INPUT\n3\nEND INPUT\n"
            b"BOUNDARY\n*type\nmechanical\n*convergence\nd_reduction=0.25\nEND BOUNDARY\n"
            b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
            b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck)
            agent = ChatOrchestrator(FakeProvider(), config(), LocalAgentApi(root))
            preview = agent.turn(
                "Change d_reduction in model.in to 0.5 and create new-output.in."
            )
            agent.turn("/confirm")
            output = (root / "new-output.in").read_bytes()
        self.assertEqual("confirm", preview.phase)
        self.assertIn(b"d_reduction=0.5", output)

    def test_natural_inspection_does_not_depend_on_model_routing(self) -> None:
        deck = (
            b"INPUT\n3\nEND INPUT\nBOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
            b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
        )
        provider = FakeProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn(
                "Inspect model.in and summarize its laminate, boundary conditions, "
                "mesh references, errors, and warnings."
            )
        self.assertEqual([], provider.requests)
        self.assertEqual("inspect_model", result.tool)
        self.assertIn("Inspection completed", result.message)
        self.assertIn("References:", result.message)

    def test_inspection_summary_includes_engineering_structure(self) -> None:
        result = {
            "summary": {"errors": 0, "warnings": 1},
            "semantic_model": {
                "entities": [
                    {"id": "c1", "kind": "cluster", "name": "ply1"},
                    {"id": "n1", "kind": "node", "name": "1", "attributes": {"cluster": "ply1"}},
                    {"id": "e1", "kind": "element", "name": "1", "attributes": {"cluster": "ply1"}},
                    {"id": "s1", "kind": "section", "name": "all", "attributes": {"cluster": "ply1", "layers": "1"}},
                    {"id": "bc1", "kind": "boundary-condition", "name": "fixed"},
                    {"id": "m1", "kind": "constitutive", "name": "1", "attributes": {"type": 3}},
                ],
                "references": [{
                    "source_entity_id": "bc1", "target_key": "cluster:ply1/node-set:xmin",
                }],
                "summary": {
                    "entities_by_kind": {"cluster": 1, "node": 1, "element": 1},
                    "references": 1, "resolved_references": 1,
                    "unresolved_references": 0, "ambiguous_references": 0,
                    "type_mismatches": 0,
                },
            },
            "source_set": {"files": [{}]},
            "diagnostics": [{"code": "BSAM-W1", "line": 4, "message": "example warning"}],
        }
        message = _summarize_result("inspect_model", result)
        self.assertIn("Ply-like clusters: ply1 (1 nodes, 1 elements)", message)
        self.assertIn("Boundary conditions: fixed -> ply1.xmin", message)
        self.assertIn("Constitutive definitions: 1 (type 3)", message)
        self.assertIn("References: 1/1 resolved", message)
        self.assertIn("BSAM-W1 line 4", message)


if __name__ == "__main__":
    unittest.main()
