from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.source_set import SourceSet


def numeric_user_deck(body: bytes) -> bytes:
    return (
        b"INPUT\n3\nEND INPUT\n"
        b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        b"MATERIALS\n0\nEND MATERIALS\n"
        b"USER\n" + body + b"END USER\n"
        b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
    )


class NumericUserCapabilityTests(unittest.TestCase):
    def test_constitutive_curve_ids_resolve_numeric_user_functions(self) -> None:
        variants = (
            (3, b"1,1,0,1,2,3,4,0", 4),
            (4, b"1,1,0,1,2,3,4,5,6,0", 6),
        )
        for constitutive_type, data, count in variants:
            with self.subTest(constitutive_type=constitutive_type):
                raw = numeric_user_deck(
                    b"1\n0\n1\n" * count,
                ).replace(
                    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
                    b"CONSTITUTIVE\n" + str(constitutive_type).encode() + b"\n"
                    + data + b"\nEND CONSTITUTIVE\n"
                    b"FAILURE\n4\nEND FAILURE\n",
                ).replace(
                    b"MATERIALS\n0\nEND MATERIALS\n",
                    b"MATERIALS\n999\nE11=1\n*end\nEND MATERIALS\n",
                )
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "model.in"
                    path.write_bytes(raw)
                    inspection = SourceSet.read(path).inspection()

                constitutive = next(
                    item for item in inspection["semantic_model"]["entities"]
                    if item["kind"] == "constitutive"
                )
                references = [
                    item for item in inspection["semantic_model"]["references"]
                    if item["source_entity_id"] == constitutive["id"]
                    and item["kind"] == "uses-numeric-user-function"
                ]
                expected_ids = list(range(1, count + 1))
                self.assertEqual(
                    expected_ids, constitutive["attributes"]["numeric_user_ids"]
                )
                self.assertEqual([
                    f"numeric-user-function:{item}" for item in expected_ids
                ], [item["target_key"] for item in references])
                self.assertTrue(all(
                    item["status"] == "resolved" for item in references
                ))
                self.assertEqual(0, inspection["summary"]["errors"])

    def test_safe_analytic_and_inline_variants_are_consumed_in_order(self) -> None:
        raw = numeric_user_deck(
            b"1\n2\n1\n2\n3\n"
            b"2\n1\n4,5\n"
            b"5\n1\n0,10\n2,5\n"
            b"101\n3\n0,0\n1,2\n2,4\n"
            b"201\n2\n0,1,2,3\n1,4,5,6\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()
            rendered = SourceSet.read(path).render_files()[path.resolve()]

        entities = [
            item for item in inspection["semantic_model"]["entities"]
            if item["kind"] == "numeric-user-function"
        ]
        records = [
            item for item in inspection["semantic_model"]["capability_records"]
            if item["capability_id"] == "block.user"
        ]
        self.assertEqual([1, 2, 5, 101, 201], [
            item["attributes"]["type"] for item in entities
        ])
        self.assertTrue(all(item["attributes"]["complete"] for item in entities))
        self.assertEqual([1, 2, 5, 101, 201], [
            item["parameters"]["type"][0]["value"] for item in records
        ])
        self.assertEqual(3, len(entities[3]["attributes"]["data"]))
        self.assertEqual(4, len(entities[4]["attributes"]["data"][0]))
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(raw, rendered)

    def test_external_and_sparse_forms_are_typed_preservation_boundaries(self) -> None:
        raw = numeric_user_deck(b"100\npoints.dat\n301\n2,2,1\n0,1,1\n1\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            semantic = SourceSet.read(path).inspection()["semantic_model"]

        entities = [
            item for item in semantic["entities"]
            if item["kind"] == "numeric-user-function"
        ]
        self.assertEqual([100, 301], [item["attributes"]["type"] for item in entities])
        self.assertEqual(
            "external-file-not-in-source-set", entities[0]["attributes"]["preservation"]
        )
        self.assertEqual("blocked-sparse-matrix", entities[1]["attributes"]["preservation"])
        self.assertEqual(2, len([
            item for item in semantic["capability_records"]
            if item["capability_id"] == "block.user"
        ]))

    def test_static_validation_rejects_incomplete_and_unsafe_numeric_functions(self) -> None:
        invalid = {
            "empty": b"",
            "unsupported": b"9\n",
            "zero-terms": b"2\n0\n",
            "short-spline": b"101\n1\n0,0\n",
            "nonmonotonic-spline": b"101\n3\n0,0\n1,1\n0,2\n",
            "piecewise-order": b"5\n1\n1,0\n2,1\n",
            "unsafe-external": b"100\n../points.dat\n",
            "bad-sparse": b"301\n2,2,1\n0,2,1\n3\n",
        }
        for name, body in invalid.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.in"
                path.write_bytes(numeric_user_deck(body))
                diagnostics = SourceSet.read(path).inspection()["diagnostics"]
            self.assertTrue(any(
                item["severity"] == "error" and item["code"] == "BSAM-E380"
                for item in diagnostics
            ))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "disabled.in"
            path.write_bytes(numeric_user_deck(b"0\n"))
            inspection = SourceSet.read(path).inspection()
        self.assertEqual(0, inspection["summary"]["errors"])


if __name__ == "__main__":
    unittest.main()
