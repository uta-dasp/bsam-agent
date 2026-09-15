from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import LocalAgentApi
from bsam_agent.capabilities import capability_manifest
from bsam_agent.orchestrator import ChatOrchestrator
from bsam_agent.provider import ProviderConfig
from bsam_agent.source_set import SourceSet


def table_deck(material_value: str = "table_stiffness") -> bytes:
    return (
        "INPUT\n3\nEND INPUT\n"
        "TABLES\n"
        "table-stiffness\n"
        "temp-moisture 0 1\n"
        "10 100 200\n"
        "20 150 250\n"
        "*end\n"
        "table-strength\n"
        "time|fvf 0.0 0.5 1.0\n"
        "1 10 20 30\n"
        "2 15 25 35\n"
        "*end\n"
        "END TABLES\n"
        "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        "MATERIALS\n999\n"
        f"E11={material_value}\n"
        "E22=table_strength\n"
        "*end\nEND MATERIALS\n"
        "CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
    ).encode("latin-1")


class TableCapabilityTests(unittest.TestCase):
    def test_polynomial_material_reference_resolves_every_table_identity(self) -> None:
        raw = table_deck("poly_stiffness_strength_stiffness")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()

        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["kind"] == "uses-table"
        ]
        self.assertEqual([
            "table:stiffness", "table:strength", "table:stiffness",
            "table:strength",
        ], [item["target_key"] for item in references])
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_named_tables_and_structured_material_references_resolve(self) -> None:
        raw = table_deck()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            source_set = SourceSet.read(path)
            inspection = source_set.inspection()
            rendered = source_set.render_files()[path.resolve()]

        semantic = inspection["semantic_model"]
        tables = [item for item in semantic["entities"] if item["kind"] == "table"]
        references = [
            item for item in semantic["references"] if item["kind"] == "uses-table"
        ]
        stiffness = next(item for item in tables if item["name"] == "stiffness")
        self.assertEqual([2, 2], stiffness["attributes"]["shape"])
        self.assertEqual([0.0, 1.0], stiffness["attributes"]["horizontal_lookup"])
        self.assertEqual([10.0, 20.0], stiffness["attributes"]["vertical_lookup"])
        self.assertEqual(2, len(tables))
        self.assertEqual(2, len(references))
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(raw, rendered)

    def test_table_capability_records_are_queryable_and_source_located(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(table_deck())
            result = LocalAgentApi(root).dispatch("query_model", {
                "source": "model.in", "query": "inspect-capability",
                "capability": "block.tables",
            })

        self.assertEqual(2, result["summary"]["matches"])
        self.assertEqual("stiffness", result["matches"][0]["parameters"]["name"][0]["value"])
        self.assertEqual([2, 2], result["matches"][0]["attributes"]["shape"])
        self.assertEqual("verified", result["matches"][0]["operations"]["inspect"])

    def test_reviewed_table_cell_edit_patches_one_exact_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            source.write_bytes(table_deck())
            api = LocalAgentApi(root)

            plan = api.dispatch("preview_modify_entity", {
                "source": "model.in",
                "capability": "block.tables",
                "entity_name": "stiffness",
                "changes": {"row": 2, "column": 2, "value": "275"},
                "plan_path": "table-change.json",
            })
            self.assertEqual("set-table-value", plan["operation"])
            self.assertEqual("250", plan["patch"]["old"])
            self.assertEqual("275", plan["patch"]["new"])
            self.assertEqual(
                ["TABLES[stiffness].values[2,2]"], plan["changed_model_paths"],
            )
            api.dispatch("review_change", {"plan_path": "table-change.json"})
            result = api.dispatch("apply_change", {
                "plan_path": "table-change.json",
                "destination": "changed.in",
                "confirm": True,
            })
            changed = (root / "changed.in").read_bytes()
            self.assertIn(b"20 150 275", changed)
            self.assertEqual(1, plan["source_diff"].count("-20 150 250"))
            self.assertEqual(1, plan["source_diff"].count("+20 150 275"))
            self.assertEqual(0, result["validation"]["summary"]["errors"])

            invalid_changes = (
                {"row": 3, "column": 1, "value": "1"},
                {"row": 1, "column": 1, "value": "nan"},
                {"row": 1, "column": 1, "value": "100.0"},
            )
            for ordinal, changes in enumerate(invalid_changes, start=1):
                with self.assertRaises(ValueError):
                    api.dispatch("preview_modify_entity", {
                        "source": "model.in",
                        "capability": "block.tables",
                        "entity_name": "stiffness",
                        "changes": changes,
                        "plan_path": f"invalid-{ordinal}.json",
                    })

    def test_reference_queries_accept_stable_kind_and_name_selectors(self) -> None:
        duplicate = table_deck().replace(
            b"END TABLES", b"table-stiffness\ntemp-moisture 0\n10 1\n*end\nEND TABLES",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(table_deck())
            (root / "duplicate.in").write_bytes(duplicate)
            api = LocalAgentApi(root)
            references = api.dispatch("query_model", {
                "source": "model.in", "query": "references-to",
                "entity_kind": "table", "entity_name": "stiffness",
            })
            ambiguous = api.dispatch("query_model", {
                "source": "duplicate.in", "query": "references-to",
                "entity_kind": "table", "entity_name": "stiffness",
            })

        self.assertEqual(1, references["summary"]["matches"])
        self.assertEqual("uses-table", references["matches"][0]["kind"])
        self.assertTrue(ambiguous["summary"]["ambiguous"])
        self.assertEqual([], ambiguous["matches"])

    def test_missing_and_duplicate_table_targets_are_diagnostics(self) -> None:
        missing = table_deck("table_missing")
        duplicate = table_deck().replace(
            b"END TABLES", b"table-stiffness\ntemp-moisture 0\n10 1\n*end\nEND TABLES",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_path = root / "missing.in"
            duplicate_path = root / "duplicate.in"
            missing_path.write_bytes(missing)
            duplicate_path.write_bytes(duplicate)
            missing_codes = [
                item["code"] for item in SourceSet.read(missing_path).inspection()["diagnostics"]
            ]
            duplicate_codes = [
                item["code"] for item in SourceSet.read(duplicate_path).inspection()["diagnostics"]
            ]

        self.assertIn("BSAM-E301", missing_codes)
        self.assertIn("BSAM-E300", duplicate_codes)
        self.assertIn("BSAM-E303", duplicate_codes)

    def test_nonrectangular_and_nonmonotonic_grids_are_rejected(self) -> None:
        invalid = table_deck().replace(
            b"temp-moisture 0 1\n10 100 200\n20 150 250",
            b"temp-moisture 1 0\n10 100\n5 150 250",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.in"
            path.write_bytes(invalid)
            inspection = SourceSet.read(path).inspection()
        codes = [item["code"] for item in inspection["diagnostics"]]
        self.assertIn("BSAM-E320", codes)
        self.assertIn("BSAM-E321", codes)
        self.assertGreater(inspection["summary"]["errors"], 0)

    def test_table_operational_support_is_explicit(self) -> None:
        table = next(
            item for item in capability_manifest() if item["id"] == "block.tables"
        )
        self.assertEqual("verified", table["operations"]["parse"])
        self.assertEqual("verified", table["operations"]["static_validation"])
        self.assertEqual("verified", table["operations"]["modify"])

    def test_natural_table_listing_is_deterministic(self) -> None:
        class NoCallProvider:
            def complete(self, _request):  # pragma: no cover - a call fails the test
                raise AssertionError("table listing should not call the provider")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(table_deck())
            agent = ChatOrchestrator(
                NoCallProvider(),
                ProviderConfig(
                    "fake", "fake", "http://127.0.0.1", None, 1, 10000, 128, "local-only",
                ),
                LocalAgentApi(root),
            )
            result = agent.turn("List the tables in model.in.")
            references = agent.turn("Show references to table stiffness in model.in.")

        self.assertEqual("query_model", result.tool)
        self.assertEqual(2, result.tool_result["summary"]["matches"])
        self.assertTrue(all(item["kind"] == "table" for item in result.tool_result["matches"]))
        self.assertEqual("find_references", references.tool)
        self.assertEqual(1, references.tool_result["summary"]["matches"])


if __name__ == "__main__":
    unittest.main()
