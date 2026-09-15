from __future__ import annotations

import sys
import tempfile
import unittest
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.chat import run_jsonl_chat, run_terminal_chat, task_view_snapshot
from bsam_agent.cli import build_parser, main
from bsam_agent.orchestrator import TaskState


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
    def test_task_view_snapshot_projects_bounded_activity_and_evidence(self) -> None:
        task = TaskState(
            "Investigate model.in", "model.in", ["inspect"], status="blocked",
            engineering_assumptions=["Treat the checked-in deck as the active source."],
            user_decisions=[{
                "decision_id": "decision-001", "question": "Choose units.",
                "value": "SI", "turn": 2,
            }],
            working_plan=["Inspect the model", "Follow references"],
            working_hypotheses=[{
                "hypothesis_id": "hypothesis-001", "statement": "A reference may be stale.",
                "status": "open", "supporting_observation_ids": ["obs-001"],
                "refuting_observation_ids": [],
            }],
            steps=[{
                "index": 1, "tool": "inspect_model", "status": "completed",
                "arguments_digest": "A" * 64, "result_digest": "B" * 64,
            }],
            observations=[{
                "observation_id": "obs-001", "index": 1, "tool": "inspect_model",
                "status": "completed", "result_digest": "B" * 64,
                "evidence": {
                    "summary": {"errors": 0, "warnings": 1},
                    "workspace_matches": [{"path": "private.md", "text": "private"}],
                },
            }],
            completion_criteria=["model_inspected", "references_inspected"],
            remaining_criteria=["references_inspected"], step_count=1,
            context_compaction={
                "schema_version": "0.1.0", "compaction_count": 2,
                "compacted_through_step": 4,
                "archived_observations": [{
                    "observation_id": "obs-000", "index": 4, "tool": "query_model",
                    "status": "completed", "result_digest": "C" * 64,
                    "artifact": ".bsam-agent/tasks/example/observations/obs-000.json",
                    "evidence_summary": {},
                }],
            },
            terminal_reason="evidence_exhausted",
        )

        snapshot = task_view_snapshot(task)

        self.assertEqual("Investigate model.in", snapshot["objective"])
        self.assertEqual("inspect_model", snapshot["activity"][0]["tool"])
        self.assertEqual("obs-001", snapshot["evidence"][0]["id"])
        self.assertEqual(
            {"errors": 0, "warnings": 1}, snapshot["evidence"][0]["details"]["summary"],
        )
        self.assertEqual(1, snapshot["evidence"][0]["details"]["workspace_match_count"])
        self.assertNotIn("workspace_matches", snapshot["evidence"][0]["details"])
        self.assertEqual("SI", snapshot["decisions"][0]["value"])
        self.assertEqual(2, snapshot["compaction"]["count"])
        self.assertEqual("read_only", snapshot["authorization"]["mode"])
        self.assertIsNone(snapshot["task_workspace"])
        self.assertEqual("evidence_exhausted", snapshot["terminal_reason"])

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
        self.assertIsNone(records[0]["task"])
        self.assertEqual("turn", records[1]["type"])
        self.assertEqual("Inspection completed.", records[1]["turn"]["message"])
        self.assertIsNone(records[1]["task"])
        self.assertEqual("error", records[2]["type"])
        self.assertEqual("closed", records[3]["type"])

    def test_jsonl_startup_failure_is_one_protocol_error(self) -> None:
        output = io.StringIO()
        with patch("bsam_agent.cli.run_jsonl_chat", side_effect=PermissionError("blocked")):
            with redirect_stdout(output):
                status = main([
                    "chat", "--workspace-root", ".", "--config", "provider.json", "--jsonl",
                ])
        records = output.getvalue().splitlines()
        self.assertEqual(2, status)
        self.assertEqual(1, len(records))
        self.assertEqual({"message": "blocked", "type": "error"}, json.loads(records[0]))


if __name__ == "__main__":
    unittest.main()
