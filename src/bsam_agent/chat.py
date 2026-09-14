"""Minimal interactive terminal client for the local chat orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, TextIO

from .api import LocalAgentApi
from .orchestrator import ChatOrchestrator
from .provider import load_provider_config
from .provider_factory import create_provider


def run_terminal_chat(
    config_path: Path,
    workspace_root: Path,
    *,
    audit_enabled: bool = True,
    session_path: Path | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    root = workspace_root.resolve()
    config = load_provider_config(config_path)
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
) -> int:
    """Serve one guarded chat session over newline-delimited JSON for local UI clients."""
    root = workspace_root.resolve()
    config = load_provider_config(config_path)
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
        "workspace": str(root),
        "conversation_id": agent.state.conversation_id,
        "phase": agent.state.phase,
        "pending_confirmation": agent.state.pending_action is not None,
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
            emit({"type": "turn", "turn": turn.as_dict()})
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            emit({"type": "error", "message": str(exc)})
    return 0
