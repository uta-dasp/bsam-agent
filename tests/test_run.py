from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent import cli
from bsam_agent.run import (
    RunError,
    _process_is_running,
    classify_run,
    request_run_stop,
    run_bsam,
    run_status,
)


RUNNABLE_DECK = (
    b"INPUT\n3\nEND INPUT\n"
    b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
    b"MATERIALS\n0\nEND MATERIALS\n"
    b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
)


class RunSupervisorTests(unittest.TestCase):
    def test_success_requires_sentinel_zero_exit_and_no_fatal_marker(self) -> None:
        success = classify_run(0, "work complete\n----- END OF PROGRAM ------\n")
        self.assertEqual("succeeded", success["classification"])
        self.assertTrue(success["success_sentinel_seen"])

        no_sentinel = classify_run(0, "work stopped early")
        self.assertEqual("unknown", no_sentinel["classification"])

        fatal = classify_run(0, "ERROR: MATERIALS input block required")
        self.assertEqual("failed", fatal["classification"])

        late_stop = classify_run(
            0,
            "work complete\n----- END OF PROGRAM ------\n",
            stop_requested=True,
        )
        self.assertEqual("succeeded", late_stop["classification"])

    def test_timeout_classifies_as_stopped(self) -> None:
        result = classify_run(0, "", stop_requested=True)
        self.assertEqual("stopped", result["classification"])

    def test_status_reads_terminal_manifest_without_mutating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            output.mkdir()
            manifest = {
                "schema_version": "1.0.0",
                "state": "terminal",
                "classification": "succeeded",
                "deck": str((Path(directory) / "model.in").resolve()),
                "output_directory": str(output.resolve()),
                "process_id": 123,
            }
            manifest_path = output / "run-manifest.json"
            original = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            manifest_path.write_text(original, encoding="utf-8")

            status = run_status(output)

            self.assertEqual("terminal", status["state"])
            self.assertEqual("succeeded", status["classification"])
            self.assertIsNone(status["process_running"])
            self.assertIn("run-manifest.json", status["artifacts"])
            self.assertEqual(original, manifest_path.read_text(encoding="utf-8"))

    def test_stop_is_controlled_audited_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            output.mkdir()
            deck = Path(directory) / "model.in"
            manifest = {
                "schema_version": "1.0.0",
                "state": "running",
                "classification": "pending",
                "deck": str(deck.resolve()),
                "deck_sha256": "A" * 64,
                "output_directory": str(output.resolve()),
                "process_id": os.getpid(),
            }
            (output / "run-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (output / "model.exit").write_text(
                "           0\r\n Ext_flag=0 (continue) and =1(exit) and =2(stop)\r\n",
                encoding="ascii",
            )

            first = request_run_stop(output)
            request_bytes = (output / "stop-request.json").read_bytes()
            second = request_run_stop(output)
            status = run_status(output)

            self.assertFalse(first["already_requested"])
            self.assertTrue(second["already_requested"])
            self.assertEqual(request_bytes, (output / "stop-request.json").read_bytes())
            self.assertEqual(b"2\n", (output / "model.exit").read_bytes())
            self.assertEqual("user", status["stop_request"]["reason"])
            self.assertTrue(status["process_running"])

            manifest["state"] = "terminal"
            (output / "run-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (output / "model.exit").write_text("terminal contents", encoding="ascii")
            terminal = request_run_stop(output)
            self.assertTrue(terminal["already_requested"])
            self.assertEqual("terminal", terminal["state"])
            self.assertEqual(
                "terminal contents",
                (output / "model.exit").read_text(encoding="ascii"),
            )

    def test_stop_rejects_terminal_run_and_mismatched_manifest_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            output.mkdir()
            manifest = {
                "state": "terminal",
                "deck": str((Path(directory) / "model.in").resolve()),
                "output_directory": str(output.resolve()),
            }
            manifest_path = output / "run-manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RunError, "already terminal"):
                request_run_stop(output)

            manifest["output_directory"] = str((Path(directory) / "other").resolve())
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RunError, "does not match"):
                run_status(output)

    def test_current_process_liveness_is_detected(self) -> None:
        self.assertTrue(_process_is_running(os.getpid()))

    def test_supervisor_reasserts_stop_requested_during_startup(self) -> None:
        class FakeProcess:
            def __init__(self, command, cwd, **_kwargs):
                self.pid = os.getpid()
                self.output = Path(cwd)
                manifest = json.loads(
                    (self.output / "run-manifest.json").read_text(encoding="utf-8")
                )
                request = {
                    "schema_version": "1.0.0",
                    "requested_at": "2026-08-31T00:00:00+00:00",
                    "reason": "user",
                    "output_directory": manifest["output_directory"],
                    "deck": manifest["deck"],
                    "deck_sha256": manifest["deck_sha256"],
                    "process_id": None,
                }
                (self.output / "stop-request.json").write_text(
                    json.dumps(request), encoding="utf-8"
                )
                # Simulate BSAM initializing its normal control file after the
                # early request was recorded.
                (self.output / "model.exit").write_text(
                    "           0\r\n Ext_flag=0 (continue) and =2(stop)\r\n",
                    encoding="ascii",
                )

            def poll(self):
                return 0 if (self.output / "model.exit").read_bytes() == b"2\n" else None

            def wait(self, timeout=None):
                result = self.poll()
                if result is None:
                    raise subprocess.TimeoutExpired("fake", timeout)
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "model.in"
            executable = root / "bsam20.exe"
            output = root / "run"
            deck.write_bytes(RUNNABLE_DECK)
            executable.write_bytes(b"fake")
            registry = {"target": {"executable_sha256": "A" * 64}}
            with (
                patch("bsam_agent.run.load_registry", return_value=registry),
                patch("bsam_agent.run._sha256", return_value="A" * 64),
                patch("bsam_agent.run.subprocess.Popen", FakeProcess),
            ):
                result = run_bsam(deck, output, executable, timeout_seconds=10)

            self.assertEqual("stopped", result["classification"])
            self.assertEqual(64, len(result["source_set_sha256"]))
            self.assertEqual(1, len(result["source_files"]))
            self.assertEqual("user", result["stop_reason"])
            self.assertFalse(result["timed_out"])
            self.assertFalse(result["stop_escalated"])
            self.assertEqual(b"2\n", (output / "model.exit").read_bytes())

    def test_supervisor_fails_closed_and_terminates_on_invalid_stop_record(self) -> None:
        class FakeProcess:
            terminated = False

            def __init__(self, command, cwd, **_kwargs):
                self.pid = os.getpid()
                self.output = Path(cwd)
                (self.output / "stop-request.json").write_text("{", encoding="utf-8")

            def poll(self):
                return 1 if self.terminated else None

            def terminate(self):
                type(self).terminated = True

            def kill(self):
                type(self).terminated = True

            def wait(self, timeout=None):
                if self.terminated:
                    return 1
                raise subprocess.TimeoutExpired("fake", timeout)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "model.in"
            executable = root / "bsam20.exe"
            output = root / "run"
            deck.write_bytes(RUNNABLE_DECK)
            executable.write_bytes(b"fake")
            registry = {"target": {"executable_sha256": "A" * 64}}
            with (
                patch("bsam_agent.run.load_registry", return_value=registry),
                patch("bsam_agent.run._sha256", return_value="A" * 64),
                patch("bsam_agent.run.subprocess.Popen", FakeProcess),
            ):
                with self.assertRaisesRegex(RunError, "cannot read stop request"):
                    run_bsam(deck, output, executable, timeout_seconds=10)

            manifest = json.loads(
                (output / "run-manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(FakeProcess.terminated)
            self.assertEqual("terminal", manifest["state"])
            self.assertEqual("failed", manifest["classification"])

    def test_status_cli_returns_manifest_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            output.mkdir()
            manifest = {
                "state": "terminal",
                "classification": "failed",
                "deck": str((Path(directory) / "model.in").resolve()),
                "output_directory": str(output.resolve()),
            }
            (output / "run-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = cli.main(["status", str(output), "--compact"])
            value = json.loads(stdout.getvalue())
            self.assertEqual(0, result)
            self.assertEqual("terminal", value["state"])
            self.assertEqual("failed", value["classification"])

    def test_executable_mismatch_fails_before_output_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "model.in"
            executable = root / "not-bsam.exe"
            output = root / "output"
            deck.write_text("INPUT\n3\n", encoding="ascii")
            executable.write_bytes(b"not the pinned executable")
            with self.assertRaisesRegex(RunError, "fingerprint mismatch"):
                run_bsam(deck, output, executable)
            self.assertFalse(output.exists())

    def test_missing_include_blocks_run_before_output_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "model.in"
            executable = root / "bsam20.exe"
            output = root / "output"
            deck.write_bytes(RUNNABLE_DECK.replace(
                b"*STOP\n",
                b"*INCLUDE, FILE=missing.inc\n*STOP\n",
            ))
            executable.write_bytes(b"fake")
            registry = {"target": {"executable_sha256": "A" * 64}}
            with (
                patch("bsam_agent.run.load_registry", return_value=registry),
                patch("bsam_agent.run._sha256", return_value="A" * 64),
            ):
                with self.assertRaisesRegex(RunError, "include target was not found"):
                    run_bsam(deck, output, executable)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
