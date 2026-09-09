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

    def test_global_crack_leading_records_and_named_cluster_are_typed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(b"*NAME\nply1\n").replace(
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
        self.assertEqual(23, semantic["summary"]["entities"])
        self.assertEqual(25, semantic["summary"]["references"])
        self.assertEqual(25, semantic["summary"]["resolved_references"])
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

            self.assertEqual("0.5.0", semantic["schema_version"])
            self.assertEqual(
                {
                    "cluster-declaration": 1,
                    "element": 1, "element-set": 2,
                    "material": 2, "node": 2, "node-set": 2, "section": 1,
                },
                semantic["summary"]["entities_by_kind"],
            )
            self.assertEqual(13, semantic["summary"]["references"])
            node = next(item for item in semantic["entities"] if item["key"] == "node:1")
            self.assertEqual("<root>", node["location"]["source"])
            self.assertGreater(node["location"]["byte_end"], node["location"]["byte_start"])
            targets = {item["target_key"] for item in semantic["references"]}
            self.assertIn("node-set:all_nodes", targets)
            self.assertIn("element-set:solid", targets)
            self.assertEqual(13, semantic["summary"]["resolved_references"])

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

    def test_include_entities_use_workspace_independent_source_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "model.in"
            include = workspace / "mesh.inc"
            root.write_bytes(deck(b"*INCLUDE,FILE=mesh.inc\n"))
            include.write_bytes(b"*NODE\n7,0,0,0\n*STOP\n")

            semantic = SourceSet.read(root).semantic_index().as_dict()

            node = next(item for item in semantic["entities"] if item["key"] == "node:7")
            self.assertEqual("mesh.inc", node["location"]["source"])
            self.assertIn("@mesh.inc:2", node["id"])

    def test_cluster_scope_and_resolution_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            root.write_bytes(deck(
                b"*NAME\nfirst\n*NODE\n1,0,0,0\n1,1,0,0\n"
                b"*ELEMENT,TYPE=C3D4\n10,1,2,1,1\n"
                b"*NAME\nsecond\n*NODE\n1,0,0,0\n"
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
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
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
                b"type=Static, nstep=1, incr=1\n"
                b"change=bc1, type=disp, value=1\n"
                b"END BOUNDARY\n",
            ).replace(
                b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
                b"CONSTITUTIVE\n1\n\t1 1 0\nEND CONSTITUTIVE\n"
                b"FAILURE\n4\nEND FAILURE\n"
                b"CRACK\n301\n\t0 1 0 0\n\t1 -approximation\nEND CRACK\n",
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
                b"*loading sequence\nchange=unknown, type=disp, value=1\n"
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
                b"*NAME\nply2\n*NODE\n1,0,0,0\n"
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

    def test_boundary_outputs_resolve_cluster_node_set_and_element_set_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
                b"*ELEMENT,TYPE=C3D4\n1,1,1,1,1\n*ELSET,ELSET=solid\n1\n"
                b"*NAME\nply2\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
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

    def test_boundary_output_rejects_missing_and_out_of_scope_set_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
                b"*NAME\nply2\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
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
