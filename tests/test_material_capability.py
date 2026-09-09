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


def material_deck() -> bytes:
    return (
        "INPUT\n3\nEND INPUT\n"
        "TABLES\ntable-modulus\ntemp-moisture 0\n0 10\n*end\nEND TABLES\n"
        "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        "MATERIALS\n"
        "999 bulk-note\nE11=table_modulus\nNu12=0.3\n*end\n"
        "998 interface-note\nK=100\ntol=0.01\n*end\n"
        "1 legacy-preserved\n 1 2 3\n"
        "END MATERIALS\n"
        "CLUSTERS\n*type\nsolid\n*NAME\nply1\n*STOP\nEND CLUSTERS\n"
    ).encode("latin-1")


class StructuredMaterialCapabilityTests(unittest.TestCase):
    def test_type_four_material_resolves_numeric_user_selectors(self) -> None:
        selector_rows = (
            "1 10 11\n2 12 13\n3\n4 1 2 3\n5\n6\n"
            "7\n8\n9 1 2\n10\n11\n12\n"
        )
        raw = (
            "INPUT\n3\nEND INPUT\n"
            "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            f"MATERIALS\n4\n{selector_rows}END MATERIALS\n"
            "USER\n" + "1\n0\n1\n" * 12 + "END USER\n"
            "CLUSTERS\n*type\nsolid\n*NAME\nply1\n*STOP\nEND CLUSTERS\n"
        ).encode("latin-1")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()

        material = next(
            item for item in inspection["semantic_model"]["entities"]
            if item["kind"] == "material"
        )
        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] == material["id"]
            and item["kind"] == "uses-numeric-user-function"
        ]
        self.assertEqual(list(range(1, 13)), material["attributes"]["numeric_user_ids"])
        self.assertEqual([
            f"numeric-user-function:{item}" for item in range(1, 13)
        ], [item["target_key"] for item in references])
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_complete_material_block_receives_declaration_order_identities(self) -> None:
        rows = lambda count: "".join("1\n" for _ in range(count))
        material_body = (
            "999 bulk\nE=1\n*end\n"
            "type=mises, name=plastic\nE=1\n*end\n"
            "10\n" + rows(2) +
            "15\n" + rows(5) +
            "2\n" + rows(18) +
            "3\n" + rows(16) +
            "4\n" + rows(12) +
            "11\n" + rows(1) +
            "40\n" + rows(2) +
            "41\n" + rows(2) +
            "200\n" + rows(2) + "*delta\n1\n" +
            "300\n2\n1 0\n2 1\n0.5\n"
            "500\n2 1\n1 1\n2 2\n"
            "800\n" + rows(3) +
            "1\n" + rows(12) +
            "*S-N\n1 1 1\n"
            "*statistics\n1\n1 1 1\n1 2 3\n#generation 9\n*end\n" +
            "12\n" + rows(3) +
            "210\n" + rows(12) + "1\nuc-file\n" +
            "998 interface\nK=1\n*end\n"
        )
        raw = (
            "INPUT\n3\nEND INPUT\n"
            "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            f"MATERIALS\n{material_body}END MATERIALS\n"
            "USER\n1\n0\n1\nEND USER\n"
            "CLUSTERS\n*type\nsolid\n*NAME\nply1\n*STOP\nEND CLUSTERS\n"
        ).encode("latin-1")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()

        materials = [
            item for item in inspection["semantic_model"]["entities"]
            if item["kind"] == "material"
        ]
        self.assertEqual(
            [999, 50, 10, 15, 2, 3, 4, 11, 40, 41, 200, 300, 500, 800, 1, 12, 210, 998],
            [item["attributes"]["type"] for item in materials],
        )
        self.assertEqual(list(range(1, 19)), [
            item["attributes"]["declaration_ordinal"] for item in materials
        ])
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_only_structured_groups_receive_declaration_identities(self) -> None:
        raw = material_deck()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            source_set = SourceSet.read(path)
            inspection = source_set.inspection()
            rendered = source_set.render_files()[path.resolve()]

        semantic = inspection["semantic_model"]
        materials = [
            item for item in semantic["entities"] if item["kind"] == "structured-material"
        ]
        self.assertEqual([999, 998], [item["attributes"]["type"] for item in materials])
        self.assertEqual([2, 2], [
            item["attributes"]["parameter_record_count"] for item in materials
        ])
        self.assertFalse(any(
            item["kind"] == "structured-material" and item["attributes"]["type"] == 1
            for item in semantic["entities"]
        ))
        table_reference = next(
            item for item in semantic["references"] if item["kind"] == "uses-table"
        )
        self.assertEqual(materials[0]["id"], table_reference["source_entity_id"])
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(raw, rendered)

    def test_structured_material_records_are_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(material_deck())
            result = LocalAgentApi(root).dispatch("query_model", {
                "source": "model.in", "query": "inspect-capability",
                "capability": "block.materials",
            })
            entities = LocalAgentApi(root).dispatch("query_model", {
                "source": "model.in", "query": "list-entities",
                "entity_kind": "structured-material",
            })

        self.assertEqual(2, result["summary"]["matches"])
        self.assertTrue(all(
            item["attributes"]["syntax"] == "structured" for item in result["matches"]
        ))
        self.assertEqual(2, entities["summary"]["matches"])

    def test_missing_structured_terminator_is_rejected(self) -> None:
        invalid = material_deck().replace(b"Nu12=0.3\n*end", b"Nu12=0.3", 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.in"
            path.write_bytes(invalid)
            inspection = SourceSet.read(path).inspection()
        self.assertIn("BSAM-E350", [item["code"] for item in inspection["diagnostics"]])

    def test_block_support_is_partial_while_structured_instances_are_verified(self) -> None:
        material = next(
            item for item in capability_manifest() if item["id"] == "block.materials"
        )
        self.assertEqual("implemented", material["operations"]["semantic"])
        self.assertEqual("unsupported", material["operations"]["modify"])

    def test_natural_structured_material_listing_is_deterministic(self) -> None:
        class NoCallProvider:
            def complete(self, _request):  # pragma: no cover - a call fails the test
                raise AssertionError("material listing should not call the provider")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(material_deck())
            agent = ChatOrchestrator(
                NoCallProvider(),
                ProviderConfig(
                    "fake", "fake", "http://127.0.0.1", None, 1, 10000, 128, "local-only",
                ),
                LocalAgentApi(root),
            )
            result = agent.turn("List the structured materials in model.in.")

        self.assertEqual("query_model", result.tool)
        self.assertEqual(2, result.tool_result["summary"]["matches"])


if __name__ == "__main__":
    unittest.main()
