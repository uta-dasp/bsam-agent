"""Minimal interactive terminal client for the local chat orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .api import LocalAgentApi
from .local_provider import LlamaCppProvider
from .orchestrator import ChatOrchestrator
from .provider import load_provider_config


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
    provider = LlamaCppProvider(config)
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
