from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.source_set import SourceSet


FIXTURES = Path(__file__).parent / "fixtures"


class RepresentativeFixtureTests(unittest.TestCase):
    def test_control_fixture_is_valid_typed_and_lossless(self) -> None:
        path = FIXTURES / "representative_controls.in"
        source_set = SourceSet.read(path)
        inspection = source_set.inspection()
        capabilities = {
            item["capability_id"]
            for item in inspection["semantic_model"]["capability_records"]
        }

        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertTrue(inspection["no_op_round_trip"])
        self.assertEqual(path.read_bytes(), source_set.render_files()[path.resolve()])
        self.assertTrue({
            "block.solver", "construct.boundary-type",
            "construct.boundary-geometric-nonlinearity",
            "construct.boundary-g-control", "construct.boundary-name",
            "construct.boundary-status", "construct.boundary-conditions",
            "construct.boundary-loading-sequence",
            "construct.boundary-convergence",
            "construct.boundary-solver-schedule", "construct.boundary-output",
        } <= capabilities)

    def test_named_data_fixture_resolves_cross_family_dependencies(self) -> None:
        path = FIXTURES / "representative_named_data.in"
        source_set = SourceSet.read(path)
        inspection = source_set.inspection()
        semantic = inspection["semantic_model"]

        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertTrue(inspection["no_op_round_trip"])
        self.assertEqual(path.read_bytes(), source_set.render_files()[path.resolve()])
        references = {
            item["kind"]: item["status"] for item in semantic["references"]
            if item["kind"] in {
                "uses-table", "uses-user-function",
                "uses-statistical-distribution", "uses-seed-cluster",
            }
        }
        self.assertEqual({
            "uses-table": "resolved",
            "uses-user-function": "resolved",
            "uses-statistical-distribution": "resolved",
            "uses-seed-cluster": "resolved",
        }, references)

    def test_existing_mesh_and_two_cluster_fixtures_remain_small_and_distinct(self) -> None:
        semantic_path = FIXTURES / "semantic_two_cluster.in"
        inspection = SourceSet.read(semantic_path).inspection()
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(2, inspection["semantic_model"]["summary"]["entities_by_kind"]["cluster"])
        self.assertLess(semantic_path.stat().st_size, 2_000)
        self.assertLess((FIXTURES / "abaqus_style_mesh_no_surface.ele").stat().st_size, 2_000)

    def test_runtime_vtk_probe_fixture_is_valid_typed_and_lossless(self) -> None:
        path = FIXTURES / "runtime_vtk_output.in"
        source_set = SourceSet.read(path)
        inspection = source_set.inspection()
        output_records = [
            item
            for item in inspection["semantic_model"]["capability_records"]
            if item["capability_id"] == "construct.boundary-output"
        ]

        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertTrue(inspection["no_op_round_trip"])
        self.assertEqual(path.read_bytes(), source_set.render_files()[path.resolve()])
        self.assertEqual(1, len(output_records))
        self.assertEqual(
            b"type=data_file,clusters=all,format=vtk,intermediate=0",
            path.read_bytes().splitlines()[30],
        )


if __name__ == "__main__":
    unittest.main()
