from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.run import RunError, classify_run, run_bsam


class RunSupervisorTests(unittest.TestCase):
    def test_success_requires_sentinel_zero_exit_and_no_fatal_marker(self) -> None:
        success = classify_run(0, "work complete\n----- END OF PROGRAM ------\n")
        self.assertEqual("succeeded", success["classification"])
        self.assertTrue(success["success_sentinel_seen"])

        no_sentinel = classify_run(0, "work stopped early")
        self.assertEqual("unknown", no_sentinel["classification"])

        fatal = classify_run(0, "ERROR: MATERIALS input block required")
        self.assertEqual("failed", fatal["classification"])

    def test_timeout_classifies_as_stopped(self) -> None:
        result = classify_run(0, "", stop_requested=True)
        self.assertEqual("stopped", result["classification"])

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


if __name__ == "__main__":
    unittest.main()
