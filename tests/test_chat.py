from __future__ import annotations

import sys
import tempfile
import unittest
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.chat import run_jsonl_chat, run_terminal_chat
from bsam_agent.cli import build_parser


class _Turn:
    message = "Inspection completed."
    tool_result = {"source_diff": "--- old\n+++ new"}

    def as_dict(self) -> dict[str, object]:
        return {
            "conversation_id": "conversation",
            "phase": "inspect",
            "message": self.message,
            "tool": "inspect_model",
            "tool_result": self.tool_result,
            "requires_confirmation": False,
            "error_code": None,
        }


class _Agent:
    def __init__(self, *_args, **_kwargs) -> None:
        self.inputs: list[str] = []
        self.state = SimpleNamespace(
            conversation_id="conversation", phase="understand", pending_action=None,
        )

    def turn(self, text: str) -> _Turn:
        self.inputs.append(text)
        return _Turn()


class ChatClientTests(unittest.TestCase):
    def test_chat_parser_binds_workspace_model_config_and_audit_opt_out(self) -> None:
        args = build_parser().parse_args([
            "chat", "--workspace-root", "project", "--config", "provider.json", "--no-audit",
            "--session", ".bsam-agent/session.json",
        ])
        self.assertEqual("chat", args.command)
        self.assertTrue(args.no_audit)
        self.assertEqual(".bsam-agent/session.json", args.session)
        self.assertFalse(args.jsonl)
        jsonl_args = build_parser().parse_args([
            "chat", "--workspace-root", "project", "--jsonl",
        ])
        self.assertTrue(jsonl_args.jsonl)

    def test_scripted_terminal_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider_path = root / "provider.json"
            provider_path.write_text(
                '{"provider":"cpu-local","model":"test","endpoint":"http://127.0.0.1:18080"}',
                encoding="utf-8",
            )
            answers = iter(["Inspect model.in", "/quit"])
            output: list[str] = []
            with patch("bsam_agent.chat.ChatOrchestrator", _Agent):
                status = run_terminal_chat(
                    provider_path, root, audit_enabled=False,
                    input_fn=lambda _prompt: next(answers), output_fn=output.append,
                )
        self.assertEqual(0, status)
        self.assertTrue(any("Inspection completed" in line for line in output))
        self.assertTrue(any("+++ new" in line for line in output))

    def test_jsonl_chat_emits_ready_turn_and_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider_path = root / "provider.json"
            provider_path.write_text(
                '{"provider":"cpu-local","model":"test","endpoint":"http://127.0.0.1:18080"}',
                encoding="utf-8",
            )
            inputs = io.StringIO(
                '{"type":"turn","text":"Inspect model.in"}\n'
                '{"type":"invalid","text":"ignored"}\n'
                '{"type":"turn","text":"/quit"}\n'
            )
            output = io.StringIO()
            with patch("bsam_agent.chat.ChatOrchestrator", _Agent):
                status = run_jsonl_chat(
                    provider_path, root, audit_enabled=False,
                    input_stream=inputs, output_stream=output,
                )
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(0, status)
        self.assertEqual("ready", records[0]["type"])
        self.assertEqual("turn", records[1]["type"])
        self.assertEqual("Inspection completed.", records[1]["turn"]["message"])
        self.assertEqual("error", records[2]["type"])
        self.assertEqual("closed", records[3]["type"])


if __name__ == "__main__":
    unittest.main()
