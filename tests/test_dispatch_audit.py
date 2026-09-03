from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import dispatch_audit


class DispatchAuditTests(unittest.TestCase):
    def test_star_case_scan_ignores_commented_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.f90"
            path.write_text(
                "select case(command)\n"
                "case('*NODE')\n"
                "! case('*OLD')\n"
                "case ('*ELEM') ! active\n"
                "end select\n",
                encoding="utf-8",
            )
            found = dispatch_audit._star_cases(path, "source/input.f90")
        self.assertEqual(["*NODE", "*ELEM"], [item.token for item in found])
        self.assertEqual("source/input.f90:2", found[0].locator)

    def test_only_commented_initializers_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.f90"
            path.write_text(
                "! call OLD_INI(input_id)\n"
                "! call stopwatch('start')\n"
                "call LIVE_INI(input_id)\n",
                encoding="utf-8",
            )
            found = dispatch_audit._commented_initializer_calls(path, "source/main.f90")
        self.assertEqual(["OLD_INI"], [item["routine"] for item in found])

    def test_generated_primary_audit_is_checked_in(self) -> None:
        text = dispatch_audit.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        self.assertIn("Primary dispatch coverage is **complete**", text)
        self.assertIn("`top_level_missing_from_registry`: none", text)
        self.assertIn("`cluster_missing_from_registry`: none", text)
        self.assertIn("`boundary_missing_from_registry`: none", text)


if __name__ == "__main__":
    unittest.main()
