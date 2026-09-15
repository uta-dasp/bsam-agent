from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.source_set import SourceSet


FIXTURES = Path(__file__).parent / "fixtures"


class StructuredConstructionAcceptanceTests(unittest.TestCase):
    def test_selected_source_and_acceptance_objective_are_valid_and_non_specialized(self) -> None:
        source = FIXTURES / "structured_copy_source.in"
        intent = json.loads(
            (FIXTURES / "structured_copy_objective.json").read_text(encoding="utf-8")
        )
        inspection = SourceSet.read(source).inspection()
        summary = inspection["semantic_model"]["summary"]
        kinds = summary["entities_by_kind"]

        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertTrue(inspection["no_op_round_trip"])
        self.assertEqual(0, summary["unresolved_references"])
        self.assertEqual(0, summary["ambiguous_references"])
        self.assertEqual(0, summary["type_mismatches"])
        self.assertEqual(1, kinds["cluster"])
        self.assertEqual(8, kinds["node"])
        self.assertEqual(1, kinds["element"])
        self.assertEqual(2, kinds["node-set"])
        self.assertEqual(1, kinds["element-set"])
        self.assertEqual(1, kinds["orientation-record"])
        self.assertEqual(1, kinds["section"])
        self.assertEqual("substantial-structured-copy-v1", intent["acceptance_id"])
        self.assertEqual("structured_copy_source.in", intent["source"])
        self.assertEqual("structured_copy_result.in", intent["destination"])
        self.assertNotIn("notch", intent["objective"].casefold())
        self.assertIn("preview_expand_notch_plies", intent["prohibited_tools"])
        self.assertEqual(2, len(intent["construction"]["copies"]))
        self.assertEqual(3, intent["expected"]["cluster_count"])
        self.assertEqual(1, intent["expected"]["confirmation_boundaries"])


if __name__ == "__main__":
    unittest.main()
