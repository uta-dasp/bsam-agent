from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.change import ChangeError, apply_plan, plan_parameter_change, write_plan


DECK = (
    b"INPUT\r\n3\r\nEND INPUT\r\n"
    b"BOUNDARY\r\n*type\r\nmechanical\r\n*convergence\r\n"
    b"absolute=1\r\nd_reduction =0.25\r\nmaxiterations=20\r\nEND BOUNDARY\r\n"
    b"CONSTITUTIVE\r\n0\r\nEND CONSTITUTIVE\r\n"
    b"MATERIALS\r\n0\r\nEND MATERIALS\r\n"
    b"CLUSTERS\r\n*type\r\nsolid\r\n*STOP\r\nEND CLUSTERS\r\n"
)


class ChangePlanTests(unittest.TestCase):
    def test_plan_and_apply_patch_only_value_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            output = root / "model.changed.in"
            source.write_bytes(DECK)

            plan = plan_parameter_change(
                source, "BOUNDARY", "*CONVERGENCE", "d_reduction", "0.5"
            )
            self.assertEqual("0.25", plan["patch"]["old"])
            self.assertEqual("0.5", plan["patch"]["new"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, output)

            self.assertEqual(DECK, source.read_bytes())
            self.assertEqual(
                DECK.replace(b"d_reduction =0.25", b"d_reduction =0.5"),
                output.read_bytes(),
            )
            self.assertNotEqual(result["base_sha256"], result["output_sha256"])

    def test_stale_plan_is_rejected_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            output = root / "model.changed.in"
            source.write_bytes(DECK)
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "maxiterations", "30"
            )
            write_plan(plan, plan_path)
            source.write_bytes(DECK + b"** changed after planning\r\n")

            with self.assertRaisesRegex(ChangeError, "source changed after planning"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())

    def test_in_place_and_ambiguous_changes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            source.write_bytes(DECK)
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
            )
            write_plan(plan, plan_path)
            with self.assertRaisesRegex(ChangeError, "in-place"):
                apply_plan(plan_path, source)

            duplicate = root / "duplicate.in"
            duplicate.write_bytes(DECK.replace(b"absolute=1", b"absolute=1, absolute=2"))
            with self.assertRaisesRegex(ChangeError, "ambiguous"):
                plan_parameter_change(
                    duplicate, "BOUNDARY", "CONVERGENCE", "absolute", "3"
                )

    def test_unregistered_and_invalid_values_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK)
            with self.assertRaisesRegex(ChangeError, "untyped edits are blocked"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "mystery", "1"
                )
            with self.assertRaisesRegex(ChangeError, "must be positive"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "-1"
                )


if __name__ == "__main__":
    unittest.main()
