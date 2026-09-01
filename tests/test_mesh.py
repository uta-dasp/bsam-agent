from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.mesh import MeshImportError, import_ele


class MeshImportTests(unittest.TestCase):
    def test_imports_abaqus_style_ele_into_canonical_mesh(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "abaqus_style_mesh.ele"

        model = import_ele(fixture)
        value = model.as_dict()

        self.assertEqual("abaqus-style-ele", value["format"])
        self.assertEqual(
            {
                "nodes": 8,
                "elements": 1,
                "node_sets": 2,
                "element_sets": 1,
                "surfaces": 1,
                "orientations": 1,
                "element_types": ["C3D8"],
            },
            value["summary"],
        )
        top = next(item for item in value["sets"] if item["name"] == "top")
        self.assertEqual([5, 6, 7, 8], top["members"])
        self.assertEqual(64, len(value["provenance"]["sha256"]))

    def test_rejects_missing_connectivity_and_dimension_mismatch(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "abaqus_style_mesh.ele"
        raw = fixture.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.ele"
            missing.write_bytes(raw.replace(b"5, 6, 7, 8\n*", b"5, 6, 7, 99\n*", 1))
            with self.assertRaisesRegex(MeshImportError, "missing nodes"):
                import_ele(missing)

            dimensions = Path(directory) / "dimensions.ele"
            dimensions.write_bytes(raw.replace(b"8, 1, 2, 1", b"9, 1, 2, 1"))
            with self.assertRaisesRegex(MeshImportError, "declares"):
                import_ele(dimensions)


if __name__ == "__main__":
    unittest.main()
