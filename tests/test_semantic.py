from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.source_set import SourceSet


def deck(cluster_lines: bytes) -> bytes:
    return (
        b"INPUT\n3\nEND INPUT\n"
        b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        b"MATERIALS\n0\nEND MATERIALS\n"
        b"CLUSTERS\n*type\nsolid\n" + cluster_lines + b"*STOP\nEND CLUSTERS\n"
    )


class SemanticIndexTests(unittest.TestCase):
    def test_unnamed_cluster_uses_source_defined_fallback_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n",
            ).replace(b"*type\nsolid\n*NAME\nply1\n", b"*type\nsolid\n"))
            inspection = SourceSet.read(root).inspection()

        semantic = inspection["semantic_model"]
        cluster = next(
            item for item in semantic["entities"] if item["kind"] == "cluster"
        )
        node = next(
            item for item in semantic["entities"] if item["kind"] == "node"
        )
        node_set = next(
            item for item in semantic["entities"] if item["kind"] == "node-set"
        )
        declaration = next(
            item for item in semantic["entities"]
            if item["kind"] == "cluster-declaration"
        )
        declaration_reference = next(
            item for item in semantic["references"]
            if item["source_entity_id"] == declaration["id"]
        )
        self.assertEqual("noname1", cluster["name"])
        self.assertTrue(cluster["attributes"]["implicit_name"])
        self.assertEqual("cluster:noname1/node:1", node["key"])
        self.assertEqual("cluster:noname1/node-set:edge", node_set["key"])
        self.assertEqual("cluster:noname1", declaration_reference["target_key"])
        self.assertEqual("resolved", declaration_reference["status"])
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_connection_section_layers_resolve_constitutive_identities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*ELEMENT,TYPE=C3D4,ELSET=solid\n1,1,1,1,1\n"
                b"*SECTION,ELSET=solid,LAYERS=2,CONNECTION\n.25,1\n.75,2\n"
            ).replace(
                b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
                b"CONSTITUTIVE\n1\n1 1 0\n1\n1 1 0\nEND CONSTITUTIVE\n"
                b"FAILURE\n4\nEND FAILURE\n",
            ).replace(
                b"MATERIALS\n0\nEND MATERIALS\n",
                b"MATERIALS\n10\n1 0 0\n1 1 1\nEND MATERIALS\n",
            )
            root.write_bytes(raw)
            inspection = SourceSet.read(root).inspection()

        section = next(
            item for item in inspection["semantic_model"]["entities"]
            if item["kind"] == "section"
        )
        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] == section["id"]
            and item["kind"] == "uses-constitutive"
        ]
        self.assertTrue(section["attributes"]["connection"])
        self.assertEqual(
            [1, 2], section["attributes"]["layer_constitutive_ids"],
        )
        self.assertEqual(
            ["constitutive:1", "constitutive:2"],
            [item["target_key"] for item in references],
        )
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_nodal_connection_expands_all_and_qualified_set_lists(self) -> None:
        raw = (
            b"INPUT\n3\nEND INPUT\n"
            b"BOUNDARY\n*type\nmechanical\n*connections\n"
            b"type=nodal, name=tie\nmset=all\nsset=ply1.edge, ply2.edge\n"
            b"END BOUNDARY\nCONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
            b"MATERIALS\n0\nEND MATERIALS\nCLUSTERS\n"
            b"*type\nsolid\n*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n*STOP\n"
            b"*type\nsolid\n*NAME\nply2\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n*STOP\n"
            b"END CLUSTERS\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(raw)
            inspection = SourceSet.read(root).inspection()

        semantic = inspection["semantic_model"]
        connection = next(
            item for item in semantic["entities"]
            if item["kind"] == "connection"
        )
        references = [
            item for item in semantic["references"]
            if item["source_entity_id"] == connection["id"]
        ]
        self.assertEqual(
            ["mset", "mset", "sset", "sset"],
            [item["kind"] for item in references],
        )
        self.assertEqual([
            "cluster:ply1/node-set:edge", "cluster:ply2/node-set:edge",
            "cluster:ply1/node-set:edge", "cluster:ply2/node-set:edge",
        ], [item["target_key"] for item in references])
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_section_layers_resolve_material_identities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*ELEMENT,TYPE=C3D4,ELSET=solid\n"
                b"1,1,1,1,1\n*SECTION,ELSET=solid,LAYERS=2\n.25,1\n.75,2\n"
            ).replace(
                b"MATERIALS\n0\nEND MATERIALS\n",
                b"MATERIALS\n10\n1 0 0\n1 1 1\n"
                b"10\n2 0 0\n2 2 2\nEND MATERIALS\n",
            ).replace(
                b"*NAME\nply1\n",
                b"*NAME\nply1\n*NODE\n1,0,0,0\n",
            )
            root.write_bytes(raw)
            inspection = SourceSet.read(root).inspection()

        section = next(
            item for item in inspection["semantic_model"]["entities"]
            if item["kind"] == "section"
        )
        references = [
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] == section["id"]
            and item["kind"] == "uses-material"
        ]
        self.assertEqual([1, 2], section["attributes"]["layer_material_ids"])
        self.assertEqual([0.25, 0.75], section["attributes"]["layer_thicknesses"])
        self.assertEqual(["material:1", "material:2"], [
            item["target_key"] for item in references
        ])
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_section_header_rows_and_normalized_thicknesses_are_validated(self) -> None:
        mesh = (
            b"*NAME\nply1\n*NODE\n1,0,0,0\n"
            b"*ELEMENT,TYPE=C3D4,ELSET=solid\n1,1,1,1,1\n"
        )
        materials = (
            b"MATERIALS\n10\n1 0 0\n1 1 1\n"
            b"10\n2 0 0\n2 2 2\nEND MATERIALS\n"
        )
        valid = b"*SECTION,ELSET=solid,LAYERS=2\n1,1\n3,2\n"
        invalid = (
            b"*SECTION,LAYERS=1\n1,1\n",
            b"*SECTION,ELSET=solid\n1,1\n",
            b"*SECTION,ELSET=solid,LAYERS=0\n",
            b"*SECTION,ELSET=solid,LAYERS=100000\n",
            b"*SECTION,ELSET=solid,LAYERS=1,OTHER\n1,1\n",
            b"*SECTION,ELSET=solid,ELSET=solid,LAYERS=1\n1,1\n",
            b"*SECTION,ELSET=solid,LAYERS=1,CONNECTION=yes\n1,1\n",
            b"*SECTION,ELSET=abcdefghijklmnopqrstu,LAYERS=1\n1,1\n",
            b"*SECTION,ELSET=solid,LAYERS=2\n1,1\n",
            b"*SECTION,ELSET=solid,LAYERS=1\n1,1,2\n",
            b"*SECTION,ELSET=solid,LAYERS=1\n-1,1\n",
            b"*SECTION,ELSET=solid,LAYERS=1\nNaN,1\n",
            b"*SECTION,ELSET=solid,LAYERS=2\n1D308,1\n1D308,2\n",
            b"*SECTION,ELSET=solid,LAYERS=1\n1,0\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(mesh + valid).replace(
                b"MATERIALS\n0\nEND MATERIALS\n", materials,
            ))
            inspection = SourceSet.read(root).inspection()
            self.assertEqual(0, inspection["summary"]["errors"])
            section = next(
                item for item in inspection["semantic_model"]["entities"]
                if item["kind"] == "section"
            )
            self.assertEqual([0.25, 0.75], section["attributes"]["layer_thicknesses"])
            for index, command in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(mesh + command).replace(
                    b"MATERIALS\n0\nEND MATERIALS\n", materials,
                ))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_global_crack_leading_records_and_named_cluster_are_typed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n"
            ).replace(
                b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
                b"CRACK\n301\n0,10\n3,-ngap\nply1,-approximation\n"
                b"*normal\nEND CRACK\nCONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
            )
            root.write_bytes(raw)
            semantic = SourceSet.read(root).inspection()["semantic_model"]

        record = next(
            item for item in semantic["capability_records"]
            if item["capability_id"] == "block.crack"
        )
        crack = next(item for item in semantic["entities"] if item["kind"] == "crack")
        reference = next(
            item for item in semantic["references"]
            if item["source_entity_id"] == crack["id"]
        )
        self.assertEqual(301, record["parameters"]["type"][0]["value"])
        self.assertEqual(0, record["parameters"]["predefined_count"][0]["value"])
        self.assertEqual(10, record["parameters"]["maximum_count"][0]["value"])
        self.assertEqual(3, record["parameters"]["n_gap"][0]["value"])
        self.assertEqual("ply1", record["parameters"]["cluster"][0]["value"])
        self.assertEqual("cluster:ply1", reference["target_key"])
        self.assertEqual("resolved", reference["status"])

    def test_global_crack_static_validation_rejects_incomplete_or_unsafe_entries(self) -> None:
        mesh = (
            b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
            b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n"
        )
        base = deck(mesh)
        invalid_blocks = {
            "empty": b"CRACK\nEND CRACK\n",
            "missing-end": b"CRACK\n101\n0,1\n6\nply1\n",
            "unsupported-type": b"CRACK\n1\nEND CRACK\n",
            "bad-counts": b"CRACK\n101\n2,1\n6\nply1\nEND CRACK\n",
            "low-gap": b"CRACK\n101\n0,1\n5\nply1\nEND CRACK\n",
            "missing-cluster": b"CRACK\n101\n0,1\n6\nmissing\nEND CRACK\n",
            "zero-normal": b"CRACK\n101\n0,1\n6\nply1\n*normal,0,0,0\nEND CRACK\n",
            "missing-point": b"CRACK\n101\n1,1\n6\nply1\nEND CRACK\n",
        }
        for name, block in invalid_blocks.items():
            raw = base.replace(
                b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
                block + b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
            )
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                root.write_bytes(raw)
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
            self.assertTrue(any(
                item["severity"] == "error" and item["code"] in {"BSAM-E350", "BSAM-E390"}
                for item in diagnostics
            ))

        disabled = base.replace(
            b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
            b"CRACK\n0\nEND CRACK\nCONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "disabled.in"
            root.write_bytes(disabled)
            inspection = SourceSet.read(root).inspection()
        self.assertEqual(0, inspection["summary"]["errors"])

    def test_cluster_commands_emit_uniform_registered_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*DIMENSIONS\n10,5,2,1\n*NAME\nply1\n"
                b"*NODE,NSET=all_nodes\n1,0,0,0\n"
            ))

            semantic = SourceSet.read(root).inspection()["semantic_model"]
            records = [
                item for item in semantic["capability_records"]
                if item["capability_id"].startswith("command.")
            ]

            self.assertEqual(
                [
                    "command.type", "command.dimensions", "command.name",
                    "command.node", "command.stop",
                ],
                [item["capability_id"] for item in records],
            )
            self.assertEqual("solid", records[0]["parameters"]["representation"][0]["value"])
            self.assertEqual("ply1", records[2]["parameters"]["name"][0]["value"])
            self.assertEqual("all_nodes", records[3]["parameters"]["NSET"][0]["value"])
            self.assertTrue(all(
                item["operations"]["parse"] in {"implemented", "verified"}
                and item["operations"]["semantic"] in {"implemented", "verified"}
                for item in records
            ))

    def test_representative_two_cluster_fixture_regression(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "semantic_two_cluster.in"

        inspection = SourceSet.read(fixture).inspection()
        semantic = inspection["semantic_model"]

        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(24, semantic["summary"]["entities"])
        self.assertEqual(26, semantic["summary"]["references"])
        self.assertEqual(26, semantic["summary"]["resolved_references"])
        keys = {item["key"] for item in semantic["entities"]}
        self.assertIn("cluster:lower_ply/node:1", keys)
        self.assertIn("cluster:upper_ply/node:1", keys)

    def test_explicit_fe_entities_and_references_have_stable_locations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NODE,NSET=all_nodes\n"
                b"1,0.,0.,0.\n2,1.,0.,0.\n"
                b"*ELEMENT,TYPE=C3D4,ELSET=solid\n"
                b"10,1,2,1,2\n"
                b"*NSET,NSET=edge\n1,2\n"
                b"*ELSET,ELSET=solid\n10\n"
                b"*SECTION,ELSET=solid,LAYERS=2\n.5,1\n.5,2\n"
            ).replace(
                b"MATERIALS\n0\nEND MATERIALS\n",
                b"MATERIALS\n10\n1 0 0\n1 1 1\n"
                b"10\n2 0 0\n2 2 2\nEND MATERIALS\n",
            ))

            semantic = SourceSet.read(root).inspection()["semantic_model"]

            self.assertEqual("0.6.0", semantic["schema_version"])
            self.assertEqual(
                {
                    "cluster": 1, "cluster-declaration": 1,
                    "element": 1, "element-set": 2,
                    "material": 2, "node": 2, "node-set": 2, "section": 1,
                    "topology-operation": 1,
                },
                semantic["summary"]["entities_by_kind"],
            )
            self.assertEqual(15, semantic["summary"]["references"])
            node = next(
                item for item in semantic["entities"]
                if item["key"] == "cluster:noname1/node:1"
            )
            self.assertEqual("<root>", node["location"]["source"])
            self.assertGreater(node["location"]["byte_end"], node["location"]["byte_start"])
            targets = {item["target_key"] for item in semantic["references"]}
            reference_kinds = {item["kind"] for item in semantic["references"]}
            self.assertIn("cluster:noname1/node-set:all_nodes", targets)
            self.assertIn("cluster:noname1/element-set:solid", targets)
            self.assertIn("assigns-to", reference_kinds)
            self.assertEqual(15, semantic["summary"]["resolved_references"])

    def test_cluster_type_and_dimensions_bind_to_the_following_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*DIMENSIONS\n100,50,4,2\n*NAME\nply1\n*NODE\n1,0,0,0\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            declaration = next(
                item for item in semantic["entities"]
                if item["kind"] == "cluster-declaration"
            )
            dimensions = next(
                item for item in semantic["entities"]
                if item["kind"] == "cluster-dimensions"
            )
            owner_ids = {declaration["id"], dimensions["id"]}
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in owner_ids
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual("solid", declaration["attributes"]["representation"])
            self.assertEqual("100", dimensions["attributes"]["node_capacity"])
            self.assertEqual("2", dimensions["attributes"]["section_capacity"])
            self.assertEqual(
                {"declares-cluster", "configures-cluster"},
                {item["kind"] for item in references},
            )
            self.assertTrue(all(
                item["target_key"] == "cluster:ply1" and item["status"] == "resolved"
                for item in references
            ))

    def test_cluster_type_shape_and_boundaries_are_validated(self) -> None:
        cases = {
            "missing": b"*NODE\n1,0,0,0\n",
            "empty": b"*TYPE\n",
            "unknown": b"*TYPE\nshell\n",
            "extra-row": b"*TYPE\nsolid\nextra\n",
            "second-before-stop": b"*TYPE\nsolid\n*TYPE\nsolid\n",
            "missing-stop": b"*TYPE\nsolid\n*NAME\nply1\n",
        }
        for name, cluster_body in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                raw = deck(b"").replace(
                    b"*type\nsolid\n*STOP\n", cluster_body, 1,
                )
                root.write_bytes(raw)
                inspection = SourceSet.read(root).inspection()
            self.assertIn(
                "BSAM-E310", {item["code"] for item in inspection["diagnostics"]},
            )

    def test_cluster_stop_is_command_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(b"").replace(
                b"*STOP\nEND CLUSTERS", b"*STOP\nunexpected\nEND CLUSTERS",
            ))
            inspection = SourceSet.read(root).inspection()
        self.assertTrue(any(
            item["code"] == "BSAM-E310" and "command-only" in item["message"]
            for item in inspection["diagnostics"]
        ))

    def test_clusters_container_enforces_envelope_and_registered_dispatch(self) -> None:
        base = deck(b"")
        invalid = {
            "empty": base.replace(b"*type\nsolid\n*STOP\n", b"", 1),
            "leading-record": base.replace(
                b"CLUSTERS\n*type\n", b"CLUSTERS\nunexpected\n*type\n", 1,
            ),
            "missing-end": base.replace(b"END CLUSTERS\n", b"", 1),
            "duplicate": base + b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n",
            "unknown-command": base.replace(b"*STOP\n", b"*MYSTERY\n*STOP\n", 1),
        }
        for name, raw in invalid.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                root.write_bytes(raw)
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
            self.assertIn("BSAM-E390", {item["code"] for item in diagnostics})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(base.replace(b"END CLUSTERS", b"END APPROXIMATION"))
            inspection = SourceSet.read(root).inspection()
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertIn("BSAM-W111", {item["code"] for item in inspection["diagnostics"]})

    def test_boundary_container_enforces_envelope_and_registered_dispatch(self) -> None:
        base = deck(b"")
        invalid = {
            "empty": base.replace(b"*type\nmechanical\n", b"", 1),
            "implicit-type": base.replace(b"*type\nmechanical\n", b"mechanical\n", 1),
            "missing-end": base.replace(b"END BOUNDARY\n", b"", 1),
            "duplicate": base + b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
            "unknown-command": base.replace(
                b"END BOUNDARY\n", b"*MYSTERY\nEND BOUNDARY\n", 1,
            ),
        }
        for name, raw in invalid.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                root.write_bytes(raw)
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
            self.assertIn("BSAM-E390", {item["code"] for item in diagnostics})

    def test_cluster_name_shape_reservation_and_uniqueness_are_validated(self) -> None:
        cases = {
            "empty": b"*NAME\n",
            "multiple-tokens": b"*NAME\nply one\n",
            "too-long": b"*NAME\n" + b"p" * 81 + b"\n",
            "reserved": b"*NAME\nMATERIALS\n",
        }
        for name, records in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                root.write_bytes(deck(records))
                inspection = SourceSet.read(root).inspection()
            self.assertIn(
                "BSAM-E310", {item["code"] for item in inspection["diagnostics"]},
            )

    def test_cluster_constitutive_assignment_shape_and_identity_are_validated(self) -> None:
        cases = {
            "empty": b"*CONSTITUTIVE\n",
            "zero": b"*CONSTITUTIVE\n0\n",
            "negative": b"*CONSTITUTIVE\n-1\n",
            "nonnumeric": b"*CONSTITUTIVE\none\n",
            "extra-field": b"*CONSTITUTIVE\n1,2\n",
        }
        for name, records in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + records))
                inspection = SourceSet.read(root).inspection()
            self.assertTrue(any(
                item["code"] in {"BSAM-E300", "BSAM-E301", "BSAM-E310"}
                for item in inspection["diagnostics"]
            ))

    def test_cluster_dimensions_shape_order_and_uniqueness_are_validated(self) -> None:
        cases = {
            "short": b"*DIMENSIONS\n1,1,0\n",
            "negative": b"*DIMENSIONS\n1,-1,0,0\n",
            "nonnumeric": b"*DIMENSIONS\n1,x,0,0\n",
            "duplicate": b"*DIMENSIONS\n1,0,0,0\n*DIMENSIONS\n1,0,0,0\n",
            "late": b"*NODE\n1,0,0,0\n*DIMENSIONS\n1,0,0,0\n",
        }
        for name, records in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + records))
                inspection = SourceSet.read(root).inspection()
            self.assertIn(
                "BSAM-E310", {item["code"] for item in inspection["diagnostics"]},
            )

    def test_cluster_dimensions_capacities_cover_allocated_entities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*DIMENSIONS\n0,0,0,0\n"
                b"*NODE\n1,0,0,0\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,1,1,1\n"
                b"*NSET,NSET=edge\n1\n"
                b"*ELSET,ELSET=solid\n1\n"
                b"*SELECTION,ID=1,TYPE=NODE\nedge\n"
                b"*SECTION,ELSET=solid,LAYERS=1\n1,1\n"
            ))
            inspection = SourceSet.read(root).inspection()
        capacity_messages = [
            item["message"] for item in inspection["diagnostics"]
            if item["code"] == "BSAM-E310" and "DIMENSIONS" in item["message"]
        ]
        self.assertEqual(4, len(capacity_messages))

    def test_explicit_node_and_element_contracts_fail_closed(self) -> None:
        invalid_commands = (
            b"*NODE,OTHER=value\n1,0,0,0\n",
            b"*NODE\n0,0,0,0\n",
            b"*NODE\n1000000,0,0,0\n",
            b"*NODE\n1,NaN,0,0\n",
            b"*ELEMENT\n1,1,1,1,1\n",
            b"*ELEMENT,TYPE=C3D4\n0,1,1,1,1\n",
            b"*ELEMENT,TYPE=C3D4\n1,1,1,1\n",
            b"*ELEMENT,TYPE=C3D4\n1,1,1,1,1000000\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for ordinal, command in enumerate(invalid_commands):
                with self.subTest(ordinal=ordinal):
                    root = Path(directory) / f"invalid-{ordinal}.in"
                    root.write_bytes(deck(b"*NAME\nply1\n" + command))
                    diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

            duplicate = Path(directory) / "duplicate.in"
            duplicate.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n1,1,0,0\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,1,1,1\n1,1,1,1,1\n"
            ))
            duplicate_codes = {
                item["code"] for item in SourceSet.read(duplicate).inspection()["diagnostics"]
            }
            self.assertIn("BSAM-E300", duplicate_codes)

            capacity = Path(directory) / "capacity.in"
            capacity.write_bytes(deck(
                b"*NAME\nply1\n*DIMENSIONS\n1,0,0,0\n"
                b"*NODE\n1,0,0,0\n2,1,0,0\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,1,1,1\n"
            ))
            messages = [
                item["message"]
                for item in SourceSet.read(capacity).inspection()["diagnostics"]
                if item["code"] == "BSAM-E310" and "capacity" in item["message"]
            ]
            self.assertTrue(any("node capacity" in message for message in messages))
            self.assertTrue(any("element capacity" in message for message in messages))

    def test_node_and_element_set_membership_contracts_fail_closed(self) -> None:
        mesh = (
            b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,2,0,0\n4,0,1,0\n"
            b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n2,1,2,3,4\n"
        )
        valid_sets = (
            b"*NSET,NSET=edge\n1,2\n"
            b"*NSET,NSET=odd,GENERATE\n1,3,2\n"
            b"*NSET,NSET=near,BOX\n0,-1,-1,1,0,1\n"
            b"*ELSET,ELSET=solid,GENERATE\n1,2,1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(mesh + valid_sets))
            inspection = SourceSet.read(root).inspection()
            self.assertEqual(0, inspection["summary"]["errors"])
            contains = [
                item for item in inspection["semantic_model"]["references"]
                if item["kind"] == "contains"
            ]
            self.assertEqual(8, len(contains))
            self.assertTrue(all(item["status"] == "resolved" for item in contains))

            invalid_sets = (
                b"*NSET\n1\n",
                b"*NSET,NSET=edge,OTHER\n1\n",
                b"*NSET,NSET=edge,GENERATE,BOX\n1,2,1\n",
                b"*NSET,NSET=edge\n99\n",
                b"*NSET,NSET=edge,GENERATE\n3,1,1\n",
                b"*NSET,NSET=edge,GENERATE\n1,999999,1\n",
                b"*NSET,NSET=edge,BOX\n1,0,0,0,1,1\n",
                b"*ELSET,ELSET=solid,BOX\n1\n",
            )
            for ordinal, command in enumerate(invalid_sets):
                with self.subTest(ordinal=ordinal):
                    invalid = Path(directory) / f"invalid-set-{ordinal}.in"
                    invalid.write_bytes(deck(mesh + command))
                    diagnostics = SourceSet.read(invalid).inspection()["diagnostics"]
                self.assertTrue(any(
                    item["code"] in {"BSAM-E301", "BSAM-E310"}
                    for item in diagnostics
                ))

            duplicate = Path(directory) / "duplicate-members.in"
            duplicate.write_bytes(deck(
                mesh
                + b"*NSET,NSET=edge\n1,2\n*NSET,NSET=edge\n2,3\n"
                + b"*ELSET,ELSET=solid\n1\n*ELSET,ELSET=solid\n1,2\n"
            ))
            duplicate_messages = [
                item["message"]
                for item in SourceSet.read(duplicate).inspection()["diagnostics"]
                if item["code"] == "BSAM-E310" and "duplicate" in item["message"]
            ]
            self.assertEqual(2, len(duplicate_messages))

    def test_include_entities_use_workspace_independent_source_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "model.in"
            include = workspace / "mesh.inc"
            root.write_bytes(deck(b"*INCLUDE,FILE=mesh.inc\n"))
            include.write_bytes(b"*NODE\n7,0,0,0\n*STOP\n")

            semantic = SourceSet.read(root).semantic_index().as_dict()

            node = next(
                item for item in semantic["entities"]
                if item["key"] == "cluster:noname1/node:7"
            )
            self.assertEqual("mesh.inc", node["location"]["source"])
            self.assertIn("@mesh.inc:2", node["id"])

    def test_cluster_scope_and_resolution_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nfirst\n*NODE\n1,0,0,0\n1,1,0,0\n"
                b"*ELEMENT,TYPE=C3D4\n10,1,2,1,1\n"
                b"*STOP\n*TYPE\nsolid\n*NAME\nsecond\n*NODE\n1,0,0,0\n"
                b"*ELEMENT,TYPE=C3D4\n20,1,1,1,1\n"
                b"*NSET,NSET=wrong\n99\n*ELSET,ELSET=99\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            codes = [item["code"] for item in inspection["diagnostics"]]

            self.assertIn("cluster:first/node:1", {item["key"] for item in semantic["entities"]})
            self.assertIn("cluster:second/node:1", {item["key"] for item in semantic["entities"]})
            self.assertEqual(1, codes.count("BSAM-E300"))
            self.assertIn("BSAM-E301", codes)
            self.assertIn("BSAM-E302", codes)
            self.assertIn("BSAM-E303", codes)

    def test_cluster_boundary_and_load_targets_follow_source_lookup_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n"
                b"*NSET,NSET=edge\n1\n"
                b"*BOUNDARY\nedge,1,2,0\n2,3,3,0\n"
                b"*BOUNDARY,FORMAT=LIST\n1,0,0,0\n"
                b"*BOUNDARY,FORMAT=POLYNOMIAL\nedge,1,2,1,0,1\n"
                b"*LOAD\nedge,1,5\n2,2,6\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            kinds = semantic["summary"]["entities_by_kind"]
            references = [
                item for item in semantic["references"]
                if item["kind"] in {"targets-node", "targets-node-set"}
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(4, kinds["nodal-boundary"])
            self.assertEqual(2, kinds["nodal-load"])
            self.assertEqual(6, len(references))
            self.assertEqual(3, sum(item["kind"] == "targets-node" for item in references))
            self.assertEqual(3, sum(item["kind"] == "targets-node-set" for item in references))
            self.assertTrue(all(item["status"] == "resolved" for item in references))

    def test_cluster_boundary_formats_rows_and_safe_targets_are_validated(self) -> None:
        valid = (
            b"*BOUNDARY\nedge,1,3,1D-3\n+2,2,2,-1\n",
            b"*BOUNDARY,FORMAT=LIST\n1,0,1D0,-1\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\nedge,1,2,0,3\n"
            b"edge,3,1,2,1,0,-1\n",
        )
        invalid = (
            b"*BOUNDARY,OTHER=LIST\n1,0,0,0\n",
            b"*BOUNDARY,FORMAT\n1,0,0,0\n",
            b"*BOUNDARY,FORMAT=ABA\n1,1,1,0\n",
            b"*BOUNDARY\nedge 1 1 0\n",
            b"*BOUNDARY\nedge,1,1\n",
            b"*BOUNDARY\nedge,0,1,0\n",
            b"*BOUNDARY\nedge,3,2,0\n",
            b"*BOUNDARY\nedge,1,1,NaN\n",
            b"*BOUNDARY\nthis_node_set_name_is_too_long,1,1,0\n",
            b"*BOUNDARY,FORMAT=LIST\nedge,0,0,0\n",
            b"*BOUNDARY,FORMAT=LIST\n0,0,0,0\n",
            b"*BOUNDARY,FORMAT=LIST\n1,0,0\n",
            b"*BOUNDARY,FORMAT=LIST\n1,0,0,NaN\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\n1,1,1,0,1\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\nmissing,1,1,0,1\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\nedge,0,1,0,1\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\nedge,1,4,0,1\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\nedge,1,1,5,1,2,3,4,5,6\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\nedge,1,1,2,1,2\n",
            b"*BOUNDARY,FORMAT=POLYNOMIAL\nedge,1,1,0,NaN\n",
        )
        prefix = (
            b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n"
            b"*NSET,NSET=edge\n1,2\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, boundary in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(prefix + boundary))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, boundary in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + boundary))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_cluster_load_rows_and_values_are_validated(self) -> None:
        valid = b"*LOAD\nedge,1,1D-3\n1,3,-2\n"
        invalid = (
            b"*LOAD,OTHER\nedge,1,1\n",
            b"*LOAD\nedge,1\n",
            b"*LOAD\nedge,0,1\n",
            b"*LOAD\nedge,4,1\n",
            b"*LOAD\nedge,1,NaN\n",
            b"*LOAD\nthis_node_set_name_is_too_long,1,1\n",
        )
        prefix = b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(prefix + valid))
            self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, load in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + load))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_missing_cluster_boundary_and_load_targets_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*BOUNDARY\n99,1,1,0\nmissing,1,1,0\n"
                b"*BOUNDARY,FORMAT=LIST\n98,0,0,0\n"
                b"*LOAD\nabsent,1,5\n"
            ))

            inspection = SourceSet.read(root).inspection()
            unresolved = [
                item for item in inspection["semantic_model"]["references"]
                if item["status"] == "unresolved"
            ]

            self.assertEqual(4, len(unresolved))
            self.assertTrue(all(item["kind"] in {"targets-node", "targets-node-set"} for item in unresolved))
            self.assertEqual(4, [
                item["code"] for item in inspection["diagnostics"]
            ].count("BSAM-E301"))

    def test_cluster_field_targets_are_source_located_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n"
                b"*NSET,NSET=edge\n1\n"
                b"*FIELD,VARIABLES=2\nedge,10,20\n2,30,40\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            fields = [
                item for item in semantic["entities"] if item["kind"] == "nodal-field"
            ]
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in {field["id"] for field in fields}
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(2, len(fields))
            self.assertEqual({"2"}, {item["attributes"]["variables"] for item in fields})
            self.assertEqual(
                {"targets-node", "targets-node-set"},
                {item["kind"] for item in references},
            )
            self.assertTrue(all(item["status"] == "resolved" for item in references))

    def test_cluster_field_variable_count_rows_and_values_are_validated(self) -> None:
        valid = b"*FIELD,VARIABLES=2\nedge,1D0,-2\n1,3,4\n"
        invalid = (
            b"*FIELD\nedge,1\n",
            b"*FIELD,OTHER=1\nedge,1\n",
            b"*FIELD,VARIABLES=0\nedge\n",
            b"*FIELD,VARIABLES=11\nedge," + b"1," * 10 + b"1\n",
            b"*FIELD,VARIABLES=2\nedge,1\n",
            b"*FIELD,VARIABLES=1\nedge,NaN\n",
            b"*FIELD,VARIABLES=1\nthis_node_set_name_is_too_long,1\n",
        )
        prefix = b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(prefix + valid))
            self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, field in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + field))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_missing_cluster_field_target_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*FIELD,VARIABLES=1\nmissing,10\n"
            ))

            inspection = SourceSet.read(root).inspection()
            fields = [
                item for item in inspection["semantic_model"]["entities"]
                if item["kind"] == "nodal-field"
            ]

            self.assertEqual(1, len(fields))
            self.assertEqual(1, [
                item["code"] for item in inspection["diagnostics"]
            ].count("BSAM-E301"))

    def test_cluster_selections_reference_nodes_elements_and_sets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n"
                b"*ELEMENT,TYPE=C3D4\n10,1,2,1,2\n"
                b"*NSET,NSET=edge\n1\n*ELSET,ELSET=solid\n10\n"
                b"*SELECTION,ID=1\nedge,2\n"
                b"*SELECTION,ID=2,TYPE=ELEMENT\nsolid\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            selections = [
                item for item in semantic["entities"] if item["kind"] == "selection"
            ]
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in {selection["id"] for selection in selections}
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(2, len(selections))
            self.assertEqual(
                {"selects-node", "selects-node-set", "selects-element-set"},
                {item["kind"] for item in references},
            )
            self.assertTrue(all(item["status"] == "resolved" for item in references))

    def test_missing_and_duplicate_cluster_selections_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*SELECTION,ID=1\n99\n*SELECTION,ID=1\n1\n"
            ))

            inspection = SourceSet.read(root).inspection()
            codes = [item["code"] for item in inspection["diagnostics"]]

            self.assertEqual(1, codes.count("BSAM-E300"))
            self.assertEqual(1, codes.count("BSAM-E301"))

    def test_cluster_selection_id_type_body_and_capacity_are_validated(self) -> None:
        cases = {
            "missing-id": b"*SELECTION,TYPE=NODE\nedge\n",
            "zero-id": b"*SELECTION,ID=0,TYPE=NODE\nedge\n",
            "over-capacity": b"*SELECTION,ID=2,TYPE=NODE\nedge\n",
            "case-sensitive-type": b"*SELECTION,ID=1,TYPE=element\n1\n",
            "empty-body": b"*SELECTION,ID=1,TYPE=NODE\n",
        }
        for name, selection in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "model.in"
                root.write_bytes(deck(
                    b"*NAME\nply1\n*DIMENSIONS\n1,0,1,0\n"
                    b"*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n" + selection
                ))
                inspection = SourceSet.read(root).inspection()
            self.assertIn(
                "BSAM-E310", {item["code"] for item in inspection["diagnostics"]},
            )

    def test_cluster_selection_enforces_ten_named_set_limit(self) -> None:
        set_names = [f"set{index}" for index in range(1, 12)]
        definitions = b"".join(
            f"*NSET,NSET={name}\n1\n".encode("ascii") for name in set_names
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*DIMENSIONS\n1,0,1,0\n"
                b"*NODE\n1,0,0,0\n" + definitions
                + b"*SELECTION,ID=1,TYPE=NODE\n"
                + ",".join(set_names).encode("ascii") + b"\n"
            ))
            inspection = SourceSet.read(root).inspection()
        messages = [
            item["message"] for item in inspection["diagnostics"]
            if item["code"] == "BSAM-E310"
        ]
        self.assertTrue(any("at most ten" in message for message in messages))

    def test_crack_region_element_set_dependency_is_source_located(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n*ELSET,ELSET=region\n1\n"
                b"*CRACK REGION,ADD,ELSET=region\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            region = next(
                item for item in semantic["entities"] if item["kind"] == "crack-region"
            )
            reference = next(
                item for item in semantic["references"]
                if item["source_entity_id"] == region["id"]
            )

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual("targets-element-set", reference["kind"])
            self.assertEqual("cluster:ply1/element-set:region", reference["target_key"])

    def test_spatial_exclusion_and_crack_region_selectors_target_the_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*EXCLUSION,PLANE,OUTSIDE\n0,0,0,0,0,1,.1\n"
                b"*CRACK REGION,ADD,SPHERE\n0,0,0,2\n"
                b"*CRACK REGION,REMOVE,CYLINDER\n0,0,0,0,0,1,2\n"
                b"*CRACK REGION,BOX\n-1,-1,-1,1,1,1\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            exclusions = [
                item for item in semantic["entities"]
                if item["kind"] == "exclusion-region"
            ]
            regions = [
                item for item in semantic["entities"]
                if item["kind"] == "crack-region"
            ]
            owner_ids = {item["id"] for item in [*exclusions, *regions]}
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in owner_ids
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual("plane", exclusions[0]["attributes"]["shape"])
            self.assertEqual("outside", exclusions[0]["attributes"]["side"])
            self.assertEqual(
                {"sphere", "cylinder", "box"},
                {item["attributes"]["selector"] for item in regions},
            )
            self.assertEqual(4, len(references))
            self.assertTrue(all(
                item["kind"] == "targets-cluster"
                and item["target_key"] == "cluster:ply1"
                and item["status"] == "resolved"
                for item in references
            ))

    def test_cluster_crack_variants_and_blocked_definition_are_validated(self) -> None:
        prefix = (
            b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
            b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n*ELSET,ELSET=region\n1\n"
        )
        valid = (
            b"*CRACK REGION,ELSET=region\n",
            b"*CRACK REGION,ADD,BOX\n-1,-1,-1,1,1,1\n",
            b"*CRACK REGION,REMOVE,SPHERE\n0,0,0,1D0\n",
            b"*CRACK REGION,CYLINDER\n0,0,0,0,0,1,1\n",
            b"*CRACK SPACING,STRICT\n",
            b"*CRACK SPACING,VALUE=0.1\n",
            b"*CRACK INITIATION,LOCATION=INTEGRATION POINTS\n",
            b"*CRACK INITIATION,LOCATION=NODES\n",
            b"*CRACK INITIATION,LOCATION=CENTER\n",
            b"*CRACK FUNCTION\n",
            b"*CRACK FUNCTION,TYPE=SIMPLE\n",
            b"*CRACK FUNCTION,TYPE=WEIGHTED\n",
        )
        invalid = (
            b"*CRACK DEFINITION,TYPE=PLANE\n0,0,0,0,0,1\n",
            b"*CRACK\n",
            b"*CRACK INITIATION\n",
            b"*CRACK INITIATION,LOCATION=OTHER\n",
            b"*CRACK INITIATION,LOCATION=NODES\nunexpected\n",
            b"*CRACK FUNCTION,TYPE=OTHER\n",
            b"*CRACK FUNCTION,OTHER\n",
            b"*CRACK FUNCTION\nunexpected\n",
            b"*CRACK REGION\n",
            b"*CRACK REGION,ADD,REMOVE,ELSET=region\n",
            b"*CRACK REGION,ELSET=region,BOX\n0,0,0,1,1,1\n",
            b"*CRACK REGION,ELSET=abcdefghijklmnopqrstu\n",
            b"*CRACK REGION,ELSET=region\nunexpected\n",
            b"*CRACK REGION,BOX\n",
            b"*CRACK REGION,BOX\n** unsafe direct-read row\n0,0,0,1,1,1\n",
            b"*CRACK REGION,BOX\n0,0,0,NaN,1,1\n",
            b"*CRACK REGION,BOX\n1,0,0,0,1,1\n",
            b"*CRACK REGION,SPHERE\n0,0,0,0\n",
            b"*CRACK REGION,CYLINDER\n0,0,0,0,0,0,1\n",
            b"*CRACK REGION,CYLINDER\n0,0,0,0,0,1,-1\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, crack in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(prefix + crack))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, crack in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + crack))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_exclusion_variants_and_geometry_are_validated(self) -> None:
        valid = (
            b"*EXCLUSION\n0,0,0,1,1,1\n",
            b"*EXCLUSION,PLANE,OUTSIDE\n0,0,0,0,0,1,0\n",
            b"*EXCLUSION,PREVIOUS\n1D-3\n",
        )
        invalid = (
            b"*EXCLUSION,BOX,PLANE\n0,0,0,1,1,1\n",
            b"*EXCLUSION,PREVIOUS,INSIDE\n1\n",
            b"*EXCLUSION,OTHER\n0,0,0,1,1,1\n",
            b"*EXCLUSION\n1,0,0,0,1,1\n",
            b"*EXCLUSION,PLANE\n0,0,0,0,0,0,1\n",
            b"*EXCLUSION,PLANE\n0,0,0,0,0,1,-1\n",
            b"*EXCLUSION,PREVIOUS\n0\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, exclusion in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + exclusion))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, exclusion in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + exclusion))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_build_and_stop_are_source_located_topology_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*BUILD\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            operations = [
                item for item in semantic["entities"]
                if item["kind"] == "topology-operation"
            ]
            operation_ids = {item["id"] for item in operations}
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in operation_ids
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(
                {"build", "stop"},
                {item["attributes"]["operation"] for item in operations},
            )
            self.assertEqual(2, len(references))
            self.assertTrue(all(
                item["kind"] == "targets-cluster"
                and item["target_key"] == "cluster:ply1"
                and item["status"] == "resolved"
                for item in references
            ))

    def test_flip_command_line_mapping_and_body_are_validated(self) -> None:
        cases = {
            "lowercase-value": b"*FLIP,TYPE=xy\n",
            "unknown-option": b"*FLIP,AXIS=XY\n",
            "attached-record": b"*FLIP,TYPE=XY\nunexpected\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, flip in cases.items():
                with self.subTest(name=name):
                    root = Path(directory) / f"{name}.in"
                    root.write_bytes(deck(b"*NAME\nply1\n*NODE\n1,0,0,0\n" + flip))
                    diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                    self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_transform_command_line_options_and_body_are_validated(self) -> None:
        valid = (b"*TRANSFORM,INERTIA\n", b"*TRANSFORM,FLATTEN=1D-3,INERTIA\n")
        invalid = (
            b"*TRANSFORM\n",
            b"*TRANSFORM,OTHER\n",
            b"*TRANSFORM,INERTIA,FLATTEN\n",
            b"*TRANSFORM,INERTIA,FLATTEN=NaN\n",
            b"*TRANSFORM,INERTIA\nunexpected\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, transform in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n*NODE\n1,0,0,0\n" + transform))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, transform in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n*NODE\n1,0,0,0\n" + transform))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_spacing_command_line_modes_and_values_are_validated(self) -> None:
        valid = (b"*SPACING\n", b"*SPACING,STRICT\n", b"*SPACING,RELAXED\n", b"*SPACING,VALUE=1D-3\n")
        invalid = (
            b"*SPACING,VALUE=0\n", b"*SPACING,VALUE=NaN\n",
            b"*SPACING,STRICT,RELAXED\n", b"*SPACING,OTHER\n",
            b"*SPACING\nunexpected\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, spacing in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + spacing))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, spacing in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + spacing))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_build_rejects_data_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*BUILD\nunexpected\n"
            ))
            diagnostics = SourceSet.read(root).inspection()["diagnostics"]
        self.assertTrue(any(
            item["code"] == "BSAM-E310" and "BUILD is command-only" in item["message"]
            for item in diagnostics
        ))

    def test_tolerance_and_spacing_are_source_located_cluster_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*TOLERANCE,TYPE=ITOL\n1e-9\n"
                b"*SPACING,VALUE=0.25\n"
                b"*CRACK SPACING,RELAXED\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            settings = [
                item for item in semantic["entities"]
                if item["kind"] == "cluster-setting"
            ]
            setting_ids = {item["id"] for item in settings}
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in setting_ids
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(3, len(settings))
            self.assertEqual("1e-9", settings[0]["attributes"]["value"])
            self.assertEqual("value", settings[1]["attributes"]["mode"])
            self.assertEqual("0.25", settings[1]["attributes"]["value"])
            self.assertEqual("relaxed", settings[2]["attributes"]["mode"])
            self.assertEqual(3, len(references))
            self.assertTrue(all(item["status"] == "resolved" for item in references))

    def test_tolerance_type_and_value_record_are_validated(self) -> None:
        valid = (b"*TOLERANCE\n0\n", b"*TOLERANCE,TYPE=FTOL\n1D-10\n")
        invalid = (
            b"*TOLERANCE,TYPE=ftol\n1e-10\n",
            b"*TOLERANCE,OTHER=PTOL\n1e-6\n",
            b"*TOLERANCE\n",
            b"*TOLERANCE\n-1\n",
            b"*TOLERANCE\nNaN\n",
            b"*TOLERANCE\n1\n2\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, tolerance in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + tolerance))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, tolerance in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(b"*NAME\nply1\n" + tolerance))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_orientation_records_resolve_node_element_and_set_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n2,1,2,3,4\n"
                b"*NSET,NSET=edge\n1\n*ELSET,ELSET=solid\n1\n"
                b"*ORIENTATION,NAME=ORI-NODE\nedge,1,0,0,0,0,1,.5\n2,1,0,0,0,0,1,.5\n"
                b"*ORIENTATION,NAME=ORI-ELE\nsolid,1,0,0,0,0,1,.5\n2,1,0,0,0,0,1,.5\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            orientations = [
                item for item in semantic["entities"]
                if item["kind"] == "orientation-record"
            ]
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in {entry["id"] for entry in orientations}
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(4, len(orientations))
            self.assertEqual(
                {"targets-node", "targets-node-set", "targets-element", "targets-element-set"},
                {item["kind"] for item in references},
            )
            self.assertTrue(all(item["status"] == "resolved" for item in references))

    def test_orientation_header_rows_and_element_vectors_are_validated(self) -> None:
        valid = (
            b"*ORIENTATION,NAME=ORI\nedge,0,0,0,0,0,0,.5\n",
            b"*ORIENTATION,NAME=ORI-ELE\nsolid,1,0,0,0,0,1,.5\n",
        )
        invalid = (
            b"*ORIENTATION\nedge,1,0,0,0,0,1,.5\n",
            b"*ORIENTATION,NAME=OTHER\nedge,1,0,0,0,0,1,.5\n",
            b"*ORIENTATION,NAME=ORI\nedge,1,0,0\n",
            b"*ORIENTATION,NAME=ORI\nedge,1,0,0,0,0,1,NaN\n",
            b"*ORIENTATION,NAME=ORI-ELE\nsolid,0,0,0,0,0,1,.5\n",
            b"*ORIENTATION,NAME=ORI-ELE\nsolid,1,0,0,1,0,0,.5\n",
        )
        prefix = (
            b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
            b"*NSET,NSET=edge\n1\n*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n*ELSET,ELSET=solid\n1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, orientation in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(prefix + orientation))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, orientation in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + orientation))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_coordinate_operations_and_integration_dependencies_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                b"*ELEMENT,TYPE=X3D8\n1,1,2,3,4,1,2,3,4\n"
                b"*NSET,NSET=edge\n1,2\n*SHIFT,NSET=edge\n1,0,0\n"
                b"*SCALE,NSET=edge\n2,2,2\n*INTEGRATION\n1,2\n"
                b"-.5,0,0,1\n.5,0,0,1\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(2, semantic["summary"]["entities_by_kind"]["coordinate-operation"])
            self.assertEqual(1, semantic["summary"]["entities_by_kind"]["integration-scheme"])
            reference_kinds = {item["kind"] for item in semantic["references"]}
            self.assertTrue({"targets-node-set", "targets-element"} <= reference_kinds)
            self.assertEqual(
                {"structural-reference"},
                {
                    item["classification"] for item in semantic["references"]
                    if item["kind"] in {"targets-node-set", "targets-element"}
                },
            )

    def test_missing_coordinate_and_integration_targets_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*SHIFT,NSET=missing\n1,0,0\n*INTEGRATION\n99,1\n0,0,0,1\n"
            ))
            inspection = SourceSet.read(root).inspection()
            self.assertEqual(2, [
                item["code"] for item in inspection["diagnostics"]
            ].count("BSAM-E301"))

    def test_integration_headers_points_targets_and_replacement_are_validated(self) -> None:
        nodes = b"".join(
            f"{label},{label},0,0\n".encode() for label in range(1, 9)
        )
        mesh = (
            b"*NAME\nply1\n*NODE\n" + nodes
            + b"*ELEMENT,TYPE=X3D8\n1,1,2,3,4,5,6,7,8\n"
            b"*ELEMENT,TYPE=Y3D8\n2,1,2,3,4,5,6,7,8\n"
        )
        valid = (
            b"*INTEGRATION\n1,1\n0,0,0,1D0\n2,1\n0,0,0,1\n"
            b"1,2\n-.5,0,0,1\n.5,0,0,1\n"
        )
        invalid = (
            b"*INTEGRATION,TYPE=CUSTOM\n1,1\n0,0,0,1\n",
            b"*INTEGRATION\n1,1,2\n0,0,0,1\n",
            b"*INTEGRATION\n0,1\n0,0,0,1\n",
            b"*INTEGRATION\n1,0\n",
            b"*INTEGRATION\n1,100001\n",
            b"*INTEGRATION\n99,1\n0,0,0,1\n",
            b"*ELEMENT,TYPE=C3D8\n3,1,2,3,4,5,6,7,8\n"
            b"*INTEGRATION\n3,1\n0,0,0,1\n",
            b"*INTEGRATION\n1,2\n0,0,0,1\n",
            b"*INTEGRATION\n1,1\n** missing point\n",
            b"*INTEGRATION\n1,1\n0,0,1\n",
            b"*INTEGRATION\n1,1\n0,0,0,NaN\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(mesh + valid))
            inspection = SourceSet.read(root).inspection()
            self.assertEqual(0, inspection["summary"]["errors"])
            schemes = [
                item for item in inspection["semantic_model"]["entities"]
                if item["kind"] == "integration-scheme"
            ]
            self.assertEqual([1, 1, 2], [
                item["attributes"]["replacement_order"] for item in schemes
            ])
            self.assertEqual(2, len(schemes[-1]["attributes"]["points"]))
            for index, command in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(mesh + command))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_all_node_coordinate_operations_target_the_current_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*SHIFT,ALL\n1,2,3\n*SCALE\n2,3,4\n"
                b"*FLIP,TYPE=YZ\n*TRANSFORM,INERTIA\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            operations = {
                item["attributes"]["operation"]: item
                for item in semantic["entities"]
                if item["kind"] == "coordinate-operation"
            }
            operation_ids = {item["id"] for item in operations.values()}
            targets = [
                item for item in semantic["references"]
                if item["source_entity_id"] in operation_ids
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual({"shift", "scale", "flip", "transform"}, set(operations))
            self.assertEqual(["1", "2", "3"], operations["shift"]["attributes"]["values"])
            self.assertEqual("YZ", operations["flip"]["attributes"]["mapping"])
            self.assertTrue(operations["transform"]["attributes"]["inertia"])
            self.assertEqual(4, sum(
                item["kind"] == "targets-cluster"
                and item["target_key"] == "cluster:ply1"
                and item["status"] == "resolved"
                for item in targets
            ))

    def test_shift_and_scale_targeting_and_vectors_are_validated(self) -> None:
        valid = (
            b"*SHIFT\n1,2D0,-3\n", b"*SHIFT,ALL\n0,0,0\n",
            b"*SCALE,NSET=edge\n-1,2,3\n",
        )
        invalid = (
            b"*SHIFT,ALL,NSET=edge\n1,2,3\n",
            b"*SHIFT,OTHER\n1,2,3\n",
            b"*SHIFT\n1,2\n",
            b"*SHIFT\n1,2,NaN\n",
            b"*SHIFT\n1,2,3\n4,5,6\n",
            b"*SCALE\n1,0,1\n",
        )
        prefix = b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
        with tempfile.TemporaryDirectory() as directory:
            for index, operation in enumerate(valid):
                root = Path(directory) / f"valid-{index}.in"
                root.write_bytes(deck(prefix + operation))
                self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, operation in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + operation))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_ngen_and_ncopy_dependencies_and_output_sets_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n5,4,0,0\n21,0,1,0\n"
                b"25,4,1,0\n31,0,2,0\n35,4,2,0\n41,0,3,0\n45,4,3,0\n"
                b"*NSET,NSET=starts\n21,31\n*NSET,NSET=ends\n25,35\n"
                b"*NGEN,NSET=line\n1,5,1\nstarts,ends,1\n"
                b"*NGEN,ARC\n0,0,0\n41,45,1\n"
                b"*NCOPY,NSET=copies\nstarts,2,100,0,0,1\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            generations = [
                item for item in semantic["entities"] if item["kind"] == "node-generation"
            ]
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in {entry["id"] for entry in generations}
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(3, len(generations))
            self.assertTrue({
                "uses-node-endpoint", "uses-node-set-endpoint", "copies-node-set",
            } <= {item["kind"] for item in references})
            keys = {item["key"] for item in semantic["entities"]}
            self.assertTrue({
                "cluster:ply1/node-set:line", "cluster:ply1/node-set:copies",
            } <= keys)
            entity_by_id = {item["id"]: item for item in semantic["entities"]}
            line_members = {
                entity_by_id[item["source_entity_id"]]["name"]
                for item in semantic["references"]
                if item["kind"] == "member-of"
                and item["target_key"] == "cluster:ply1/node-set:line"
            }
            copy_members = {
                entity_by_id[item["source_entity_id"]]["name"]
                for item in semantic["references"]
                if item["kind"] == "member-of"
                and item["target_key"] == "cluster:ply1/node-set:copies"
            }
            self.assertEqual(
                {str(label) for label in range(1, 6)}
                | {str(label) for label in range(21, 26)}
                | {str(label) for label in range(31, 36)},
                line_members,
            )
            self.assertEqual({"121", "131", "221", "231"}, copy_members)

    def test_ngen_headers_variants_geometry_and_coordinates_are_validated(self) -> None:
        prefix = (
            b"*NAME\nply1\n*NODE\n"
            b"1,0,0,0\n5,4,0,0\n11,0,2,0\n15,4,2,0\n"
            b"21,1,0,0\n25,0,1,0\n26,-1,0,0\n200002,10,0,0\n"
            b"*NSET,NSET=starts\n11\n*NSET,NSET=ends\n15\n"
            b"*NSET,NSET=ends2\n15,25\n*NSET,NSET=source\n1,5\n"
        )
        valid = (
            b"*NGEN,NSET=line,BIAS=2\n1,5,1\n"
            b"*NGEN,NSET=paired\nstarts,ends,1\n"
            b"*NGEN,NSET=arc,ARC\n0,0,0\n21,25,1\n"
            b"*NCOPY,NSET=copies\nsource,1,100,0,0,1\n"
            b"*NGEN,NSET=chained\n101,105,1\n"
        )
        invalid = (
            b"*NGEN,OTHER\n1,5,1\n",
            b"*NGEN,BIAS=1,BIAS=2\n1,5,1\n",
            b"*NGEN,NSET=abcdefghijklmnopqrstu\n1,5,1\n",
            b"*NGEN,BIAS=0\n1,5,1\n",
            b"*NGEN,BIAS=NaN\n1,5,1\n",
            b"*NGEN,ARC=yes\n0,0,0\n21,25,1\n",
            b"*NGEN\n1,5\n",
            b"*NGEN\n1 5 1\n",
            b"*NGEN\n1,5,0\n",
            b"*NGEN\n5,1,1\n",
            b"*NGEN\n99,100,1\n",
            b"*NGEN\nstarts,ends2,1\n",
            b"*NGEN\n1,200002,1\n",
            b"*NODE\n3,2,0,0\n*NGEN\n1,5,1\n",
            b"*NGEN,ARC\n0,0,0\n",
            b"*NGEN,ARC\n0,0,0\n21,25,1\n21,25,1\n",
            b"*NGEN,ARC\n0,0,0\n** unsafe consumed row\n21,25,1\n",
            b"*NGEN,ARC\n0,0,NaN\n21,25,1\n",
            b"*NGEN,ARC\n0,0,0\n21,26,1\n",
            b"*NGEN,ARC\n0,0,0\n21,21,1\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(prefix + valid))
            inspection = SourceSet.read(root).inspection()
            self.assertEqual(0, inspection["summary"]["errors"])
            nodes = {
                item["name"]: item for item in inspection["semantic_model"]["entities"]
                if item["kind"] == "node"
            }
            self.assertEqual([1.0, 0.0, 0.0], nodes["3"]["attributes"]["coordinates"])
            self.assertEqual([2.0, 0.0, 1.0], nodes["103"]["attributes"]["coordinates"])
            self.assertAlmostEqual(
                2 ** -0.5, nodes["23"]["attributes"]["coordinates"][0], places=12,
            )
            self.assertAlmostEqual(
                2 ** -0.5, nodes["23"]["attributes"]["coordinates"][1], places=12,
            )
            for index, command in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + command))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_generated_node_identities_resolve_downstream_connectivity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n5,4,0,0\n"
                b"*NSET,NSET=source\n1\n*NGEN,NSET=line\n1,5,1\n"
                b"*NCOPY,NSET=copies\nsource,1,100,0,0,1\n"
                b"*ELEMENT,TYPE=C3D4\n1,2,3,4,5\n2,101,2,3,4\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            nodes = {
                item["key"]: item for item in semantic["entities"] if item["kind"] == "node"
            }

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual("ngen", nodes["cluster:ply1/node:2"]["attributes"]["generated_by"])
            self.assertEqual("ncopy", nodes["cluster:ply1/node:101"]["attributes"]["generated_by"])
            self.assertEqual(8, sum(
                item["kind"] == "connectivity" and item["status"] == "resolved"
                for item in semantic["references"]
            ))

    def test_elgen_identities_and_shifted_connectivity_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                b"11,2,0,0\n12,3,0,0\n13,2,1,0\n14,2,0,1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n"
                b"*ELGEN,TYPE=C3D4\n1,2,1,1,10,0,0\n"
                b"*ELSET,ELSET=generated\n2\n"
            ))

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            generated = next(
                item for item in semantic["entities"]
                if item["key"] == "cluster:ply1/element:2"
            )

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual("elgen", generated["attributes"]["generated_by"])
            self.assertEqual(["11", "12", "13", "14"], generated["attributes"]["connectivity"])
            self.assertEqual(4, sum(
                item["source_entity_id"] == generated["id"]
                and item["status"] == "resolved"
                for item in semantic["references"]
            ))

    def test_elgen_missing_shifted_connectivity_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n"
                b"*ELGEN,TYPE=C3D4\n1,2,1,1,10,0,0\n"
            ))
            inspection = SourceSet.read(root).inspection()
            self.assertEqual(4, [
                item["code"] for item in inspection["diagnostics"]
            ].count("BSAM-E301"))

    def test_elgen_header_rows_seed_grid_and_connectivity_are_validated(self) -> None:
        mesh = (
            b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
            b"11,2,0,0\n12,3,0,0\n13,2,1,0\n14,2,0,1\n"
            b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n"
        )
        valid = b"*ELGEN,TYPE=C3D4\n1,2,1,1,10,0,0\n"
        invalid = (
            b"*ELGEN\n1,2,1,1,10,0,0\n",
            b"*ELGEN,TYPE=B3D10\n1,2,1,1,10,0,0\n",
            b"*ELGEN,TYPE=C3D4,ELSET=made\n1,2,1,1,10,0,0\n",
            b"*ELGEN,TYPE=C3D4\n1,2,1,1,10,0\n",
            b"*ELGEN,TYPE=C3D4\n1,0,1,1,10,0,0\n",
            b"*ELGEN,TYPE=C3D4\n1,100002,1,1,10,0,0\n",
            b"*ELGEN,TYPE=C3D4\n99,2,1,1,10,0,0\n",
            b"*ELGEN,TYPE=C3D8\n1,2,1,1,10,0,0\n",
            b"*ELGEN,TYPE=C3D4\n1,2,1,1,100,0,0\n",
            b"*ELEMENT,TYPE=C3D4\n2,11,12,13,14\n"
            b"*ELGEN,TYPE=C3D4\n1,2,1,1,10,0,0\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(mesh + valid))
            self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, command in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(mesh + command))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_missing_ngen_and_ncopy_sources_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*NGEN\n1,99,1\n*NCOPY\nmissing,1,10,0,0,1\n"
            ))
            inspection = SourceSet.read(root).inspection()
            self.assertEqual(2, [
                item["code"] for item in inspection["diagnostics"]
            ].count("BSAM-E301"))

    def test_boundary_connection_loading_and_crack_references_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n*NSET,NSET=edge\n1\n"
            ).replace(
                b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
                b"BOUNDARY\n*type\nmechanical\n"
                b"*clusters\nPLY1\n"
                b"*boundary condition\n"
                b"type=disp, comp=x, name=bc1, value=0, nset=PLY1.edge\n"
                b"type=temp, name=heat, value=10\n"
                b"*connections\n"
                b"type=-2, name=penalty\n"
                b"mset=PLY1.edge, Material=1, Constitutive=1, Failure=1\n"
                b"last=PLY1\n"
                b"*loading sequence\n"
                b"type=Static, name=step1, nstep=1, incr=1\n"
                b"change=bc1, type=disp, value=1\n"
                b"END BOUNDARY\n",
            ).replace(
                b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
                b"CONSTITUTIVE\n1\n\t1 1 0\nEND CONSTITUTIVE\n"
                b"FAILURE\n4\nEND FAILURE\n"
                b"CRACK\n301\n\t0 1 0 0\n\t2 -ngap\n\t1 -approximation\nEND CRACK\n",
            ).replace(
                b"MATERIALS\n0\nEND MATERIALS\n",
                b"MATERIALS\n999\nE11=1\n*end\nEND MATERIALS\n",
            )
            root.write_bytes(raw)

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            kinds = semantic["summary"]["entities_by_kind"]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(2, kinds["boundary-condition"])
            self.assertEqual(1, kinds["connection"])
            self.assertEqual(1, kinds["load-change"])
            self.assertEqual(1, kinds["crack"])
            self.assertEqual(1, kinds["cluster-selection"])
            reference_kinds = {item["kind"] for item in semantic["references"]}
            self.assertTrue({
                "targets-node-set", "mset", "uses-material", "uses-constitutive",
                "uses-failure", "terminal-cluster",
                "changes-boundary-condition", "targets-cluster", "selects-cluster",
            } <= reference_kinds)
            heat = next(
                item for item in semantic["entities"]
                if item["kind"] == "boundary-condition" and item["name"] == "heat"
            )
            self.assertEqual(
                ["cluster:ply1"],
                [
                    item["target_key"] for item in semantic["references"]
                    if item["source_entity_id"] == heat["id"]
                    and item["kind"] == "targets-cluster"
                ],
            )

    def test_missing_boundary_and_loading_targets_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(b"*NAME\nply1\n*NODE\n1,0,0,0\n").replace(
                b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
                b"BOUNDARY\n*type\nmechanical\n"
                b"*boundary condition\n"
                b"type=disp, comp=x, name=bc1, value=0, nset=PLY1.missing\n"
                b"*loading sequence\ntype=Static, name=step1, nstep=1, incr=1\n"
                b"change=unknown, type=disp, value=1\n"
                b"END BOUNDARY\n",
            )
            root.write_bytes(raw)

            inspection = SourceSet.read(root).inspection()
            errors = [item for item in inspection["diagnostics"] if item["severity"] == "error"]

            self.assertEqual(2, len(errors))
            self.assertTrue(all(item["code"] == "BSAM-E301" for item in errors))

    def test_boundary_cluster_selection_resolves_all_and_reports_missing_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n"
                b"*STOP\n*TYPE\nsolid\n*NAME\nply2\n*NODE\n1,0,0,0\n"
            ).replace(
                b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
                b"BOUNDARY\n*type\nmechanical\n"
                b"*clusters\nall\n*clusters\nply1,missing\nEND BOUNDARY\n",
            )
            root.write_bytes(raw)

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            cluster_refs = [
                item for item in semantic["references"]
                if item["kind"] == "selects-cluster"
            ]

            self.assertEqual(2, semantic["summary"]["entities_by_kind"]["cluster-selection"])
            self.assertEqual(4, len(cluster_refs))
            self.assertEqual(3, sum(item["status"] == "resolved" for item in cluster_refs))
            self.assertEqual(1, [
                item["code"] for item in inspection["diagnostics"]
            ].count("BSAM-E301"))

    def test_boundary_name_optional_record_and_constraints_are_validated(self) -> None:
        valid_empty = deck(b"*NAME\nply1\n").replace(
            b"*type\nmechanical\nEND BOUNDARY",
            b"*type\nmechanical\n*name\nEND BOUNDARY",
        )
        invalid_records = {
            "multiple-records": b"first\nsecond\n",
            "multiple-tokens": b"first case\n",
            "too-long": b"x" * 81 + b"\n",
            "reserved": b"MATERIALS\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(valid_empty)
            self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for name, name_body in invalid_records.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"{name}.in"
                    path.write_bytes(deck(b"*NAME\nply1\n").replace(
                        b"*type\nmechanical\nEND BOUNDARY",
                        b"*type\nmechanical\n*name\n" + name_body + b"END BOUNDARY",
                    ))
                    diagnostics = SourceSet.read(path).inspection()["diagnostics"]
                    self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_boundary_type_mechanical_and_thermal_records_are_validated(self) -> None:
        valid_bodies = {
            "mechanical": b"mechanical\n",
            "mechanical-options": b"mechanical\nGEO_NL, FIBER_ROT\n",
            "thermal": b"thermal\n-2.5D+1\n",
            "thermal-options": b"thermo-mechanical\n0\nDLM_NORMAL_ROT MIC_NORMAL_ROT\n",
        }
        invalid_bodies = {
            "missing-type": b"",
            "short-type": b"mec\n",
            "unknown-type": b"dynamic\n",
            "mechanical-extra-row": b"mechanical\nGEO_NL\nFIBER_ROT\n",
            "unknown-option": b"mechanical\nGEO_NL, UNKNOWN\n",
            "thermal-missing-temperature": b"thermal\n",
            "thermal-invalid-temperature": b"thermal\nNaN\n",
            "thermal-extra-row": b"thermal\n0\nGEO_NL\nFIBER_ROT\n",
            "blocked-contact": b"contact\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, type_body in valid_bodies.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"valid-{name}.in"
                    path.write_bytes(deck(b"*NAME\nply1\n").replace(
                        b"*type\nmechanical\nEND BOUNDARY",
                        b"*type\n" + type_body + b"END BOUNDARY",
                    ))
                    self.assertEqual(
                        0, SourceSet.read(path).inspection()["summary"]["errors"],
                    )
            for name, type_body in invalid_bodies.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"invalid-{name}.in"
                    path.write_bytes(deck(b"*NAME\nply1\n").replace(
                        b"*type\nmechanical\nEND BOUNDARY",
                        b"*type\n" + type_body + b"END BOUNDARY",
                    ))
                    diagnostics = SourceSet.read(path).inspection()["diagnostics"]
                    self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_boundary_g_control_options_and_safe_ranges_are_validated(self) -> None:
        valid_commands = {
            "empty": b"*g-control\n",
            "full": (
                b"*g-control,UPDATE,DAMP,G_ITER=20,GMIN=0,GMAX=2,"
                b"GTHR=1D-3,NO_DAMAGE_LOCK\n"
            ),
            "source-prefixes": b"*g-control G_IT 3 G_TH 0 GMAX 1 GTHR .5 UPDA\n",
        }
        invalid_commands = {
            "body-record": b"*g-control\nGMIN=0\n",
            "unknown": b"*g-control,OTHER=1\n",
            "missing-value": b"*g-control,GMAX\n",
            "noninteger-iterations": b"*g-control,G_ITER=1.5\n",
            "zero-iterations": b"*g-control,G_ITER=0\n",
            "negative-threshold": b"*g-control,GMIN=-1\n",
            "nonfinite-threshold": b"*g-control,GMAX=NaN\n",
            "reversed-range": b"*g-control,GMIN=2,GMAX=1\n",
            "update-without-threshold": b"*g-control,UPDATE\n",
            "update-zero-threshold": b"*g-control,UPDATE,GTHR=0\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, control in valid_commands.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"valid-{name}.in"
                    path.write_bytes(deck(b"*NAME\nply1\n").replace(
                        b"mechanical\nEND BOUNDARY",
                        b"mechanical\n" + control + b"END BOUNDARY",
                    ))
                    self.assertEqual(
                        0, SourceSet.read(path).inspection()["summary"]["errors"],
                    )
            for name, control in invalid_commands.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"invalid-{name}.in"
                    path.write_bytes(deck(b"*NAME\nply1\n").replace(
                        b"mechanical\nEND BOUNDARY",
                        b"mechanical\n" + control + b"END BOUNDARY",
                    ))
                    diagnostics = SourceSet.read(path).inspection()["diagnostics"]
                    self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_boundary_loading_sequence_rows_are_validated(self) -> None:
        valid_bodies = {
            "static": (
                b"type=Static,name=step1,nstep=2,incr=5D-1\n"
                b"change=bc1,type=disp,value=1\n"
            ),
            "fatigue": (
                b"type=fatigue,name=cyclic,nstep=2,maxcycle=10,mincycle=0,"
                b"R=.1,incr=.5,inicycle=0\n"
                b"change=bc1,maxcycle=-2,mincycle=1,R=.2\n"
            ),
            "closed-block": (
                b"type=fatigue,name=a,nstep=1,maxcycle=10,mincycle=0,R=0,"
                b"incr=1,inicycle=0,block=2\n"
                b"type=fatigue,name=b,nstep=1,maxcycle=10,mincycle=0,R=0,"
                b"incr=1,inicycle=0,block=2\n"
            ),
        }
        invalid_bodies = {
            "empty": b"",
            "odd-pair": b"type=static,name\n",
            "missing-required": b"type=static,name=step1,nstep=1\n",
            "unknown-type": b"type=dynamic,name=step1,nstep=1,incr=1\n",
            "unknown-option": b"type=static,name=step1,nstep=1,incr=1,bad=2\n",
            "zero-steps": b"type=static,name=step1,nstep=0,incr=1\n",
            "nonfinite-increment": b"type=static,name=step1,nstep=1,incr=NaN\n",
            "change-first": b"change=bc1,value=1\n",
            "bad-change-type": (
                b"type=static,name=step1,nstep=1,incr=1\nchange=bc1,type=heat\n"
            ),
            "unclosed-block": (
                b"type=fatigue,name=a,nstep=1,maxcycle=10,mincycle=0,R=0,"
                b"incr=1,inicycle=0,block=2\n"
            ),
            "blocked-2d-change": (
                b"type=2dfatigue,name=a,nstep=1,maxcycle=10,mincycle=0,R=0,"
                b"incr=1,inicycle=0\nchange=bc1,value=1\n"
            ),
            "blocked-reduced-block": (
                b"type=reduced_fatigue,name=a,nstep=1,maxcycle=10,mincycle=0,R=0,"
                b"incr=1,inicycle=0,block=2\n"
            ),
        }
        boundary_condition = b"*boundary condition\ntype=off,name=bc1\n"
        with tempfile.TemporaryDirectory() as directory:
            for name, loading_body in valid_bodies.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"valid-{name}.in"
                    path.write_bytes(deck(b"*NAME\nply1\n").replace(
                        b"mechanical\nEND BOUNDARY",
                        b"mechanical\n" + boundary_condition
                        + b"*loading sequence\n" + loading_body + b"END BOUNDARY",
                    ))
                    self.assertEqual(
                        0, SourceSet.read(path).inspection()["summary"]["errors"],
                    )
            for name, loading_body in invalid_bodies.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"invalid-{name}.in"
                    path.write_bytes(deck(b"*NAME\nply1\n").replace(
                        b"mechanical\nEND BOUNDARY",
                        b"mechanical\n" + boundary_condition
                        + b"*loading sequence\n" + loading_body + b"END BOUNDARY",
                    ))
                    diagnostics = SourceSet.read(path).inspection()["diagnostics"]
                    self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_boundary_connection_variants_are_structurally_validated(self) -> None:
        valid_bodies = {
            "penalty": b"type=-2,name=tie,tolerance=1D-5,search=vtms\nmset=ply1.edge\nlast=ply1\n",
            "nodal": b"type=nodal,name=tie,component=xyz\nmset=all\nsset=ply1.edge\n",
            "surface": b"type=surface,name=contact,tolerance=.01,search=sheff\nmset=ply1.edge,sset=ply1.edge\n",
        }
        invalid_bodies = {
            "empty": b"",
            "missing-header": b"mset=ply1.edge\n",
            "unknown-type": b"type=rigid\nmset=ply1.edge\n",
            "blocked-minus-21": b"type=-21\nmset=ply1.edge\nlast=none\n",
            "bad-tolerance": b"type=-2,tolerance=0\nmset=ply1.edge\nlast=none\n",
            "penalty-no-assignment": b"type=-2\nlast=none\n",
            "penalty-unqualified": b"type=-2\nmset=edge\nlast=none\n",
            "penalty-no-last": b"type=-2\nmset=ply1.edge\n",
            "multiple-penalties": (
                b"type=-2\nmset=ply1.edge\nlast=none\n"
                b"type=-2\nmset=ply1.edge\nlast=none\n"
            ),
            "nodal-bad-component": b"type=nodal,component=123\nmset=all\nsset=all\n",
            "nodal-wrong-order": b"type=nodal\nsset=all\nmset=all\n",
            "surface-no-search": b"type=surface\nmset=ply1.edge,sset=ply1.edge\n",
            "surface-missing-side": b"type=surface,search=sheff\nmset=ply1.edge\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, connection_body in valid_bodies.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"valid-{name}.in"
                    path.write_bytes(deck(
                        b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
                    ).replace(
                        b"mechanical\nEND BOUNDARY",
                        b"mechanical\n*clusters\nply1\n*connections\n"
                        + connection_body + b"END BOUNDARY",
                    ))
                    self.assertEqual(
                        0, SourceSet.read(path).inspection()["summary"]["errors"],
                    )
            for name, connection_body in invalid_bodies.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"invalid-{name}.in"
                    path.write_bytes(deck(
                        b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
                    ).replace(
                        b"mechanical\nEND BOUNDARY",
                        b"mechanical\n*clusters\nply1\n*connections\n"
                        + connection_body + b"END BOUNDARY",
                    ))
                    diagnostics = SourceSet.read(path).inspection()["diagnostics"]
                    self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_boundary_problem_names_must_be_unique(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(b"*NAME\nply1\n").replace(
                b"*type\nmechanical\nEND BOUNDARY",
                b"*type\nmechanical\n*name\ncase1\n"
                b"*type\nmechanical\n*name\nCASE1\nEND BOUNDARY",
            ))
            diagnostics = SourceSet.read(root).inspection()["diagnostics"]
        self.assertIn("BSAM-E300", {item["code"] for item in diagnostics})

    def test_boundary_outputs_resolve_cluster_node_set_and_element_set_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,1,1,1\n*ELSET,ELSET=solid\n1\n"
                b"*STOP\n*TYPE\nsolid\n*NAME\nply2\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,1,1,1\n*ELSET,ELSET=solid\n1\n"
            ).replace(
                b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
                b"BOUNDARY\n*type\nmechanical\n*clusters\nall\n*output\n"
                b"type=data_file, clusters=list\nply1,ply2\n"
                b"type=sum_force, nset=list\nply1.edge,ply2.edge\n"
                b"type=volume_average, elset=list\nply1.solid,ply2.solid\n"
                b"type=traction_average, nset=all\n"
                b"type=cfv, elset=ply1.solid\nEND BOUNDARY\n",
            )
            root.write_bytes(raw)

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            outputs = [
                item for item in semantic["entities"]
                if item["kind"] == "output-selection"
            ]
            output_ids = {item["id"] for item in outputs}
            references = [
                item for item in semantic["references"]
                if item["source_entity_id"] in output_ids
            ]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(5, len(outputs))
            self.assertEqual(9, len(references))
            self.assertEqual(
                {"selects-cluster", "selects-node-set", "selects-element-set"},
                {item["kind"] for item in references},
            )
            self.assertTrue(all(item["status"] == "resolved" for item in references))

    def test_ncopy_options_rows_and_generated_labels_are_validated(self) -> None:
        valid = b"*NCOPY,NSET=copies\nsource,2,10,1D0,0,-1\n"
        invalid = (
            b"*NCOPY,OTHER=x\nsource,1,10,0,0,1\n",
            b"*NCOPY\nsource,1,10,0,0\n",
            b"*NCOPY\nsource,0,10,0,0,1\n",
            b"*NCOPY\nsource,100001,10,0,0,1\n",
            b"*NCOPY\nsource,1,0,0,0,1\n",
            b"*NCOPY\nsource,1,10,0,0,NaN\n",
            b"*NCOPY\nmissing,1,10,0,0,1\n",
            b"*NCOPY\nsource,1,-2,0,0,1\n",
        )
        prefix = b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=source\n1\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "valid.in"
            root.write_bytes(deck(prefix + valid))
            self.assertEqual(0, SourceSet.read(root).inspection()["summary"]["errors"])
            for index, ncopy in enumerate(invalid):
                root = Path(directory) / f"invalid-{index}.in"
                root.write_bytes(deck(prefix + ncopy))
                diagnostics = SourceSet.read(root).inspection()["diagnostics"]
                self.assertIn("BSAM-E310", {item["code"] for item in diagnostics})

    def test_boundary_output_rejects_missing_and_out_of_scope_set_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
                b"*STOP\n*TYPE\nsolid\n*NAME\nply2\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
            ).replace(
                b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
                b"BOUNDARY\n*type\nmechanical\n*clusters\nply1\n*output\n"
                b"type=sum_force, nset=list\nply1.missing,ply2.edge,bare\n"
                b"END BOUNDARY\n",
            )
            root.write_bytes(raw)

            inspection = SourceSet.read(root).inspection()
            codes = [item["code"] for item in inspection["diagnostics"]]

            self.assertEqual(1, codes.count("BSAM-E301"))
            self.assertEqual(2, codes.count("BSAM-E313"))


if __name__ == "__main__":
    unittest.main()
