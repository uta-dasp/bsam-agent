from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent import cli
from bsam_agent.change import (
    ChangeError,
    _plan_digest,
    apply_plan,
    plan_parameter_change,
    review_plan,
    write_plan,
)
from bsam_agent.source_set import SourceSet


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
            self.assertEqual(
                ["BOUNDARY.*CONVERGENCE[1].d_reduction"],
                plan["changed_model_paths"],
            )
            self.assertIn("-d_reduction =0.25", plan["source_diff"])
            self.assertIn("+d_reduction =0.5", plan["source_diff"])
            write_plan(plan, plan_path)
            review = review_plan(plan_path)
            self.assertEqual(plan["proposed_sha256"], review["proposed_sha256"])
            result = apply_plan(plan_path, output)

            self.assertEqual(DECK, source.read_bytes())
            self.assertEqual(
                DECK.replace(b"d_reduction =0.25", b"d_reduction =0.5"),
                output.read_bytes(),
            )
            self.assertNotEqual(result["base_sha256"], result["output_sha256"])
            audit_path = Path(str(output) + ".audit.json")
            self.assertEqual(audit_path.resolve(), Path(result["audit"]))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["plan_digest"], audit["plan"]["digest"])
            self.assertEqual(result["output_sha256"], audit["output_sha256"])
            self.assertEqual(0, audit["validation"]["summary"]["errors"])
            self.assertIsNone(audit["run_directory"])
            audit_content = {
                key: value for key, value in audit.items()
                if key not in {"audit_digest", "audit_id"}
            }
            self.assertEqual(audit["audit_digest"], _plan_digest(audit_content))

    def test_diff_cli_revalidates_and_returns_review_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            source.write_bytes(DECK)
            write_plan(
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "maxiterations", "30"
                ),
                plan_path,
            )

            output = io.StringIO()
            with redirect_stdout(output):
                status = cli.main(["diff", str(plan_path), "--compact"])
            review = json.loads(output.getvalue())
            self.assertEqual(0, status)
            self.assertEqual(
                ["BOUNDARY.*CONVERGENCE[1].maxiterations"],
                review["changed_model_paths"],
            )
            self.assertIn("-maxiterations=20", review["source_diff"])
            self.assertIn("+maxiterations=30", review["source_diff"])

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
            with self.assertRaisesRegex(ChangeError, "source changed after planning"):
                review_plan(plan_path)

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

            output = root / "output.in"
            audit = Path(str(output) + ".audit.json")
            audit.write_text("existing", encoding="ascii")
            with self.assertRaisesRegex(ChangeError, "audit destination already exists"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())

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

    def test_change_planning_rejects_unresolved_semantic_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            invalid = DECK.replace(
                b"*STOP\r\n",
                b"*ELEMENT,TYPE=C3D4\r\n1,99,99,99,99\r\n*STOP\r\n",
            )
            source.write_bytes(invalid)

            with self.assertRaisesRegex(ChangeError, "dependency validation"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
                )
            with self.assertRaisesRegex(ChangeError, "must be positive"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "-1"
                )

    def test_redigested_forged_plan_cannot_bypass_registered_typing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "forged.json"
            output = root / "changed.in"
            source.write_bytes(DECK)
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
            )
            plan["patch"]["new"] = "-1"
            content = {
                key: value for key, value in plan.items()
                if key not in {"plan_digest", "plan_id"}
            }
            digest = _plan_digest(content)
            plan["plan_digest"] = digest
            plan["plan_id"] = digest[:16]
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(ChangeError, "must be positive"):
                review_plan(plan_path)
            with self.assertRaisesRegex(ChangeError, "must be positive"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())

    def test_plan_is_bound_to_includes_and_preserves_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "change.json"
            output = root / "model.changed.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(b"*NODE\r\n1, 0, 0, 0\r\n")
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "d_reduction", "0.5"
            )
            self.assertIn("base_source_set_sha256", plan)
            self.assertIn("proposed_source_set_sha256", plan)
            write_plan(plan, plan_path)

            legacy = dict(plan)
            for field in (
                "workspace_root",
                "base_source_set_sha256",
                "proposed_source_set_sha256",
                "plan_digest",
                "plan_id",
            ):
                legacy.pop(field, None)
            legacy["schema_version"] = "1.1.0"
            legacy_digest = _plan_digest(legacy)
            legacy["plan_digest"] = legacy_digest
            legacy["plan_id"] = legacy_digest[:16]
            legacy_path = root / "legacy.json"
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
            with self.assertRaisesRegex(ChangeError, "legacy change plan"):
                review_plan(legacy_path)

            include.write_bytes(include.read_bytes() + b"** changed\r\n")
            with self.assertRaisesRegex(ChangeError, "source set changed after planning"):
                review_plan(plan_path)
            with self.assertRaisesRegex(ChangeError, "source set changed after planning"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())

            include.write_bytes(b"*NODE\r\n1, 0, 0, 0\r\n")
            outside_directory = root / "revision"
            outside_directory.mkdir()
            with self.assertRaisesRegex(ChangeError, "original input directory"):
                apply_plan(plan_path, outside_directory / "model.changed.in")

            result = apply_plan(plan_path, output)
            self.assertEqual(
                plan["proposed_source_set_sha256"],
                result["output_source_set_sha256"],
            )
            self.assertEqual(
                result["output_source_set_sha256"],
                SourceSet.read(output).sha256,
            )
            audit = json.loads(Path(result["audit"]).read_text(encoding="utf-8"))
            self.assertEqual(
                result["output_source_set_sha256"],
                audit["output_source_set_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
