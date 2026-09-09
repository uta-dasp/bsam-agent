from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.source_set import SourceSet


def failure_deck(body: str) -> bytes:
    return (
        "INPUT\n3\nEND INPUT\n"
        "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        f"FAILURE\n{body}END FAILURE\n"
        "MATERIALS\n0\nEND MATERIALS\n"
        "CLUSTERS\n*type\nsolid\n*NAME\nply1\n*STOP\nEND CLUSTERS\n"
    ).encode("latin-1")


class FailureCapabilityTests(unittest.TestCase):
    def test_failure_variants_are_consumed_in_declaration_order(self) -> None:
        degradation = "".join("1 1 1 1 1 1 1 1\n" for _ in range(10))
        raw = failure_deck(
            "4 no-data\n"
            "1 degradation\n" + degradation +
            "23 fatigue-wrapper\n1\n"
            "18 cfv\n1 2 20\n1 1 1 1 1\n2 1 1 1 1\n"
            "26 CFACTOR=0.5\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            source_set = SourceSet.read(path)
            inspection = source_set.inspection()
            rendered = source_set.render_files()[path.resolve()]

        semantic = inspection["semantic_model"]
        failures = [item for item in semantic["entities"] if item["kind"] == "failure"]
        self.assertEqual([4, 1, 23, 18, 26], [
            item["attributes"]["type"] for item in failures
        ])
        self.assertEqual(10, failures[1]["attributes"]["degradation_row_count"])
        self.assertEqual(2, failures[3]["attributes"]["mode_count"])
        self.assertEqual(0.5, failures[4]["attributes"]["cfactor"])
        references = [item for item in semantic["references"] if item["kind"] == "uses-failure"]
        self.assertEqual(2, len(references))
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        records = [
            item for item in semantic["capability_records"]
            if item["capability_id"] == "block.failure"
        ]
        self.assertEqual(5, len(records))
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(raw, rendered)

    def test_incomplete_failure_body_is_rejected_without_phantom_entities(self) -> None:
        raw = failure_deck("18\n1 2 20\n1 1 1 1 1\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()

        self.assertFalse(any(
            item["kind"] == "failure"
            for item in inspection["semantic_model"]["entities"]
        ))
        self.assertIn("BSAM-E370", [item["code"] for item in inspection["diagnostics"]])


if __name__ == "__main__":
    unittest.main()
