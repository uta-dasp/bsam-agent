from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.change import plan_parameter_change
from bsam_agent.source_set import SourceSet


NOTCH = Path(__file__).resolve().parents[2] / "projects" / "notch_v1" / "notch_v1.in"


@unittest.skipUnless(NOTCH.is_file(), "local notch_v1 acceptance model is unavailable")
class NotchProjectIntegrationTests(unittest.TestCase):
    def test_notch_semantic_baseline_and_safe_change_preview(self) -> None:
        inspection = SourceSet.read(NOTCH).inspection()

        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(
            "B7ACAA7EFEF23D27F9ADCD01FE24AD6D2BC2F5EC9CB997AEE221CC562DB9010D",
            inspection["sha256"],
        )
        semantic = inspection["semantic_model"]["summary"]
        self.assertEqual(15480, semantic["entities"])
        self.assertEqual(53690, semantic["resolved_references"])
        self.assertEqual(0, semantic["unresolved_references"])

        plan = plan_parameter_change(
            NOTCH, "BOUNDARY", "CONVERGENCE", "d_reduction", "0.30"
        )
        self.assertEqual("0.25", plan["patch"]["old"])
        self.assertEqual(0, plan["validation"]["summary"]["errors"])
        self.assertIn("+d_reduction =0.30", plan["source_diff"])


if __name__ == "__main__":
    unittest.main()
