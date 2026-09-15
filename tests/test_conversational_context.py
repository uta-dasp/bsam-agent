from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import LocalAgentApi
from bsam_agent.orchestrator import (
    ChatOrchestrator,
    ConversationState,
    _routing_request_schema,
    _recovery_classification,
)
from bsam_agent.provider import ProviderConfig


DECK = (
    b"INPUT\n3\nEND INPUT\n"
    b"BOUNDARY\n*type\nmechanical\n"
    b"*boundary condition\n"
    b"type=disp, comp=x, name=bc1-1, value=0, nset=ply1.edge\n"
    b"type=disp, comp=x, name=bc5-1, value=0, nset=ply2.edge\n"
    b"*convergence\nd_reduction=0.25\nEND BOUNDARY\n"
    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
    b"MATERIALS\n0\nEND MATERIALS\n"
    b"CLUSTERS\n*type\nsolid\n*NAME\nply1\n*NODE\n1,0,0,0\n"
    b"*NSET,NSET=edge\n1\n*NAME\nply2\n*NODE\n2,1,0,0\n"
    b"*NSET,NSET=edge\n2\n*STOP\nEND CLUSTERS\n"
)
FIXTURES = Path(__file__).parent / "fixtures"


def config() -> ProviderConfig:
    return ProviderConfig(
        "cpu-local", "test", "http://127.0.0.1:1", None,
        1.0, 24000, 512, "local-private",
    )


class NoModelProvider:
    def complete(self, request):  # pragma: no cover - deterministic routes must avoid it
        raise AssertionError("unexpected provider call")


class ConversationalContextTests(unittest.TestCase):
    def agent(self, root: Path) -> ChatOrchestrator:
        return ChatOrchestrator(NoModelProvider(), config(), LocalAgentApi(root))

    def test_absolute_inspection_and_active_model_followups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "RUNNER~1" / "Temp"
            root.mkdir(parents=True)
            source = root / "model.in"
            source.write_bytes(DECK)
            agent = self.agent(root)

            inspected = agent.turn(f"Inspect {source}")
            editable = agent.turn("Which parameters can I safely change?")
            current = agent.turn("What is the current value of d_reduction?")
            change = agent.turn("Change that value to 0.5.")
            restored = ConversationState.from_dict(agent.state.as_dict())

        self.assertEqual("inspect_model", inspected.tool)
        self.assertEqual("model.in", agent.state.model_context.active_source)
        self.assertIn("d_reduction", editable.message)
        self.assertIn("0.25", current.message)
        self.assertTrue(change.requires_confirmation)
        self.assertEqual("model.in", restored.model_context.active_source)
        self.assertIsNotNone(restored.model_context.active_source_digest)

    def test_boundary_query_chains_references_and_resolves_followup_entity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = self.agent(root)
            agent.turn("Inspect model.in")
            boundary = agent.turn("Which BCs act on ply2 and what sets do they reference?")
            followup_filter = agent.turn("Which ones are on ply2?")
            direct = agent.turn("What does bc5-1 reference?")
            followup = agent.turn("What does that BC reference?")

        self.assertEqual(["bc5-1"], [item["name"] for item in boundary.tool_result["matches"]])
        self.assertEqual(1, len(boundary.tool_result["read_only_chain"]))
        self.assertEqual(["bc5-1"], [item["name"] for item in followup_filter.tool_result["matches"]])
        self.assertIn("ply2.edge", direct.message)
        self.assertIn("ply2.edge", followup.message)
        self.assertEqual("bc5-1", agent.state.model_context.selected_entity["name"])

    def test_complete_crack_coreference_dialogue_uses_canonical_entity_intents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "notch_v1.in"
            source.write_bytes((FIXTURES / "conversational_cracks.in").read_bytes())
            agent = self.agent(root)

            inspected = agent.turn("Inspect notch_v1.in.")
            counted = agent.turn("How many cracks?")
            explained = agent.turn("Explain the cracks.")
            linked = agent.turn("Which one references ply2?")
            detailed = agent.turn("Show me that crack in more detail.")

        self.assertEqual("inspect_model", inspected.tool)
        self.assertEqual("query_model", counted.tool)
        self.assertEqual(2, counted.tool_result["summary"]["matches"])
        self.assertEqual("query_model", explained.tool)
        self.assertEqual(["1", "2"], [item["name"] for item in explained.tool_result["matches"]])
        self.assertEqual("find_references", linked.tool)
        self.assertEqual(1, linked.tool_result["summary"]["matches"])
        selected = agent.state.model_context.selected_entity
        self.assertEqual({"kind": "crack", "name": "2"}, {
            "kind": selected["kind"], "name": selected["name"],
        })
        self.assertEqual("inspect_entity", detailed.tool)
        self.assertEqual("2", detailed.tool_result["matches"][0]["name"])
        self.assertIn("type=301", detailed.message)

    def test_change_followup_uses_active_source_and_recovers_output_and_audit_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            (root / "model.changed.in").write_bytes(b"occupied")
            (root / "model.changed.in.audit.json").write_text("{}", encoding="utf-8")
            agent = self.agent(root)
            agent.turn("Inspect model.in")
            preview = agent.turn("Change d_reduction to 0.5 and validate it.")
            applied = agent.turn("/confirm")
            validated = agent.turn("Validate the changed model.")

            output = (root / "model.changed-2.in").read_bytes()
            audit_exists = (root / "model.changed-2.in.audit.json").is_file()

        self.assertTrue(preview.requires_confirmation)
        self.assertIn(b"d_reduction=0.5", output)
        self.assertTrue(audit_exists)
        self.assertEqual("model.changed-2.in", agent.state.model_context.last_created_output)
        self.assertEqual(0, applied.tool_result["post_apply_validation"]["summary"]["errors"])
        self.assertEqual("validate_model", validated.tool)

    def test_audit_only_collision_selects_matching_numbered_output_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            (root / "model.changed.in.audit.json").write_text("occupied", encoding="utf-8")
            agent = self.agent(root)
            preview = agent.turn("Change d_reduction in model.in to 0.5.")
            applied = agent.turn("/confirm")
            output_exists = (root / "model.changed-2.in").is_file()
            audit_exists = (root / "model.changed-2.in.audit.json").is_file()

        self.assertIn("model.changed-2.in", preview.message)
        self.assertEqual("model.changed-2.in", agent.state.model_context.last_created_output)
        self.assertEqual(0, applied.tool_result["validation"]["summary"]["errors"])
        self.assertTrue(output_exists and audit_exists)

    def test_capability_summary_and_recovery_classes_are_engineering_facing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            agent = self.agent(Path(directory))
            result = agent.turn("What can you do?")

        self.assertEqual("get_capabilities", result.tool)
        self.assertIn("verified operations", result.message)
        self.assertIn("inspect-only capabilities", result.message)
        self.assertNotIn("Loaded 28", result.message)
        self.assertEqual("safe_recovery", _recovery_classification("conflict", "destination already exists"))
        self.assertEqual("needs_user_decision", _recovery_classification("invalid_arguments", "two materials are ambiguous"))
        self.assertEqual("hard_failure", _recovery_classification("path_not_allowed", "workspace escape"))

    def test_hosted_router_refuses_pasted_bsam_payload_before_provider(self) -> None:
        hosted = ProviderConfig(
            "openai", "gpt-5.6-terra", "https://api.openai.com",
            "env:OPENAI_API_KEY", 1.0, 24000, 128, "sanitized", False, "high",
        )
        with tempfile.TemporaryDirectory() as directory:
            agent = ChatOrchestrator(
                NoModelProvider(), hosted, LocalAgentApi(Path(directory)),
            )
            result = agent.turn(
                "Explain this pasted deck:\nINPUT\n3\nEND INPUT\nBOUNDARY\n*type\nmechanical\nEND BOUNDARY"
            )
        self.assertEqual("data_policy_violation", result.error_code)
        self.assertIn("Hosted routing refused", result.message)

    def test_model_facing_generic_and_query_schemas_are_capability_specific(self) -> None:
        query = _routing_request_schema("query_model", include_registry_catalog=False)
        references = _routing_request_schema("find_references", include_registry_catalog=False)
        create = _routing_request_schema("preview_create_entity", include_registry_catalog=False)
        self.assertIn("list_boundary_conditions", query["properties"]["query"]["enum"])
        self.assertEqual(
            ["inbound", "outbound"], references["properties"]["direction"]["enum"],
        )
        self.assertIn("command.node", create["properties"]["capability"]["enum"])
        metadata = create["properties"]["attributes"]["description"]
        self.assertIn('"required_fields"', metadata)
        self.assertIn('"operation_maturity":"verified"', metadata)


if __name__ == "__main__":
    unittest.main()
