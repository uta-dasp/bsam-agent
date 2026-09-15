"""Minimal interactive terminal client for the local chat orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, TextIO

from .api import LocalAgentApi
from .orchestrator import ChatOrchestrator, TaskState
from .provider import load_provider_config, override_provider_config
from .provider_factory import create_provider


def task_view_snapshot(task: TaskState | None) -> dict[str, object] | None:
    """Return a bounded local-UI projection of durable engineering-task state."""
    if task is None:
        return None
    activity = [
        {
            "index": item.get("index"),
            "tool": item.get("tool"),
            "status": item.get("status"),
        }
        for item in task.steps[-task.max_steps:]
        if isinstance(item, dict)
    ]
    evidence = []
    for observation in task.observations[-task.max_steps:]:
        if not isinstance(observation, dict):
            continue
        value = observation.get("evidence")
        details: dict[str, object] = {}
        if isinstance(value, dict):
            for name in (
                "summary", "match_count", "state", "classification", "differences",
                "validation",
            ):
                if name in value:
                    details[name] = value[name]
            if isinstance(value.get("workspace_matches"), list):
                details["workspace_match_count"] = len(value["workspace_matches"])
            if isinstance(value.get("workspace_files"), list):
                details["workspace_file_count"] = len(value["workspace_files"])
        evidence.append({
            "id": observation.get("observation_id"),
            "index": observation.get("index"),
            "tool": observation.get("tool"),
            "status": observation.get("status"),
            "result_digest": observation.get("result_digest"),
            "details": details,
        })
    hypotheses = [
        {
            "id": item.get("hypothesis_id"),
            "statement": item.get("statement"),
            "status": item.get("status"),
            "supporting_evidence": item.get("supporting_observation_ids", []),
            "refuting_evidence": item.get("refuting_observation_ids", []),
        }
        for item in task.working_hypotheses
        if isinstance(item, dict)
    ]
    return {
        "objective": task.objective,
        "status": task.status,
        "plan": task.working_plan,
        "activity": activity,
        "evidence": evidence,
        "assumptions": task.engineering_assumptions,
        "hypotheses": hypotheses,
        "completion_criteria": task.completion_criteria,
        "remaining_criteria": task.remaining_criteria,
        "terminal_reason": task.terminal_reason,
    }


def run_terminal_chat(
    config_path: Path,
    workspace_root: Path,
    *,
    audit_enabled: bool = True,
    session_path: Path | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    provider_name: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> int:
    root = workspace_root.resolve()
    config = override_provider_config(
        load_provider_config(config_path), provider=provider_name, model=model,
        reasoning_effort=reasoning_effort,
    )
    provider = create_provider(config)
    audit_directory = root / ".bsam-agent" / "audit" if audit_enabled else None
    state = ChatOrchestrator.load_state(session_path) if session_path and session_path.is_file() else None
    agent = ChatOrchestrator(
        provider, config, LocalAgentApi(root), audit_directory=audit_directory, state=state
    )
    output_fn(
        f"BSAM Agent chat ({config.model}). Workspace: {root}\n"
        "Commands: /confirm, /cancel, /quit"
    )
    while True:
        try:
            text = input_fn("bsam> ").strip()
        except (EOFError, KeyboardInterrupt):
            output_fn("\nChat ended.")
            return 0
        if text.casefold() in {"/quit", "/exit"}:
            output_fn("Chat ended.")
            return 0
        turn = agent.turn(text)
        if session_path is not None:
            agent.save_state(session_path)
        output_fn(turn.message)
        if turn.tool_result and isinstance(turn.tool_result.get("source_diff"), str):
            output_fn(turn.tool_result["source_diff"])


def run_jsonl_chat(
    config_path: Path,
    workspace_root: Path,
    *,
    audit_enabled: bool = True,
    session_path: Path | None = None,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    provider_name: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> int:
    """Serve one guarded chat session over newline-delimited JSON for local UI clients."""
    root = workspace_root.resolve()
    config = override_provider_config(
        load_provider_config(config_path), provider=provider_name, model=model,
        reasoning_effort=reasoning_effort,
    )
    provider = create_provider(config)
    audit_directory = root / ".bsam-agent" / "audit" if audit_enabled else None
    state = ChatOrchestrator.load_state(session_path) if session_path and session_path.is_file() else None
    agent = ChatOrchestrator(
        provider, config, LocalAgentApi(root), audit_directory=audit_directory, state=state
    )

    def emit(value: dict[str, object]) -> None:
        output_stream.write(json.dumps(value, separators=(",", ":")) + "\n")
        output_stream.flush()

    emit({
        "type": "ready",
        "model": config.model,
        "provider": config.provider,
        "reasoning_effort": config.reasoning_effort,
        "workspace": str(root),
        "conversation_id": agent.state.conversation_id,
        "phase": agent.state.phase,
        "pending_confirmation": agent.state.pending_action is not None,
        "task": task_view_snapshot(getattr(agent.state, "task", None)),
    })
    for raw_line in input_stream:
        try:
            request = json.loads(raw_line)
            if not isinstance(request, dict) or set(request) != {"type", "text"}:
                raise ValueError("request must contain exactly type and text")
            if request["type"] != "turn" or not isinstance(request["text"], str):
                raise ValueError("request must be a turn with string text")
            if request["text"].strip().casefold() in {"/quit", "/exit"}:
                emit({"type": "closed", "message": "Chat ended."})
                return 0
            turn = agent.turn(request["text"])
            if session_path is not None:
                agent.save_state(session_path)
            emit({
                "type": "turn", "turn": turn.as_dict(),
                "task": task_view_snapshot(getattr(agent.state, "task", None)),
            })
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            emit({"type": "error", "message": str(exc)})
    return 0
