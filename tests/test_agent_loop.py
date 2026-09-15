from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.agent_benchmark import evaluate_trajectory
from bsam_agent.api import LocalAgentApi
from bsam_agent.knowledge import KnowledgeQuery, RetrievalUnavailable
from bsam_agent.orchestrator import ChatOrchestrator, ConversationState, _model_task_context
from bsam_agent.provider import ProviderConfig, ProviderResponse


DECK = (
    b"INPUT\n3\nEND INPUT\n"
    b"BOUNDARY\n*type\nmechanical\n*boundary condition\n"
    b"type=disp, comp=x, name=bc5-1, value=0, nset=ply2.edge\n"
    b"*convergence\nd_reduction=0.25\nEND BOUNDARY\n"
    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
    b"CLUSTERS\n*type\nsolid\n*NAME\nply2\n*NODE\n2,1,0,0\n"
    b"*NSET,NSET=edge\n2\n*STOP\nEND CLUSTERS\n"
)


def config() -> ProviderConfig:
    return ProviderConfig(
        "cpu-local", "test", "http://127.0.0.1:1", None,
        1.0, 24000, 512, "local-private",
    )


def tool_decision(
    tool: str, arguments: dict[str, object], *, task_update: dict[str, object] | None = None,
) -> ProviderResponse:
    decision = {
        "outcome": "dispatch", "tool": tool, "arguments": arguments,
        "error_code": None, "response": None,
    }
    if task_update is not None:
        decision["task_update"] = task_update
    return ProviderResponse(content=json.dumps(decision))


def exhausted_decision(response: str) -> ProviderResponse:
    return ProviderResponse(content=json.dumps({
        "outcome": "exhausted", "tool": None, "arguments": {},
        "error_code": None, "response": response,
    }))


def synthesis_response(*claims: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(content=json.dumps({"claims": list(claims)}))


class ScriptedProvider:
    def __init__(self, *responses: ProviderResponse) -> None:
        self.responses = list(responses)
        self.requests = []

    def complete(self, request, cancel=None):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0)


class AgentLoopTests(unittest.TestCase):
    def test_model_can_choose_a_second_read_only_action_after_observation(self) -> None:
        provider = ScriptedProvider(
            tool_decision(
                "query_model", {
                    "source": "model.in", "query": "list_boundary_conditions",
                },
                task_update={"hypotheses": [{
                    "statement": "A boundary-condition reference may explain the reported issue.",
                    "status": "supported",
                    "supporting_observation_ids": ["obs-001"],
                    "refuting_observation_ids": [],
                }]},
            ),
            synthesis_response({
                "kind": "current_model",
                "text": "The inspected model contains one boundary condition requiring review.",
                "evidence_ids": ["obs-001", "obs-002"],
            }),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and tell me whether anything looks wrong.")

        self.assertEqual(["inspect_model", "query_model"], agent.state.task.completed_steps)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual(2, agent.state.task.step_count)
        self.assertEqual(2, len(agent.state.task.observations))
        self.assertEqual("obs-001", agent.state.task.observations[0]["observation_id"])
        self.assertEqual("hypothesis-001", agent.state.task.working_hypotheses[0]["hypothesis_id"])
        self.assertEqual(
            ["obs-001"],
            agent.state.task.working_hypotheses[0]["supporting_observation_ids"],
        )
        self.assertIn("Task context", provider.requests[0].messages[-1].content)
        self.assertEqual("query_model", result.tool)
        self.assertIn("Finding:", result.message)
        self.assertIn("[obs-001, obs-002]", result.message)
        self.assertIsNotNone(agent.state.task.final_synthesis)
        self.assertEqual(1, agent.state.task.model_step_count)
        restored = ConversationState.from_dict(agent.state.as_dict())
        self.assertEqual(agent.state.task.final_synthesis, restored.task.final_synthesis)

    def test_model_can_search_allowed_project_notes_after_model_inspection(self) -> None:
        provider = ScriptedProvider(
            tool_decision("search_workspace", {
                "query": "warning", "pattern": "*.md", "max_matches": 10,
            }),
            synthesis_response({
                "kind": "documentation",
                "text": "The project notes call for checking the ply2 edge set.",
                "evidence_ids": ["obs-002"],
            }),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            (root / "engineering-notes.md").write_text(
                "Boundary warning: verify the ply2 edge set.\n", encoding="utf-8",
            )
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and review project documentation for warnings.")

        self.assertEqual(["inspect_model", "search_workspace"], agent.state.task.completed_steps)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual("search_workspace", result.tool)
        self.assertEqual(1, result.tool_result["summary"]["matches"])
        evidence = agent.state.task.observations[-1]["evidence"]
        self.assertEqual("engineering-notes.md", evidence["workspace_matches"][0]["path"])
        local_context = _model_task_context(agent.state.task, hosted=False)
        hosted_context = _model_task_context(agent.state.task, hosted=True)
        self.assertIn("Boundary warning", local_context)
        self.assertNotIn("Boundary warning", hosted_context)
        self.assertNotIn("engineering-notes.md", hosted_context)
        self.assertNotIn('"pattern"', hosted_context)
        self.assertIn('"arguments_digest"', hosted_context)
        self.assertLessEqual(len(local_context), 12_000)
        self.assertLessEqual(len(hosted_context), 12_000)
        self.assertIn("Documentation:", result.message)

    def test_unknown_hypothesis_evidence_is_repaired_and_not_persisted(self) -> None:
        invalid = tool_decision(
            "query_model", {
                "source": "model.in", "query": "list_boundary_conditions",
            },
            task_update={"hypotheses": [{
                "statement": "An unsupported guess.",
                "status": "supported",
                "supporting_observation_ids": ["obs-999"],
                "refuting_observation_ids": [],
            }]},
        )
        corrected = tool_decision("query_model", {
            "source": "model.in", "query": "list_boundary_conditions",
        })
        provider = ScriptedProvider(
            invalid,
            corrected,
            synthesis_response({
                "kind": "inference",
                "text": "The boundary reference warrants further engineering review.",
                "evidence_ids": ["obs-001", "obs-002"],
            }),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and tell me whether anything looks wrong.")

        self.assertEqual("query_model", result.tool)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual([], agent.state.task.working_hypotheses)
        self.assertEqual(3, len(provider.requests))

    def test_grounded_synthesis_repairs_unknown_evidence_and_cannot_complete_task(self) -> None:
        provider = ScriptedProvider(
            tool_decision("query_model", {
                "source": "model.in", "query": "list_boundary_conditions",
            }),
            synthesis_response({
                "kind": "current_model", "text": "Unsupported claim.",
                "evidence_ids": ["obs-999"],
            }),
            synthesis_response({
                "kind": "current_model",
                "text": "The model has one inspected boundary condition.",
                "evidence_ids": ["obs-002"],
            }),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and tell me whether anything looks wrong.")

        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual([], agent.state.task.remaining_criteria)
        self.assertEqual(3, len(provider.requests))
        self.assertIn("[obs-002]", result.message)
        self.assertIn("Correct the grounded synthesis", provider.requests[-1].messages[-1].content)

    def test_hosted_grounded_synthesis_uses_sanitized_task_context(self) -> None:
        provider = ScriptedProvider(
            tool_decision("search_workspace", {
                "query": "warning", "pattern": "*.md", "max_matches": 10,
            }),
            synthesis_response({
                "kind": "documentation",
                "text": "Retrieved project documentation contains a warning.",
                "evidence_ids": ["obs-002"],
            }),
        )
        hosted = ProviderConfig(
            "openai", "test", "https://api.openai.com/v1", "OPENAI_API_KEY",
            1.0, 24_000, 512, "hosted-redacted",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            (root / "private-engineering-notes.md").write_text(
                "Secret boundary warning for the ply2 edge set.\n", encoding="utf-8",
            )
            agent = ChatOrchestrator(provider, hosted, LocalAgentApi(root))
            agent.turn("Inspect model.in and review project documentation for warnings.")

        synthesis_prompt = provider.requests[-1].messages[-1].content
        self.assertIn("Completed task evidence", synthesis_prompt)
        self.assertNotIn("private-engineering-notes.md", synthesis_prompt)
        self.assertNotIn("Secret boundary warning", synthesis_prompt)
        self.assertNotIn("ply2", synthesis_prompt)

    def test_workspace_evidence_request_can_start_without_a_model_source(self) -> None:
        provider = ScriptedProvider(tool_decision("search_workspace", {
            "query": "convergence", "pattern": "*.md", "max_matches": 10,
        }))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "engineering-notes.md").write_text(
                "Investigate convergence after validating the boundary set.\n", encoding="utf-8",
            )
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Find project documentation mentioning convergence.")

        self.assertEqual("search_workspace", result.tool)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual(["search_workspace"], agent.state.task.completed_steps)
        offered = provider.requests[0].response_schema["properties"]["tool"]["enum"]
        self.assertIn("list_workspace_files", offered)
        self.assertIn("read_allowed_text_file", offered)
        self.assertIn("search_workspace", offered)
        self.assertEqual(["workspace_evidence_collected"], agent.state.task.completion_criteria)

    def test_boundary_investigation_uses_model_selected_read_only_continuations(self) -> None:
        provider = ScriptedProvider(
            tool_decision("query_model", {
                "source": "model.in", "query": "list_boundary_conditions",
            }),
            tool_decision("find_references", {
                "source": "model.in", "direction": "outbound",
                "entity_kind": "boundary-condition", "entity_name": "bc5-1",
            }),
            synthesis_response({
                "kind": "inference",
                "text": "The boundary condition resolves to the inspected ply2 edge set.",
                "evidence_ids": ["obs-002", "obs-003", "obs-004"],
            }),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn(
                "Something looks wrong with the boundary conditions in model.in. Check it."
            )

        self.assertEqual(
            ["inspect_model", "query_model", "find_references", "validate_model"],
            agent.state.task.completed_steps,
        )
        self.assertEqual("complete", agent.state.task.status)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(3, len(provider.requests))
        self.assertTrue(all(
            "Task context" in request.messages[-1].content for request in provider.requests[:2]
        ))
        self.assertIn("Inference:", result.message)
        offered = provider.requests[0].response_schema["properties"]["tool"]["enum"]
        self.assertTrue({
            "query_model", "inspect_entity", "find_references", "validate_model",
        }.issubset(offered))

    def test_repeated_successful_action_stops_the_agent_loop(self) -> None:
        provider = ScriptedProvider(tool_decision("inspect_model", {"source": "model.in"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and tell me whether anything looks wrong.")

        self.assertEqual("repeated_action", result.error_code)
        self.assertEqual("blocked", agent.state.task.status)
        self.assertEqual(1, agent.state.task.step_count)

    def test_canonical_alias_cannot_repeat_an_equivalent_successful_query(self) -> None:
        provider = ScriptedProvider(
            tool_decision("query_model", {
                "source": "model.in", "query": "list_boundary_conditions",
            }),
            tool_decision("query_model", {
                "source": "model.in", "query": "list-boundary-conditions",
            }),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn(
                "Something looks wrong with the boundary conditions in model.in. Check it."
            )

        self.assertEqual("repeated_action", result.error_code)
        self.assertEqual("blocked", agent.state.task.status)
        self.assertEqual(["inspect_model", "query_model"], agent.state.task.completed_steps)

    def test_model_can_stop_safely_when_useful_read_only_evidence_is_exhausted(self) -> None:
        provider = ScriptedProvider(exhausted_decision(
            "The available deterministic observations do not identify a narrower cause."
        ))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and tell me whether anything looks wrong.")

        self.assertEqual("evidence_exhausted", result.error_code)
        self.assertEqual("blocked", agent.state.task.status)
        self.assertEqual("evidence_exhausted", agent.state.task.terminal_reason)
        self.assertIn("focused_evidence_collected", result.message)

    def test_compare_original_with_last_changed_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            (root / "model.changed.in").write_bytes(
                DECK.replace(b"d_reduction=0.25", b"d_reduction=0.5")
            )
            agent = ChatOrchestrator(ScriptedProvider(), config(), LocalAgentApi(root))
            agent.state.model_context.active_source = "model.changed.in"
            agent.state.model_context.last_created_output = "model.changed.in"
            agent.state.model_context.recent_sources = ["model.changed.in", "model.in"]
            result = agent.turn("Compare the original with the last changed model.")

        self.assertEqual("compare_models", result.tool)
        self.assertEqual("complete", agent.state.task.status)
        self.assertGreater(result.tool_result["differences"]["changed_lines"], 0)

    def test_failed_run_diagnosis_observes_status_then_bounded_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            output = root / "runs" / "case"
            output.mkdir(parents=True)
            (output / "run-manifest.json").write_text(json.dumps({
                "schema_version": "1.0.0", "state": "terminal",
                "classification": "failed", "deck": str(root / "model.in"),
                "output_directory": str(output), "process_exit_code": 2,
                "fatal_markers": ["ERROR:"],
            }), encoding="utf-8")
            (output / "process.stderr.log").write_text(
                "ERROR: input processing stopped at BOUNDARY", encoding="latin-1",
            )
            agent = ChatOrchestrator(ScriptedProvider(), config(), LocalAgentApi(root))
            agent.state.model_context.last_run = {
                "output_directory": "runs/case", "state": "terminal",
                "classification": "failed",
            }
            result = agent.turn("Why did the last run fail?")

        self.assertEqual(["get_run_status", "inspect_run_log"], agent.state.task.completed_steps)
        self.assertEqual("complete", agent.state.task.status)
        self.assertIn("ERROR:", result.message)

    def test_change_validate_and_run_stops_at_two_distinct_confirmations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(ScriptedProvider(), config(), LocalAgentApi(root))
            preview = agent.turn(
                "Change d_reduction in model.in to 0.5, preserve the original, validate it, and run it."
            )
            ready_to_run = agent.turn("/confirm")

        self.assertTrue(preview.requires_confirmation)
        self.assertTrue(ready_to_run.requires_confirmation)
        self.assertEqual("run_bsam", agent.state.pending_action.tool)
        self.assertEqual(
            ["inspect_model", "preview_parameter_change", "apply_change", "validate_model"],
            agent.state.task.completed_steps,
        )

    def test_state_round_trip_and_trajectory_metrics_include_agent_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(ScriptedProvider(), config(), LocalAgentApi(root))
            turn = agent.turn("Inspect model.in")
            restored = ConversationState.from_dict(agent.state.as_dict())
            legacy = agent.state.as_dict()
            legacy["schema_version"] = "0.6.0"
            legacy["task"].pop("working_hypotheses")
            legacy["task"].pop("model_step_count")
            legacy["task"].pop("final_synthesis")
            for observation in legacy["task"]["observations"]:
                observation.pop("observation_id")
            migrated = ConversationState.from_dict(legacy)
            report = evaluate_trajectory(restored.task, [turn], {
                "tool_sequence": ["inspect_model"],
                "confirmation_boundaries": 0,
                "terminal_status": "complete",
                "no_mutation": True,
            })

        self.assertTrue(report["passed"])
        self.assertEqual(1, restored.task.step_count)
        self.assertEqual("inspect_model", restored.task.observations[0]["tool"])
        self.assertEqual("model.in", restored.task.active_source)
        self.assertIsNotNone(restored.task.active_source_digest)
        self.assertTrue(restored.task.recent_entities)
        self.assertEqual(["model_inspected"], restored.task.completion_criteria)
        self.assertEqual("obs-001", restored.task.observations[0]["observation_id"])
        self.assertEqual([], migrated.task.working_hypotheses)
        self.assertEqual("obs-001", migrated.task.observations[0]["observation_id"])

    def test_model_can_request_one_focused_clarification(self) -> None:
        clarification = ProviderResponse(content=json.dumps({
            "outcome": "clarify", "tool": None, "arguments": {},
            "error_code": "clarification_required",
            "response": "Which material definition should be treated as authoritative?",
        }))
        provider = ScriptedProvider(clarification)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and tell me whether anything looks wrong.")

        self.assertEqual("clarification_required", result.error_code)
        self.assertEqual("clarify", agent.state.task.status)
        self.assertEqual(1, len(agent.state.task.missing_decisions))

    def test_unsupported_syntax_repair_stops_after_read_only_evidence(self) -> None:
        refusal = ProviderResponse(content=json.dumps({
            "outcome": "refuse", "tool": None, "arguments": {},
            "error_code": "unsupported_capability",
            "response": "No deterministic syntax-repair primitive is registered.",
        }))
        provider = ScriptedProvider(refusal)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn(
                "Inspect model.in and fix syntax-only issues without changing physics."
            )

        self.assertEqual(["inspect_model"], agent.state.task.completed_steps)
        self.assertEqual("refused", agent.state.task.status)
        self.assertEqual("unsupported_capability", result.error_code)
        self.assertFalse((root / "model.changed.in").exists())

    def test_retrieval_interface_is_fail_closed_and_non_authoritative(self) -> None:
        query = KnowledgeQuery("search_bsam_knowledge", "convergence guidance")
        self.assertEqual((), RetrievalUnavailable().retrieve(query))


if __name__ == "__main__":
    unittest.main()
