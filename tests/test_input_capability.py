from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.source_set import SourceSet


TAIL = (
    "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
    "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
    "MATERIALS\n0\nEND MATERIALS\n"
    "CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
)


def diagnostics(input_block: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.in"
        path.write_text(input_block + TAIL, encoding="ascii", newline="\n")
        return SourceSet.read(path).inspection()["diagnostics"]


class InputCapabilityTests(unittest.TestCase):
    def test_accepts_exact_current_single_record_and_preserves_bytes(self) -> None:
        raw = "INPUT\n** current format\n3\nEND INPUT\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_text(raw + TAIL, encoding="ascii", newline="\n")
            inspection = SourceSet.read(path).inspection()
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertTrue(inspection["no_op_round_trip"])
        record = next(
            item for item in inspection["semantic_model"]["capability_records"]
            if item["capability_id"] == "block.input"
        )
        self.assertEqual("3", record["parameters"]["type"][0]["value"])

    def test_rejects_wrong_type_missing_extra_and_unterminated_records(self) -> None:
        wrong = diagnostics("INPUT\n2\nEND INPUT\n")
        missing = diagnostics("INPUT\nEND INPUT\n")
        extra = diagnostics("INPUT\n3\n3\nEND INPUT\n")
        unterminated = diagnostics("INPUT\n3\n")
        self.assertIn("BSAM-E310", {item["code"] for item in wrong})
        self.assertIn("BSAM-E390", {item["code"] for item in missing})
        self.assertIn("BSAM-E390", {item["code"] for item in extra})
        self.assertIn("BSAM-E390", {item["code"] for item in unterminated})

    def test_rejects_duplicate_required_input_blocks(self) -> None:
        items = diagnostics("INPUT\n3\nEND INPUT\nINPUT\n3\nEND INPUT\n")
        self.assertIn("BSAM-E390", {item["code"] for item in items})


if __name__ == "__main__":
    unittest.main()
