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
    def test_orthotropic_nonlinear_shear_resolves_numeric_users(self) -> None:
        properties = (
            "1 2 3\n1 2 3\n1\n0.1 1 2 3\n0.1\n0.1\n"
            "uf= {g13}\n1\nuf= {g12} 1 1\n1\n1\n1\n"
        )
        raw = (
            "INPUT\n3\nEND INPUT\n"
            "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            "MATERIALS\n105\n"
            + properties.format(g13=1, g12=2)
            + "1\n*shear\n"
            + properties.format(g13=3, g12=4)
            + "END MATERIALS\n"
            + "USER\n" + "1\n0\n1\n" * 4 + "END USER\n"
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
            [{"g13": 1, "g12": 2}, {"g13": 3, "g12": 4}],
            [item["attributes"]["numeric_user_selectors"] for item in materials],
        )
        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] in {material["id"] for material in materials}
            and item["kind"] == "uses-numeric-user-function"
        ]
        self.assertEqual([
            "numeric-user-function:1", "numeric-user-function:2",
            "numeric-user-function:3", "numeric-user-function:4",
        ], [item["target_key"] for item in references])
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_compro_material_resolves_cluster_identity(self) -> None:
        raw = (
            "INPUT\n3\nEND INPUT\n"
            "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            "MATERIALS\n800\n1\ncompro.out\n1 2 3 4 5 6\nEND MATERIALS\n"
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
        reference = next(
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] == material["id"]
            and item["kind"] == "uses-cluster"
        )
        self.assertEqual(1, material["attributes"]["cluster_id"])
        self.assertEqual("cluster:ply1", reference["target_key"])
        self.assertEqual("resolved", reference["status"])
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_interface_and_viscoelastic_materials_resolve_numeric_users(self) -> None:
        raw = (
            "INPUT\n3\nEND INPUT\n"
            "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            "MATERIALS\n"
            "15\n1 2 3\n0.1 0.2\n1\n2\n3\n"
            "500\n2 4\n1 0.5\n2 0.25\n"
            "END MATERIALS\n"
            "USER\n" + "1\n0\n1\n" * 4 + "END USER\n"
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
            {"mode_i": 1, "mode_ii": 2, "phase": 3},
            materials[0]["attributes"]["numeric_user_selectors"],
        )
        self.assertEqual(
            {"function": 4},
            materials[1]["attributes"]["numeric_user_selectors"],
        )
        material_ids = {item["id"] for item in materials}
        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] in material_ids
            and item["kind"] == "uses-numeric-user-function"
        ]
        self.assertEqual([
            "numeric-user-function:1", "numeric-user-function:2",
            "numeric-user-function:3", "numeric-user-function:4",
        ], [item["target_key"] for item in references])
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_composite_materials_resolve_prior_material_identities(self) -> None:
        raw = (
            "INPUT\n3\nEND INPUT\n"
            "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            "MATERIALS\n"
            "999\nE=1\n*end\n"
            "999\nE=2\n*end\n"
            "11\n1 2 0.25 0.75\n"
            "300\n2\n1 0.25\n2 0.75\n0.5\n"
            "END MATERIALS\n"
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
        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["kind"] == "uses-material"
            and item["source_entity_id"] in {materials[2]["id"], materials[3]["id"]}
        ]
        self.assertEqual([1, 2], materials[2]["attributes"]["material_ids"])
        self.assertEqual([0.25, 0.75], materials[2]["attributes"]["fractions"])
        self.assertEqual([1, 2], materials[3]["attributes"]["material_ids"])
        self.assertEqual(0.5, materials[3]["attributes"]["default_fraction"])
        self.assertEqual([
            "material:1", "material:2", "material:1", "material:2",
        ], [item["target_key"] for item in references])
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_variable_isotropic_materials_resolve_numeric_user_selectors(self) -> None:
        raw = (
            "INPUT\n3\nEND INPUT\n"
            "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            "MATERIALS\n"
            "40\n1 2 3\n10 11 12\n"
            "40\nE=4,G=5,U=6,ALF=7\n10 11 12\n"
            "41\n8 9 10 11\n10 11 12\n"
            "END MATERIALS\n"
            "USER\n" + "1\n0\n1\n" * 11 + "END USER\n"
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
            {"e": 1, "g": 2, "alf": 3},
            materials[0]["attributes"]["numeric_user_selectors"],
        )
        self.assertEqual(
            {"e": 4, "g": 5, "u": 6, "alf": 7},
            materials[1]["attributes"]["numeric_user_selectors"],
        )
        self.assertEqual(
            {"e_j1": 8, "e_j2": 9, "nu": 10, "alpha": 11},
            materials[2]["attributes"]["numeric_user_selectors"],
        )
        material_ids = {item["id"] for item in materials}
        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] in material_ids
            and item["kind"] == "uses-numeric-user-function"
        ]
        self.assertEqual(11, len(references))
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

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
            "11\n1 2 0.5 0.5\n"
            "40\n1 1 1\n1 1 1\n"
            "41\n1 1 1 1\n1 1 1\n"
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
