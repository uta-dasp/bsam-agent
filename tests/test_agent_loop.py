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


def tool_decision(tool: str, arguments: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(content=json.dumps({
        "outcome": "dispatch", "tool": tool, "arguments": arguments,
        "error_code": None, "response": None,
    }))


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
        provider = ScriptedProvider(tool_decision("query_model", {
            "source": "model.in", "query": "list_boundary_conditions",
        }))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Inspect model.in and tell me whether anything looks wrong.")

        self.assertEqual(["inspect_model", "query_model"], agent.state.task.completed_steps)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual(2, agent.state.task.step_count)
        self.assertEqual(2, len(agent.state.task.observations))
        self.assertIn("Task context", provider.requests[0].messages[-1].content)
        self.assertEqual("query_model", result.tool)

    def test_model_can_search_allowed_project_notes_after_model_inspection(self) -> None:
        provider = ScriptedProvider(tool_decision("search_workspace", {
            "query": "warning", "pattern": "*.md", "max_matches": 10,
        }))
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

    def test_boundary_investigation_chains_without_model_or_confirmation(self) -> None:
        provider = ScriptedProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn(
                "Something looks wrong with the boundary conditions in model.in. Check it."
            )

        self.assertEqual(
            ["inspect_model", "query_model", "query_model", "validate_model"],
            agent.state.task.completed_steps,
        )
        self.assertEqual("complete", agent.state.task.status)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual([], provider.requests)

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
