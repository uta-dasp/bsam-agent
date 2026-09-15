from __future__ import annotations

import hashlib
import json
from copy import deepcopy
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.agent_benchmark import evaluate_trajectory
from bsam_agent.api import LocalAgentApi
from bsam_agent.knowledge import KnowledgeQuery, RetrievalUnavailable
from bsam_agent.local_provider import ProviderError
from bsam_agent.orchestrator import (
    ChatOrchestrator, ChatTurn, ConversationState, TaskAuthorization, TaskState,
    _bounded_observation, _compact_task_state, _model_task_context,
    _next_deterministic_task_action, _task_completion, _validate_grounded_synthesis,
)
from bsam_agent.provider import ProviderConfig, ProviderResponse
from bsam_agent.task_workspace import TaskWorkspace


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
    def test_explicit_run_authorization_is_audited_consumed_and_persisted(self) -> None:
        class RunApi:
            def dispatch(self, tool, arguments):
                self.tool = tool
                self.arguments = arguments
                return {
                    "state": "accepted", "classification": "pending",
                    "output_directory": arguments["output_dir"],
                }

        provider = ScriptedProvider(tool_decision("run_bsam", {
            "source": "model.in", "output_dir": "runs/case",
            "executable": "bsam20.exe", "confirm": False,
        }))
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory) / "audit"
            api = RunApi()
            agent = ChatOrchestrator(provider, config(), api, audit_directory=audit)  # type: ignore[arg-type]
            result = agent.turn("Run model.in in runs/case.")
            restored = ConversationState.from_dict(agent.state.as_dict())
            events = [
                json.loads(line) for line in agent.audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertFalse(result.requires_confirmation)
        self.assertEqual("run_bsam", api.tool)
        self.assertTrue(api.arguments["confirm"])
        self.assertEqual("execution_when_explicitly_requested", agent.state.task.authorization.mode)
        self.assertEqual("consumed", agent.state.task.authorization.status)
        self.assertEqual(["full"], agent.state.task.authorization.consumed_run_kinds)
        self.assertEqual(["runs/case"], agent.state.task.authorization.destination_scope)
        self.assertEqual(agent.state.task.authorization, restored.task.authorization)
        self.assertTrue(any(item["event"] == "authorization_granted" for item in events))
        self.assertTrue(any(item["event"] == "authorization_consumed" for item in events))
        self.assertTrue(any(
            item["event"] == "confirmation_satisfied_by_task_authorization" for item in events
        ))

    def test_local_run_output_is_routed_into_the_task_workspace(self) -> None:
        class ScopedRunApi:
            def __init__(self, workspace_root: Path) -> None:
                self.workspace_root = workspace_root

            def dispatch(self, tool, arguments):
                self.arguments = arguments
                return {
                    "state": "accepted", "classification": "pending",
                    "output_directory": arguments["output_dir"],
                }

        provider = ScriptedProvider(tool_decision("run_bsam", {
            "source": "model.in", "output_dir": "project-runs/case",
            "executable": "bsam20.exe", "confirm": False,
        }))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            api = ScopedRunApi(root)
            agent = ChatOrchestrator(provider, config(), api)  # type: ignore[arg-type]
            result = agent.turn("Run model.in in project-runs/case.")
            task_root = agent.state.task.task_workspace["root"]

        self.assertFalse(result.requires_confirmation)
        self.assertTrue(api.arguments["output_dir"].startswith(f"{task_root}/runs/full-"))
        self.assertIn(api.arguments["output_dir"], agent.state.task.authorization.destination_scope)
        self.assertEqual(api.arguments["output_dir"], result.tool_result["output_directory"])

    def test_edit_authorization_can_be_revoked_with_pending_write_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(ScriptedProvider(), config(), LocalAgentApi(root))
            preview = agent.turn("Change d_reduction in model.in to 0.5.")
            revoked = agent.turn("/revoke")
            restored = ConversationState.from_dict(agent.state.as_dict())

        self.assertTrue(preview.requires_confirmation)
        self.assertEqual("edits_with_confirmation", agent.state.task.authorization.mode)
        self.assertEqual("authorization_revoked", revoked.error_code)
        self.assertIsNone(agent.state.pending_action)
        self.assertEqual("revoked", restored.task.authorization.status)
        self.assertEqual("user_revoked", restored.task.authorization.revoked_reason)
        self.assertEqual("authorization_revoked", restored.task.terminal_reason)

    def test_execution_authorization_expires_rejects_scope_expansion_and_is_single_use(self) -> None:
        authorization = TaskAuthorization(
            mode="execution_when_explicitly_requested", operations=["read", "execute"],
            source_scope=["model.in"], run_kinds=["full"], max_executions=1,
            granted_turn=1, expires_after_turn=2,
        )
        task = TaskState("Run model.in", "model.in", ["run"], authorization=authorization)
        expired_state = ConversationState(turn_number=3, task=task)
        expired = ChatOrchestrator(
            ScriptedProvider(), config(), object(), state=expired_state,  # type: ignore[arg-type]
        )
        self.assertFalse(expired._consume_execution_authorization(
            task, {"source": "model.in", "output_dir": "runs/model"},
        ))
        self.assertEqual("expired", authorization.status)

        active = TaskAuthorization(
            mode="execution_when_explicitly_requested", operations=["read", "execute"],
            source_scope=["model.in"], run_kinds=["full"], max_executions=1,
            granted_turn=1, expires_after_turn=9,
        )
        active_task = TaskState(
            "Run model.in in runs/case2", "model.in", ["run"], authorization=active,
        )
        agent = ChatOrchestrator(
            ScriptedProvider(), config(), object(),
            state=ConversationState(turn_number=2, task=active_task),  # type: ignore[arg-type]
        )
        self.assertFalse(agent._consume_execution_authorization(
            active_task, {"source": "other.in", "output_dir": "runs/model"},
        ))
        self.assertEqual(0, active.executions_used)
        self.assertFalse(agent._consume_execution_authorization(
            active_task, {"source": "model.in", "output_dir": "runs/other"},
        ))
        self.assertFalse(agent._consume_execution_authorization(
            active_task, {"source": "model.in", "output_dir": "runs/case"},
        ))
        self.assertTrue(agent._consume_execution_authorization(
            active_task, {"source": "model.in", "output_dir": "runs/model"},
        ))
        self.assertFalse(agent._consume_execution_authorization(
            active_task, {"source": "model.in", "output_dir": "runs/model"},
        ))
        self.assertEqual("consumed", active.status)

    def test_smoke_request_does_not_silently_dispatch_a_full_run(self) -> None:
        class NoRunApi:
            def dispatch(self, tool, arguments):
                raise AssertionError(f"unexpected full execution: {tool} {arguments}")

        provider = ScriptedProvider(tool_decision("run_bsam", {
            "source": "model.in", "output_dir": "runs/smoke",
            "executable": "bsam20.exe", "confirm": False,
        }))
        agent = ChatOrchestrator(provider, config(), NoRunApi())  # type: ignore[arg-type]
        result = agent.turn("Run a smoke test of model.in.")

        self.assertEqual("unsupported_capability", result.error_code)
        self.assertEqual("smoke_test_unavailable", agent.state.task.terminal_reason)
        self.assertEqual(["smoke"], agent.state.task.authorization.run_kinds)
        self.assertEqual(0, agent.state.task.authorization.executions_used)

    def test_explicit_stop_is_authorized_within_the_active_run_lifecycle(self) -> None:
        class StopApi:
            def dispatch(self, tool, arguments):
                self.calls = getattr(self, "calls", [])
                self.calls.append((tool, arguments))
                if tool == "get_run_status":
                    return {
                        "state": "terminal", "classification": "stopped",
                        "output_directory": arguments["output_dir"],
                    }
                return {
                    "state": "stopping", "classification": "pending",
                    "output_directory": arguments["output_dir"],
                }

        provider = ScriptedProvider(
            tool_decision("stop_run", {
                "output_dir": "runs/case", "confirm": False,
            }),
            tool_decision("get_run_status", {"output_dir": "runs/case"}),
        )
        api = StopApi()
        agent = ChatOrchestrator(provider, config(), api)  # type: ignore[arg-type]
        agent.state.model_context.last_run = {
            "output_directory": "runs/case", "state": "running", "classification": "pending",
        }
        result = agent.turn("Stop it.")

        self.assertFalse(result.requires_confirmation)
        self.assertEqual(["stop_run", "get_run_status"], [item[0] for item in api.calls])
        self.assertTrue(api.calls[0][1]["confirm"])
        self.assertEqual("get_run_status", result.tool)
        self.assertEqual(["read", "stop"], agent.state.task.authorization.operations)
        self.assertEqual("consumed", agent.state.task.authorization.status)

    def test_provider_cancellation_propagates_to_a_safe_task_terminal(self) -> None:
        class CancelledProvider:
            def complete(self, request, cancel=None):
                self.assert_cancelled = cancel is not None and cancel.is_set()
                raise ProviderError(
                    "cancelled", "provider request was cancelled", retryable=False,
                    correlation_id=request.correlation_id,
                )

        provider = CancelledProvider()
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn(
                "Inspect model.in and tell me whether anything looks wrong.", cancel=cancel,
            )

        self.assertTrue(provider.assert_cancelled)
        self.assertEqual("provider_cancelled", result.error_code)
        self.assertEqual("blocked", agent.state.task.status)
        self.assertEqual("provider_cancelled", agent.state.task.terminal_reason)

    def test_synthesis_cancellation_preserves_deterministic_completion_without_retry(self) -> None:
        cancel = threading.Event()

        class SynthesisCancelledProvider:
            def __init__(self) -> None:
                self.calls = 0

            def complete(self, request, supplied_cancel=None):
                self.calls += 1
                if self.calls == 1:
                    cancel.set()
                    return tool_decision("query_model", {
                        "source": "model.in", "query": "list_boundary_conditions",
                    })
                raise ProviderError(
                    "cancelled", "provider request was cancelled", retryable=False,
                    correlation_id=request.correlation_id,
                )

        provider = SynthesisCancelledProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn(
                "Inspect model.in and tell me whether anything looks wrong.", cancel=cancel,
            )

        self.assertEqual(2, provider.calls)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual([], agent.state.task.remaining_criteria)
        self.assertIsNone(agent.state.task.final_synthesis)
        self.assertEqual("provider_cancelled", result.error_code)
        self.assertIn("deterministic evidence remains complete", result.message)

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
        self.assertIn('"authorization":{"executions_used":0', local_context)
        self.assertIn('"mode":"read_only"', hosted_context)
        self.assertNotIn('"source_scope"', hosted_context)
        self.assertNotIn(".bsam-agent/tasks", hosted_context)
        self.assertLessEqual(len(local_context), 12_000)
        self.assertLessEqual(len(hosted_context), 12_000)
        self.assertIn("Documentation:", result.message)

    def test_explain_entities_inspects_each_match_then_synthesizes_grounded_claims(self) -> None:
        provider = ScriptedProvider(synthesis_response(
            {
                "kind": "current_model",
                "text": "Crack 1 is type 301 and targets cluster ply1.",
                "evidence_ids": ["obs-002"],
            },
            {
                "kind": "current_model",
                "text": "Crack 2 is type 301 and targets cluster ply2.",
                "evidence_ids": ["obs-003"],
            },
            {
                "kind": "inference",
                "text": "The two declarations apply the same crack formulation to different plies.",
                "evidence_ids": ["obs-002", "obs-003"],
            },
            {
                "kind": "general",
                "text": "Crack definitions describe candidate discontinuity behavior.",
                "evidence_ids": [],
            },
        ))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cracks.in").write_bytes(
                (Path(__file__).parent / "fixtures" / "conversational_cracks.in").read_bytes()
            )
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Explain the cracks in cracks.in.")

        self.assertEqual(
            ["query_model", "inspect_entity", "inspect_entity"],
            agent.state.task.completed_steps,
        )
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual([], agent.state.task.remaining_criteria)
        self.assertEqual(
            ["1", "2"],
            [
                observation["evidence"]["entity_details"][0]["name"]
                for observation in agent.state.task.observations[1:]
            ],
        )
        first_parameters = agent.state.task.observations[1]["evidence"][
            "entity_details"
        ][0]["capability_records"][0]["parameters"]
        self.assertEqual(["ply1"], first_parameters["cluster"])
        self.assertEqual(["ply2"], agent.state.task.observations[2]["evidence"][
            "entity_details"
        ][0]["capability_records"][0]["parameters"]["cluster"])
        self.assertEqual(1, len(provider.requests))
        self.assertIn('"cluster":["ply1"]', provider.requests[0].messages[-1].content)
        self.assertIn('"cluster":["ply2"]', provider.requests[0].messages[-1].content)
        self.assertIn("Finding:", result.message)
        self.assertIn("Inference:", result.message)
        self.assertIn("General context:", result.message)
        self.assertEqual("inference", agent.state.task.final_synthesis["claims"][2]["kind"])

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

    def test_change_validate_and_explicit_run_uses_one_edit_confirmation(self) -> None:
        class ChangeAndRunApi(LocalAgentApi):
            def dispatch(self, tool, arguments):
                if tool == "run_bsam":
                    self.run_arguments = arguments
                    return {
                        "state": "accepted", "classification": "pending",
                        "output_directory": arguments["output_dir"],
                    }
                return super().dispatch(tool, arguments)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            api = ChangeAndRunApi(root)
            agent = ChatOrchestrator(ScriptedProvider(), config(), api)
            preview = agent.turn(
                "Change d_reduction in model.in to 0.5, preserve the original, validate it, and run it."
            )
            accepted = agent.turn("/confirm")

        self.assertTrue(preview.requires_confirmation)
        self.assertFalse(accepted.requires_confirmation)
        self.assertEqual("run_bsam", accepted.tool)
        self.assertIsNone(agent.state.pending_action)
        self.assertTrue(api.run_arguments["confirm"])
        self.assertEqual(
            [
                "inspect_model", "preview_parameter_change", "apply_change",
                "validate_model", "run_bsam",
            ],
            agent.state.task.completed_steps,
        )
        self.assertEqual("execution_when_explicitly_requested", agent.state.task.authorization.mode)
        self.assertEqual("consumed", agent.state.task.authorization.status)
        self.assertEqual(["full"], agent.state.task.authorization.consumed_run_kinds)

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
            legacy["task"].pop("authorization")
            legacy["task"].pop("task_workspace")
            for observation in legacy["task"]["observations"]:
                observation.pop("observation_id")
            migrated = ConversationState.from_dict(legacy)
            report = evaluate_trajectory(restored.task, [turn], {
                "tool_sequence": ["inspect_model"],
                "confirmation_boundaries": 0,
                "terminal_status": "complete",
                "no_mutation": True,
            })
            workspace_manifest = json.loads(
                (root / restored.task.task_workspace["manifest"]).read_text(encoding="utf-8")
            )

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
        self.assertIsNotNone(restored.task.task_workspace)
        self.assertEqual("active", restored.task.task_workspace["state"])
        self.assertEqual(["model.in"], workspace_manifest["source_scope"])
        self.assertEqual(
            hashlib.sha256(b"Inspect model.in").hexdigest(),
            workspace_manifest["objective_sha256"],
        )

    def test_context_compaction_archives_immutable_evidence_and_keeps_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            task_area = TaskWorkspace.create(
                root, "task-compact", objective_sha256="a" * 64,
                source_scope=["model.in"],
            )
            task = TaskState(
                "Explain model.in", "model.in", ["inspect"], max_steps=20,
                engineering_assumptions=["Use the selected model."],
                missing_decisions=["Choose the reporting basis."],
                user_decisions=[{
                    "decision_id": "decision-001", "question": "Choose units.",
                    "value": "SI", "turn": 1,
                }],
                task_workspace={
                    "task_id": "task-compact",
                    "root": ".bsam-agent/tasks/task-compact",
                    "manifest": ".bsam-agent/tasks/task-compact/task-workspace.json",
                    "state": "active",
                },
            )
            agent = ChatOrchestrator(ScriptedProvider(), config(), LocalAgentApi(root))
            agent.state.task = task
            for index in range(1, 11):
                agent._append_task_observation(
                    task, "inspect_model", {"source": "model.in"},
                    {"source_set_sha256": f"{index:064x}", "summary": {"errors": 0}},
                )

            restored = TaskState.from_dict(task.as_dict())
            context = json.loads(_model_task_context(restored, hosted=False))
            hosted_context = _model_task_context(restored, hosted=True)
            archived = restored.context_compaction["archived_observations"]
            manifest = task_area.manifest()

        self.assertEqual(["obs-001", "obs-002", "obs-003", "obs-004"], [
            item["observation_id"] for item in archived
        ])
        self.assertEqual(["obs-005", "obs-006", "obs-007", "obs-008", "obs-009", "obs-010"], [
            item["observation_id"] for item in restored.observations
        ])
        self.assertEqual(10, len(manifest["artifacts"]))
        self.assertEqual("SI", context["user_decisions"][0]["value"])
        self.assertEqual(4, len(context["compaction"]["archived_observations"]))
        self.assertNotIn(".bsam-agent/tasks", hosted_context)
        _validate_grounded_synthesis({"claims": [{
            "kind": "current_model", "text": "The archived inspection is deterministic.",
            "evidence_ids": ["obs-001"],
        }]}, restored)
        tampered = restored.as_dict()
        tampered["context_compaction"]["archived_observations"][0]["artifact"] = (
            ".bsam-agent/tasks/another-task/observations/obs-001.json"
        )
        with self.assertRaisesRegex(ValueError, "evidence path"):
            TaskState.from_dict(tampered)

    def test_compaction_preserves_completion_authorization_and_next_action(self) -> None:
        steps = [
            {
                "index": index, "tool": "inspect_model", "status": "completed",
                "arguments_digest": f"{index:064x}", "result_digest": f"{index + 50:064x}",
            }
            for index in range(1, 11)
        ]
        task = TaskState(
            "Inspect and validate model.in", "model.in", ["inspect", "validate"],
            status="verify", steps=steps, step_count=10, max_steps=20,
            completed_steps=["inspect_model"] * 10,
            completion_criteria=["model_inspected", "validation_passed"],
            remaining_criteria=["validation_passed"],
            observations=[
                _bounded_observation(
                    "inspect_model", {"source": "model.in"},
                    {"source_set_sha256": f"{index:064x}", "summary": {"errors": 0}},
                    index,
                )
                for index in range(1, 11)
            ],
            task_workspace={
                "task_id": "task-equivalence",
                "root": ".bsam-agent/tasks/task-equivalence",
                "manifest": ".bsam-agent/tasks/task-equivalence/task-workspace.json",
                "state": "active",
            },
        )
        uncompacted = deepcopy(task)
        latest = ChatTurn("conversation", "verify", "continue")

        self.assertTrue(_compact_task_state(task))

        self.assertEqual(_task_completion(uncompacted), _task_completion(task))
        self.assertEqual(
            _next_deterministic_task_action(uncompacted, latest),
            _next_deterministic_task_action(task, latest),
        )
        self.assertEqual(uncompacted.authorization.as_dict(), task.authorization.as_dict())
        self.assertEqual(uncompacted.remaining_criteria, task.remaining_criteria)
        self.assertEqual(uncompacted.working_plan, task.working_plan)
        TaskState.from_dict(task.as_dict())

    def test_task_authorization_rejects_inconsistent_persisted_state(self) -> None:
        value = TaskAuthorization().as_dict()
        value["operations"] = ["read", "execute"]
        with self.assertRaisesRegex(ValueError, "read-only.*inconsistent"):
            TaskAuthorization.from_dict(value)

        value = TaskAuthorization(
            mode="execution_when_explicitly_requested",
            operations=["read", "execute"], run_kinds=["full"], max_executions=1,
        ).as_dict()
        value["max_executions"] = 2
        with self.assertRaisesRegex(ValueError, "limit.*inconsistent"):
            TaskAuthorization.from_dict(value)

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
