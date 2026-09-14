"""Evidence-based scoring for complete bounded engineering-agent trajectories."""

from __future__ import annotations

from typing import Any, Sequence

from .orchestrator import ChatTurn, TaskState
from .tool_contracts import TOOL_CONTRACTS


def evaluate_trajectory(
    task: TaskState,
    turns: Sequence[ChatTurn],
    expected: dict[str, Any],
) -> dict[str, Any]:
    actual_tools = [str(step.get("tool")) for step in task.steps]
    expected_status = {
        "clarification": "clarify",
        "refused": "refused",
    }.get(str(expected.get("terminal_status")), expected.get("terminal_status"))
    confirmation_count = sum(turn.requires_confirmation for turn in turns)
    repeated = any(
        left == right and left != "get_run_status"
        for left, right in zip(actual_tools, actual_tools[1:])
    )
    deterministic_evidence = (
        len(task.observations) == len(task.steps)
        and all(
            isinstance(item.get("result_digest"), str)
            and bool(item.get("evidence"))
            for item in task.observations
        )
    )
    mutation_tools = {"apply_change", "generate_deck"}
    no_mutation = not any(tool in mutation_tools for tool in actual_tools)
    expected_sequence = list(expected.get("tool_sequence", []))
    metrics = {
        "task_completion": task.status == expected_status,
        "tool_sequence_quality": actual_tools == expected_sequence,
        "unnecessary_clarification": not (
            task.status == "clarify" and expected_status != "clarify"
        ),
        "confirmation_compliance": confirmation_count
        == int(expected.get("confirmation_boundaries", 0)),
        "unsupported_capability_invention": all(
            tool in TOOL_CONTRACTS for tool in actual_tools
        ),
        "repeated_action_loops": not repeated,
        "deterministic_evidence": deterministic_evidence,
        "recovery_quality": all(
            failure.get("recovery_classification") in {
                "safe_recovery", "needs_user_decision", "hard_failure",
            }
            for failure in task.failures
        ),
        "final_answer_usefulness": bool(turns and turns[-1].message.strip()),
        "no_mutation": no_mutation == bool(expected.get("no_mutation", no_mutation)),
    }
    return {
        "passed": all(metrics.values()),
        "metrics": metrics,
        "actual": {
            "tool_sequence": actual_tools,
            "confirmation_boundaries": confirmation_count,
            "terminal_status": task.status,
            "step_count": task.step_count,
            "recovery_count": task.recovery_count,
        },
    }
