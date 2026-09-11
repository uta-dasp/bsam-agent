from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import LocalAgentApi
from bsam_agent.orchestrator import ChatOrchestrator, ConversationState
from bsam_agent.provider import ProviderConfig, ProviderResponse, Usage


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


class TaskTrajectoryTests(unittest.TestCase):
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
        self.assertEqual([], provider.requests)

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

        self.assertEqual(["inspect_model", "preview_parameter_change"], before_confirmation)
        self.assertTrue(preview.requires_confirmation)
        self.assertEqual("confirm", preview.phase)
        self.assertIsNotNone(restored.task)
        self.assertEqual(before_confirmation, [item["tool"] for item in restored.task.steps])
        self.assertEqual(
            ["inspect_model", "preview_parameter_change", "apply_change", "validate_model"],
            after_confirmation,
        )
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual(0, applied.tool_result["post_apply_validation"]["summary"]["errors"])
        self.assertIn(b"d_reduction=0.4", output)
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
            agent.turn("Change d_reduction in model.in to 0.4 and validate it.")
            old_plan = agent.state.last_plan.plan_path
            source.write_bytes(PARAMETER_DECK + b"** unrelated external change\n")
            stale = agent.turn("/confirm")

            refreshed = agent.turn("Refresh the stale plan.")
            new_plan = agent.state.last_plan.plan_path
            completed = agent.turn("/confirm")
            output = (root / "model.changed.in").read_bytes()

        self.assertEqual("invalid_arguments", stale.error_code)
        self.assertEqual("preview_refresh_change", refreshed.tool)
        self.assertTrue(refreshed.requires_confirmation)
        self.assertNotEqual(old_plan, new_plan)
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
        pending = agent.turn("Run model.in in runs/case and verify whether it succeeds.")
        result = agent.turn("/confirm")

        self.assertTrue(pending.requires_confirmation)
        self.assertEqual("run_bsam", result.tool)
        self.assertEqual("failed", agent.state.task.status)
        self.assertEqual("execution_input_failure", agent.state.task.failures[0]["category"])
        self.assertIn("no engineering values were changed", result.message)
        self.assertEqual(0, agent.state.task.recovery_count)
        self.assertEqual(1, len(agent.state.task.steps))


if __name__ == "__main__":
    unittest.main()
