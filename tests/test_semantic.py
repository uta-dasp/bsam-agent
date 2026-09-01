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

            self.assertEqual("0.1.0", semantic["schema_version"])
            self.assertEqual(
                {"element": 1, "element-set": 2, "node": 2, "node-set": 2, "section": 1},
                semantic["summary"]["entities_by_kind"],
            )
            self.assertEqual(11, semantic["summary"]["references"])
            node = next(item for item in semantic["entities"] if item["key"] == "node:1")
            self.assertEqual("<root>", node["location"]["source"])
            self.assertGreater(node["location"]["byte_end"], node["location"]["byte_start"])
            targets = {item["target_key"] for item in semantic["references"]}
            self.assertIn("node-set:all_nodes", targets)
            self.assertIn("element-set:solid", targets)

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


if __name__ == "__main__":
    unittest.main()
