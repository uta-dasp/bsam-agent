from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.change import (
    apply_plan,
    plan_expand_notch_plies,
    plan_parameter_change,
    review_plan,
    write_plan,
)
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

    def test_approved_two_to_eight_ply_notch_transformation(self) -> None:
        plan = plan_expand_notch_plies(NOTCH)

        self.assertEqual("expand-notch-plies", plan["operation"])
        self.assertEqual(8, plan["selector"]["output_plies"])
        self.assertEqual(0.25, plan["selector"]["ply_thickness"])
        self.assertEqual([75, 15] * 4, plan["selector"]["layup_degrees"])
        self.assertEqual(5, len(plan["patches"]))
        self.assertEqual(0, plan["validation"]["summary"]["errors"])
        self.assertEqual(61920, plan["validation"]["semantic_summary"]["entities"])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "expand.json"
            output = root / "notch_v1_8ply.in"
            write_plan(plan, plan_path)
            review = review_plan(plan_path)
            self.assertEqual(plan["proposed_sha256"], review["proposed_sha256"])
            result = apply_plan(plan_path, output)
            self.assertEqual(plan["proposed_sha256"], result["output_sha256"])

            text = output.read_text(encoding="latin-1")
            self.assertEqual(1, text.count("type=-2, name=penalty"))
            self.assertEqual(7, text.count("mset=PLY"))
            self.assertIn("last=PLY8", text)
            self.assertEqual(8, text.count("-approximation"))
            self.assertEqual(8, text.count("type=disp, value=0.1"))
            self.assertEqual(1, text.count("comp=z"))
            inspection = SourceSet.read(output).inspection()
            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(61920, inspection["semantic_model"]["summary"]["entities"])


if __name__ == "__main__":
    unittest.main()
