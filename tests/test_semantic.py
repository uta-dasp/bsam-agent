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
    def test_representative_two_cluster_fixture_regression(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "semantic_two_cluster.in"

        inspection = SourceSet.read(fixture).inspection()
        semantic = inspection["semantic_model"]

        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(19, semantic["summary"]["entities"])
        self.assertEqual(20, semantic["summary"]["references"])
        self.assertEqual(20, semantic["summary"]["resolved_references"])
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
            ))

            semantic = SourceSet.read(root).inspection()["semantic_model"]

            self.assertEqual("0.2.0", semantic["schema_version"])
            self.assertEqual(
                {
                    "constitutive": 1, "element": 1, "element-set": 2,
                    "node": 2, "node-set": 2, "section": 1,
                },
                semantic["summary"]["entities_by_kind"],
            )
            self.assertEqual(11, semantic["summary"]["references"])
            node = next(item for item in semantic["entities"] if item["key"] == "node:1")
            self.assertEqual("<root>", node["location"]["source"])
            self.assertGreater(node["location"]["byte_end"], node["location"]["byte_start"])
            targets = {item["target_key"] for item in semantic["references"]}
            self.assertIn("node-set:all_nodes", targets)
            self.assertIn("element-set:solid", targets)
            self.assertEqual(11, semantic["summary"]["resolved_references"])

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

    def test_boundary_connection_loading_and_crack_references_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "model.in"
            raw = deck(
                b"*NAME\nply1\n*NODE\n1,0,0,0\n*NSET,NSET=edge\n1\n"
            ).replace(
                b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
                b"BOUNDARY\n*type\nmechanical\n"
                b"*boundary condition\n"
                b"type=disp, comp=x, name=bc1, value=0, nset=PLY1.edge\n"
                b"*connections\n"
                b"type=-2, name=penalty\n"
                b"mset=PLY1.edge, Constitutive=1\n"
                b"last=PLY1\n"
                b"*loading sequence\n"
                b"type=Static, nstep=1, incr=1\n"
                b"change=bc1, type=disp, value=1\n"
                b"END BOUNDARY\n",
            ).replace(
                b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n",
                b"CONSTITUTIVE\n1\n\t1 1 0\nEND CONSTITUTIVE\n"
                b"CRACK\n301\n\t0 1 0 0\n\t1 -approximation\nEND CRACK\n",
            )
            root.write_bytes(raw)

            inspection = SourceSet.read(root).inspection()
            semantic = inspection["semantic_model"]
            kinds = semantic["summary"]["entities_by_kind"]

            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(1, kinds["boundary-condition"])
            self.assertEqual(1, kinds["connection"])
            self.assertEqual(1, kinds["load-change"])
            self.assertEqual(1, kinds["crack"])
            reference_kinds = {item["kind"] for item in semantic["references"]}
            self.assertTrue({
                "targets-node-set", "mset", "uses-constitutive", "terminal-cluster",
                "changes-boundary-condition", "targets-cluster",
            } <= reference_kinds)

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


if __name__ == "__main__":
    unittest.main()
