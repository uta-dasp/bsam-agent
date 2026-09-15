from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import LocalAgentApi
from bsam_agent.orchestrator import (
    ChatOrchestrator, ConversationState, TaskAuthorization, TaskState, _task_completion,
)
from bsam_agent.provider import ProviderConfig, ProviderResponse, Usage
from bsam_agent.task_workspace import TaskWorkspace


PARAMETER_DECK = (
    b"INPUT\n3\nEND INPUT\n"
    b"BOUNDARY\n*type\nmechanical\n*convergence\nd_reduction=0.5\nEND BOUNDARY\n"
    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
    b"MATERIALS\n0\nEND MATERIALS\n"
    b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
)

RENAME_DECK = (
    b"INPUT\n3\nEND INPUT\n"
    b"BOUNDARY\n*type\nmechanical\n"
    b"*boundary condition\n"
    b"type=disp, comp=x, name=pull, value=0, nset=ply.edge\n"
    b"*loading sequence\n"
    b"type=Static, name=step1, nstep=1, incr=1\n"
    b"change=pull, type=disp, value=1\n"
    b"END BOUNDARY\n"
    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
    b"MATERIALS\n0\nEND MATERIALS\n"
    b"CLUSTERS\n*type\nsolid\n*NAME\nply\n"
    b"*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n*STOP\nEND CLUSTERS\n"
)


def config() -> ProviderConfig:
    return ProviderConfig(
        "cpu-local", "test", "http://127.0.0.1:1", None,
        1.0, 24000, 512, "local-private",
    )


class ScriptedProvider:
    def __init__(self, *responses: ProviderResponse) -> None:
        self.responses = list(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0)


def decision(tool: str, arguments: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(
        content=json.dumps({
            "outcome": "dispatch", "tool": tool, "arguments": arguments,
            "error_code": None, "response": None,
        }),
        usage=Usage(10, 5),
    )


class FailedRunApi:
    def dispatch(self, tool, arguments):
        if tool != "run_bsam":
            raise AssertionError(f"unexpected tool {tool}")
        return {
            "state": "terminal",
            "classification": "failed",
            "failure_category": "execution_input_failure",
            "diagnostic": "input processing stopped at BOUNDARY",
            "output_directory": "runs/case",
            "source_set_sha256": "A" * 64,
        }


class RunLifecycleApi:
    def __init__(self) -> None:
        self.status_calls = 0

    def dispatch(self, tool, arguments):
        if tool == "run_bsam":
            return {
                "state": "accepted",
                "classification": "pending",
                "output_directory": "runs/case",
            }
        if tool == "get_run_status":
            self.status_calls += 1
            if self.status_calls == 1:
                return {
                    "state": "running",
                    "classification": "pending",
                    "output_directory": "runs/case",
                }
            return {
                "state": "terminal",
                "classification": "stopped",
                "output_directory": "runs/case",
            }
        raise AssertionError(f"unexpected tool {tool}")


class TaskTrajectoryTests(unittest.TestCase):
    def test_run_status_updates_persisted_task_through_terminal_state(self) -> None:
        provider = ScriptedProvider(
            decision("run_bsam", {
                "source": "model.in", "output_dir": "runs/case",
                "executable": "bsam20.exe", "confirm": False, "timeout": 30,
            }),
            decision("get_run_status", {"output_dir": "runs/case"}),
            decision("get_run_status", {"output_dir": "runs/case"}),
        )
        api = RunLifecycleApi()
        agent = ChatOrchestrator(provider, config(), api)  # type: ignore[arg-type]

        accepted = agent.turn("Run model.in in runs/case with a 30 second timeout.")
        running = agent.turn("Check status for runs/case.")
        terminal = agent.turn("Check status for runs/case again.")
        restored = ConversationState.from_dict(agent.state.as_dict())

        self.assertFalse(accepted.requires_confirmation)
        self.assertEqual("pending", accepted.tool_result["classification"])
        self.assertEqual("running", running.tool_result["state"])
        self.assertEqual("stopped", terminal.tool_result["classification"])
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual({
            "state": "terminal",
            "classification": "stopped",
            "output_directory": "runs/case",
        }, agent.state.task.run_state)
        self.assertEqual(agent.state.task.run_state, restored.task.run_state)

    def test_composite_plan_has_one_confirmation_and_post_apply_validation(self) -> None:
        provider = ScriptedProvider(decision("preview_compose_changes", {
            "source": "model.in",
            "plan_paths": ["reduction.json", "iterations.json"],
            "plan_path": "combined.json",
        }))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = PARAMETER_DECK.replace(
                b"d_reduction=0.5\n", b"d_reduction=0.5\nmaxiterations=20\n"
            )
            (root / "model.in").write_bytes(deck)
            api = LocalAgentApi(root)
            api.dispatch("preview_parameter_change", {
                "source": "model.in", "block": "BOUNDARY", "construct": "CONVERGENCE",
                "parameter": "d_reduction", "value": "0.4", "plan_path": "reduction.json",
            })
            api.dispatch("preview_parameter_change", {
                "source": "model.in", "block": "BOUNDARY", "construct": "CONVERGENCE",
                "parameter": "maxiterations", "value": "30", "plan_path": "iterations.json",
            })
            agent = ChatOrchestrator(provider, config(), api)

            preview = agent.turn(
                "Combine reduction.json and iterations.json for model.in into combined.in "
                "and validate it."
            )
            applied = agent.turn("/confirm")
            output = (root / "combined.in").read_bytes()

        self.assertTrue(preview.requires_confirmation)
        self.assertEqual(
            ["inspect_model", "preview_compose_changes", "apply_change", "validate_model"],
            [item["tool"] for item in agent.state.task.steps],
        )
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual(0, applied.tool_result["post_apply_validation"]["summary"]["errors"])
        self.assertIn(b"d_reduction=0.4", output)
        self.assertIn(b"maxiterations=30", output)

    def test_ambiguous_parameter_stops_for_focused_clarification(self) -> None:
        provider = ScriptedProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(RENAME_DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            result = agent.turn("Change type in model.in to off and validate it.")

            restored_state = ConversationState.from_dict(agent.state.as_dict())
            resumed = ChatOrchestrator(
                provider, config(), LocalAgentApi(root), state=restored_state,
            )
            continued = resumed.turn("Use BOUNDARY/BOUNDARY CONDITION.")

        self.assertEqual("invalid_arguments", result.error_code)
        self.assertIn("ambiguous", result.message)
        self.assertEqual("clarify", agent.state.task.status)
        self.assertGreaterEqual(len(agent.state.task.missing_decisions), 2)
        self.assertEqual([], agent.state.task.steps)
        self.assertEqual("preview_parameter_change", continued.tool)
        self.assertEqual("confirm", continued.phase)
        self.assertEqual([], resumed.state.task.missing_decisions)
        self.assertIsNone(resumed.state.task.clarification)
        self.assertEqual("BOUNDARY/BOUNDARY CONDITION", resumed.state.task.user_decisions[0]["value"])
        self.assertEqual(2, resumed.state.task.user_decisions[0]["turn"])
        self.assertEqual([], provider.requests)

    def test_save_resume_across_compaction_preserves_task_meaning_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(PARAMETER_DECK)
            task_area = TaskWorkspace.create(
                root, "resume-compacted", objective_sha256="a" * 64,
                source_scope=["model.in"],
            )
            steps = [
                {
                    "index": index, "tool": "inspect_model", "status": "completed",
                    "arguments_digest": f"{index:064x}",
                    "result_digest": f"{index + 100:064x}",
                }
                for index in range(1, 11)
            ]
            task = TaskState(
                "Investigate model.in, preserve the selected basis, validate, and run it.",
                "model.in", ["inspect", "validate", "run"], status="clarify",
                engineering_assumptions=["Use SI units unless explicitly superseded."],
                missing_decisions=["Choose the crack-growth reporting basis."],
                user_decisions=[{
                    "decision_id": "decision-001", "question": "Choose unit system.",
                    "value": "SI", "turn": 1,
                }],
                steps=steps, step_count=10, max_steps=20,
                completed_steps=["inspect_model"] * 9 + ["validate_model"],
                validation_state={"errors": 0, "warnings": 0},
                failures=[{
                    "category": "missing_reference", "recovery_classification": "recoverable",
                    "tool": "find_references", "code": "not_found",
                    "message": "The first selector did not resolve.",
                }],
                recovery_count=1,
                working_plan=["inspect both cracks", "validate evidence", "run if authorized"],
                completion_criteria=["model_inspected", "validation_passed", "run_terminal_evidence"],
                remaining_criteria=["run_terminal_evidence"],
                active_source="model.in", active_source_digest="b" * 64,
                destination="final.in", last_created_output="final.in",
                authorization=TaskAuthorization(
                    mode="execution_when_explicitly_requested",
                    operations=["read", "execute"], source_scope=["model.in"],
                    destination_scope=["runs/model"], run_kinds=["full"],
                    max_executions=1, granted_turn=1, expires_after_turn=9,
                ),
                task_workspace={
                    "task_id": "resume-compacted",
                    "root": ".bsam-agent/tasks/resume-compacted",
                    "manifest": ".bsam-agent/tasks/resume-compacted/task-workspace.json",
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
            task.working_hypotheses = [{
                "hypothesis_id": "hypothesis-001",
                "statement": "The first crack definition controls the reported initiation site.",
                "status": "supported", "supporting_observation_ids": ["obs-001"],
                "refuting_observation_ids": [],
            }]
            session = root / ".bsam-agent" / "conversations" / "resume.json"
            agent.save_state(session)

            restored_state = ChatOrchestrator.load_state(session)
            restored = ChatOrchestrator(
                ScriptedProvider(), config(), LocalAgentApi(root), state=restored_state,
            )
            restored._append_task_observation(
                restored.state.task, "validate_model", {"source": "model.in"},
                {"source_set_sha256": "c" * 64, "summary": {"errors": 0}},
            )
            restored.save_state(session)
            twice_restored = ChatOrchestrator.load_state(session).task
            manifest = task_area.manifest()

        self.assertEqual("SI", twice_restored.user_decisions[0]["value"])
        self.assertEqual(task.authorization.as_dict(), twice_restored.authorization.as_dict())
        self.assertEqual(task.engineering_assumptions, twice_restored.engineering_assumptions)
        self.assertEqual(task.missing_decisions, twice_restored.missing_decisions)
        self.assertEqual(task.working_plan, twice_restored.working_plan)
        self.assertEqual(task.failures, twice_restored.failures)
        self.assertEqual(task.validation_state, twice_restored.validation_state)
        self.assertEqual(["run_terminal_evidence"], twice_restored.remaining_criteria)
        self.assertEqual(["obs-001"], twice_restored.working_hypotheses[0]["supporting_observation_ids"])
        self.assertEqual("obs-011", twice_restored.observations[-1]["observation_id"])
        self.assertEqual("obs-005", twice_restored.context_compaction["archived_observations"][-1]["observation_id"])
        self.assertEqual(11, len(manifest["artifacts"]))
        self.assertEqual((False, ["run_terminal_evidence"]), _task_completion(twice_restored))

    def test_parameter_change_chains_inspect_preview_confirm_apply_validate(self) -> None:
        provider = ScriptedProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(PARAMETER_DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))

            preview = agent.turn(
                "Change d_reduction in model.in to 0.4 and validate the resulting file."
            )
            before_confirmation = [item["tool"] for item in agent.state.task.steps]
            restored = ConversationState.from_dict(agent.state.as_dict())
            applied = agent.turn("/confirm")
            after_confirmation = [item["tool"] for item in agent.state.task.steps]
            output = (root / "model.changed.in").read_bytes()
            task_reference = agent.state.task.task_workspace
            task_manifest = json.loads(
                (root / task_reference["manifest"]).read_text(encoding="utf-8")
            )

        self.assertEqual(["inspect_model", "preview_parameter_change"], before_confirmation)
        self.assertTrue(preview.requires_confirmation)
        self.assertEqual("confirm", preview.phase)
        self.assertEqual("edits_with_confirmation", restored.task.authorization.mode)
        self.assertEqual("active", restored.task.authorization.status)
        self.assertIsNotNone(restored.task)
        self.assertEqual(before_confirmation, [item["tool"] for item in restored.task.steps])
        self.assertEqual(
            ["inspect_model", "preview_parameter_change", "apply_change", "validate_model"],
            after_confirmation,
        )
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual("consumed", agent.state.task.authorization.status)
        self.assertEqual(0, applied.tool_result["post_apply_validation"]["summary"]["errors"])
        self.assertIn(b"d_reduction=0.4", output)
        self.assertTrue(agent.state.last_plan.plan_path.startswith(
            f"{task_reference['root']}/plans/",
        ))
        self.assertIn(task_reference["root"], preview.message)
        self.assertEqual("promoted", task_manifest["state"])
        self.assertEqual("model.changed.in", task_manifest["promotions"][0]["destination"])
        self.assertEqual("promote_task_artifact", agent.state.task.observations[-1]["tool"])
        self.assertEqual(
            "model.changed.in",
            agent.state.task.observations[-1]["evidence"]["destination"],
        )
        self.assertEqual(
            {"observations", "plans", "variants"},
            {item["category"] for item in task_manifest["artifacts"]},
        )
        self.assertEqual([], provider.requests)

    def test_structural_rename_updates_dependents_and_validates(self) -> None:
        provider = ScriptedProvider(decision("preview_rename_entity", {
            "source": "model.in", "capability": "construct.boundary-conditions",
            "entity_name": "pull", "new_name": "fixed",
            "plan_path": "rename.json",
        }))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(RENAME_DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            preview = agent.turn(
                "Rename boundary condition pull to fixed in model.in, write renamed.in, "
                "and validate the result."
            )
            applied = agent.turn("/confirm")
            output = (root / "renamed.in").read_text(encoding="latin-1")

        self.assertTrue(preview.requires_confirmation)
        self.assertIn("name=fixed", output)
        self.assertIn("change=fixed", output)
        self.assertEqual(0, applied.tool_result["post_apply_validation"]["summary"]["errors"])
        self.assertEqual("complete", agent.state.task.status)
        self.assertIn("construct.boundary-conditions", agent.state.task.resolved_capabilities)

    def test_task_workspace_promotes_root_change_and_reuses_unchanged_include(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(PARAMETER_DECK.replace(
                b"*STOP\n", b"*INCLUDE,FILE=shared.inc\n",
            ))
            shared = root / "shared.inc"
            shared.write_bytes(b"*STOP\n")
            agent = ChatOrchestrator(ScriptedProvider(), config(), LocalAgentApi(root))

            preview = agent.turn(
                "Change d_reduction in model.in to 0.4, write final.in, and validate it."
            )
            applied = agent.turn("/confirm")
            manifest = json.loads(
                (root / agent.state.task.task_workspace["manifest"]).read_text(encoding="utf-8")
            )

            self.assertTrue(preview.requires_confirmation)
            self.assertEqual(0, applied.tool_result["post_apply_validation"]["summary"]["errors"])
            self.assertIn(b"d_reduction=0.4", (root / "final.in").read_bytes())
            self.assertEqual(b"*STOP\n", shared.read_bytes())
            self.assertEqual(["shared.inc"], manifest["promotions"][0]["reused_outputs"])

    def test_stale_revision_stops_and_identical_failure_is_not_repeated(self) -> None:
        provider = ScriptedProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            source.write_bytes(PARAMETER_DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            agent.turn("Change d_reduction in model.in to 0.4 and validate it.")
            source.write_bytes(PARAMETER_DECK + b"** external change\n")

            stale = agent.turn("/confirm")
            agent.turn("Apply that reviewed change.")
            repeated = agent.turn("/confirm")

        self.assertEqual("invalid_arguments", stale.error_code)
        self.assertIn("stale plan was not applied", stale.message)
        self.assertEqual("stale_revision", agent.state.task.failures[0]["category"])
        self.assertEqual("repeated_failed_action", repeated.error_code)
        self.assertFalse((root / "model.changed.in").exists())

    def test_stale_parameter_plan_can_be_safely_repreviewed_and_reconfirmed(self) -> None:
        provider = ScriptedProvider()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            source.write_bytes(PARAMETER_DECK)
            agent = ChatOrchestrator(provider, config(), LocalAgentApi(root))
            agent.turn(
                "Change d_reduction in model.in to 0.4, write revised.in, and validate it."
            )
            old_plan = agent.state.last_plan.plan_path
            source.write_bytes(PARAMETER_DECK + b"** unrelated external change\n")
            stale = agent.turn("/confirm")

            refreshed = agent.turn("Refresh the stale plan.")
            new_plan = agent.state.last_plan.plan_path
            completed = agent.turn("/confirm")
            output = (root / "revised.in").read_bytes()
            task_root = agent.state.task.task_workspace["root"]

        self.assertEqual("invalid_arguments", stale.error_code)
        self.assertEqual("preview_refresh_change", refreshed.tool)
        self.assertTrue(refreshed.requires_confirmation)
        self.assertNotEqual(old_plan, new_plan)
        self.assertTrue(old_plan.startswith(f"{task_root}/plans/"))
        self.assertTrue(new_plan.startswith(f"{task_root}/retries/"))
        self.assertEqual("revised.in", agent.state.task.last_created_output)
        self.assertEqual(1, agent.state.task.recovery_count)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual(0, completed.tool_result["post_apply_validation"]["summary"]["errors"])
        self.assertIn(b"d_reduction=0.4", output)
        self.assertIn(b"unrelated external change", output)
        self.assertEqual([], provider.responses)

    def test_failed_run_records_structured_failure_without_recovery_loop(self) -> None:
        provider = ScriptedProvider(decision("run_bsam", {
            "source": "model.in", "output_dir": "runs/case",
            "executable": "bsam20.exe", "confirm": False,
        }))
        agent = ChatOrchestrator(provider, config(), FailedRunApi())  # type: ignore[arg-type]
        result = agent.turn("Run model.in in runs/case and verify whether it succeeds.")

        self.assertFalse(result.requires_confirmation)
        self.assertEqual("run_bsam", result.tool)
        self.assertEqual("failed", agent.state.task.status)
        self.assertEqual("execution_input_failure", agent.state.task.failures[0]["category"])
        self.assertIn("no engineering values were changed", result.message)
        self.assertEqual(0, agent.state.task.recovery_count)
        self.assertEqual(1, len(agent.state.task.steps))


if __name__ == "__main__":
    unittest.main()
