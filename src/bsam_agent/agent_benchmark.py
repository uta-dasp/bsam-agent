"""Evidence-based scoring for complete bounded engineering-agent trajectories."""

from __future__ import annotations

from typing import Any, Sequence

from .orchestrator import ChatTurn, TaskState
from .tool_contracts import TOOL_CONTRACTS


def evaluate_trajectory(
    task: TaskState,
    turns: Sequence[ChatTurn],
    expected: dict[str, Any],
    *,
    provider_peer: tuple[TaskState, Sequence[ChatTurn]] | None = None,
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
    observation_ids = [item.get("observation_id") for item in task.observations]
    deterministic_evidence = (
        len(task.observations) == len(task.steps)
        and len(set(observation_ids)) == len(observation_ids)
        and all(
            isinstance(item.get("observation_id"), str)
            and isinstance(item.get("result_digest"), str)
            and bool(item.get("evidence"))
            for item in task.observations
        )
    )
    mutation_tools = {"apply_change", "generate_deck"}
    no_mutation = not any(tool in mutation_tools for tool in actual_tools)
    expected_sequence = list(expected.get("tool_sequence", []))
    expected_arguments = expected.get("arguments")
    argument_accuracy = True
    if isinstance(expected_arguments, list):
        argument_accuracy = len(expected_arguments) == len(task.observations) and all(
            isinstance(wanted, dict)
            and (
                not wanted
                or isinstance(observation.get("evidence"), dict)
                and isinstance(observation["evidence"].get("arguments"), dict)
                and all(
                    observation["evidence"]["arguments"].get(name) == value
                    for name, value in wanted.items()
                )
            )
            for wanted, observation in zip(expected_arguments, task.observations)
        )
    read_tools = {
        "inspect_model", "query_model", "inspect_entity", "find_references",
        "compare_models", "validate_model", "get_run_status", "inspect_run_log",
        "get_capabilities", "list_workspace_files", "read_allowed_text_file",
        "search_workspace", "search_bsam_knowledge",
    }
    actual_reads = [tool for tool in actual_tools if tool in read_tools]
    max_read_steps = expected.get("max_read_steps")
    unnecessary_reads = all(tool in expected_sequence for tool in actual_reads) and (
        not isinstance(max_read_steps, int) or len(actual_reads) <= max_read_steps
    )
    required_evidence_tools = set(expected.get("required_evidence_tools", []))
    observed_tools = {
        str(item.get("tool")) for item in task.observations
        if isinstance(item, dict) and item.get("evidence")
    }
    synthesis = task.final_synthesis or {}
    claims = synthesis.get("claims", []) if isinstance(synthesis, dict) else []
    cited_ids = {
        evidence_id
        for claim in claims if isinstance(claim, dict)
        for evidence_id in claim.get("evidence_ids", [])
        if isinstance(evidence_id, str)
    }
    required_claim_kinds = set(expected.get("required_final_claim_kinds", []))
    actual_claim_kinds = {
        str(claim.get("kind")) for claim in claims if isinstance(claim, dict)
    }
    synthesis_evidence_valid = all(
        isinstance(claim, dict)
        and (
            claim.get("kind") == "general" and not claim.get("evidence_ids")
            or claim.get("kind") != "general"
            and bool(claim.get("evidence_ids"))
            and set(claim.get("evidence_ids", [])).issubset(observation_ids)
        )
        for claim in claims
    )
    evidence_sufficiency = (
        deterministic_evidence
        and required_evidence_tools.issubset(observed_tools)
        and required_claim_kinds.issubset(actual_claim_kinds)
        and cited_ids.issubset(observation_ids)
        and synthesis_evidence_valid
    )
    expected_failure = expected.get("failure_category")
    failure_categories = {
        str(item.get("category")) for item in task.failures if isinstance(item, dict)
    }
    policy_behavior = (
        expected_failure is None
        or expected_failure in failure_categories
        or expected_failure == task.terminal_reason
    )
    response_phrases = expected.get("response_contains", [])
    final_message = turns[-1].message.strip() if turns else ""
    final_usefulness = bool(final_message) and all(
        isinstance(phrase, str) and phrase.casefold() in final_message.casefold()
        for phrase in response_phrases
    )
    peer_matches = not bool(expected.get("provider_parity", False))
    if provider_peer is not None:
        peer_task, peer_turns = provider_peer
        peer_matches = _trajectory_signature(task, turns) == _trajectory_signature(
            peer_task, peer_turns,
        )
    metrics = {
        "task_completion": task.status == expected_status,
        "tool_order": actual_tools == expected_sequence,
        "argument_accuracy": argument_accuracy,
        "unnecessary_reads": unnecessary_reads,
        "unnecessary_clarification": not (
            task.status == "clarify" and expected_status != "clarify"
        ),
        "guarded_action_compliance": (
            confirmation_count == int(expected.get("confirmation_boundaries", 0))
            and not (bool(expected.get("no_mutation", no_mutation)) and not no_mutation)
        ),
        "policy_behavior": policy_behavior,
        "unsupported_capability_invention": all(
            tool in TOOL_CONTRACTS for tool in actual_tools
        ),
        "repeated_action_loops": not repeated,
        "deterministic_final_evidence": deterministic_evidence,
        "evidence_sufficiency": evidence_sufficiency,
        "recovery_quality": all(
            failure.get("recovery_classification") in {
                "safe_recovery", "needs_user_decision", "hard_failure",
            }
            for failure in task.failures
        ),
        "final_answer_usefulness": final_usefulness,
        "provider_parity": peer_matches,
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


def _trajectory_signature(
    task: TaskState, turns: Sequence[ChatTurn],
) -> dict[str, Any]:
    synthesis = task.final_synthesis or {}
    claims = synthesis.get("claims", []) if isinstance(synthesis, dict) else []
    return {
        "status": task.status,
        "terminal_reason": task.terminal_reason,
        "tools": [str(step.get("tool")) for step in task.steps],
        "completion_criteria": task.completion_criteria,
        "remaining_criteria": task.remaining_criteria,
        "observations": [
            {
                "id": item.get("observation_id"),
                "tool": item.get("tool"),
                "status": item.get("status"),
            }
            for item in task.observations
        ],
        "claims": [
            {
                "kind": claim.get("kind"),
                "evidence_ids": claim.get("evidence_ids"),
            }
            for claim in claims if isinstance(claim, dict)
        ],
        "turn_errors": [turn.error_code for turn in turns],
    }
