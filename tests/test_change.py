from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent import cli
from bsam_agent.change import (
    ChangeError,
    _plan_digest,
    apply_plan,
    plan_add_element,
    plan_add_node,
    plan_add_set_members,
    plan_compose_changes,
    plan_create_set,
    plan_delete_element,
    plan_delete_node,
    plan_delete_set,
    plan_import_mesh,
    plan_migrate_legacy_solver,
    plan_parameter_change,
    plan_parameter_removal,
    plan_refresh_change,
    plan_remove_set_member,
    plan_retarget_nodal_record,
    plan_retarget_coordinate_operation,
    plan_retarget_section,
    plan_rename_boundary_condition,
    plan_rename_entity,
    review_plan,
    write_plan,
)
from bsam_agent.source_set import SourceSet


DECK = (
    b"INPUT\r\n3\r\nEND INPUT\r\n"
    b"BOUNDARY\r\n*type\r\nmechanical\r\n*convergence\r\n"
    b"absolute=1\r\nd_reduction =0.25\r\nmaxiterations=20\r\nEND BOUNDARY\r\n"
    b"CONSTITUTIVE\r\n0\r\nEND CONSTITUTIVE\r\n"
    b"MATERIALS\r\n0\r\nEND MATERIALS\r\n"
    b"CLUSTERS\r\n*type\r\nsolid\r\n*STOP\r\nEND CLUSTERS\r\n"
)


class ChangePlanTests(unittest.TestCase):
    def test_parameter_edits_require_registered_consumer_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK)

            with self.assertRaisesRegex(
                ChangeError, "modify is unsupported for construct.boundary-type"
            ):
                plan_parameter_change(
                    source, "BOUNDARY", "TYPE", "problem_type", "thermal"
                )

            source.write_bytes(DECK.replace(
                b"*convergence\r\n",
                b"*boundary condition\r\n"
                b"type=off, name=idle\r\n*convergence\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "require the rename adapter"):
                plan_parameter_change(
                    source, "BOUNDARY", "BOUNDARY CONDITION", "name", "active"
                )

    def test_remove_one_member_from_included_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "remove-member.json"
            destination = root / "revision"
            destination.mkdir()
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n"
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n3,0,1,0\r\n"
                b"*NSET,NSET=edge\r\n1, 2, 3\r\n"
            )

            plan = plan_remove_set_member(source, "ply1", "node", "edge", 2)
            self.assertEqual("remove-set-member", plan["operation"])
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, destination / "model.in")

            self.assertIn(b"1, 3", (destination / "mesh.inc").read_bytes())
            self.assertIn(b"1, 2, 3", include.read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])

            single = root / "single.in"
            single.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
                b"*NSET,NSET=edge\r\n1\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "leave node-set edge empty"):
                plan_remove_set_member(single, "ply1", "node", "edge", 1)

    def test_delete_unreferenced_explicit_set_from_include(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "delete-set.json"
            destination = root / "revision"
            destination.mkdir()
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE,FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*NSET,NSET=temporary\r\n1,2"
            )

            plan = plan_delete_set(source, "ply1", "node", "temporary")
            self.assertEqual("delete-set", plan["operation"])
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, destination / "model.in")

            self.assertIn(b"NSET,NSET=temporary", include.read_bytes())
            self.assertNotIn(b"NSET,NSET=temporary", (destination / "mesh.inc").read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])

    def test_generic_set_rename_updates_cross_file_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "rename-set.json"
            destination = root / "revision"
            destination.mkdir()
            source.write_bytes(DECK.replace(
                b"mechanical\r\n*convergence",
                b"mechanical\r\n*boundary condition\r\n"
                b"type=displacement,component=x,name=fix,value=0,nset=ply1.edge\r\n"
                b"*convergence",
            ).replace(
                b"*STOP\r\n", b"*INCLUDE,FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
                b"*NSET,NSET=edge\r\n1\r\n*SHIFT,NSET=edge\r\n1,0,0"
            )

            plan = plan_rename_entity(
                source, "command.nset", "edge", "rim",
                context={"cluster": "ply1"},
            )
            self.assertEqual("rename-set", plan["operation"])
            self.assertEqual(3, len(plan["patches"]))
            self.assertEqual(2, len(plan["affected_files"]))
            write_plan(plan, plan_path)
            review_plan(plan_path)
            result = apply_plan(plan_path, destination / "model.in")

            changed_root = (destination / "model.in").read_bytes()
            changed_include = (destination / "mesh.inc").read_bytes()
            self.assertIn(b"nset=ply1.rim", changed_root)
            self.assertIn(b"*NSET,NSET=rim", changed_include)
            self.assertIn(b"*SHIFT,NSET=rim", changed_include)
            self.assertNotIn(b"edge", changed_root + changed_include)
            self.assertEqual(0, result["validation"]["summary"]["errors"])

            with self.assertRaisesRegex(ChangeError, "explicit node-set"):
                generated = root / "generated.in"
                generated.write_bytes(DECK.replace(
                    b"*STOP\r\n",
                    b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
                    b"2,1,0,0\r\n*NSET,NSET=edge,GENERATE\r\n1,2,1\r\n*STOP\r\n",
                ))
                plan_rename_entity(
                    generated, "command.nset", "edge", "rim",
                    context={"cluster": "ply1"},
                )

    def test_delete_set_blocks_dependents_and_nonisolated_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            referenced = root / "referenced.in"
            referenced.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
                b"*NSET,NSET=edge\r\n1\r\n*BOUNDARY\r\nedge,1,1,0\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "dependent references"):
                plan_delete_set(referenced, "ply1", "node", "edge")

            generated = root / "generated.in"
            generated.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
                b"*NSET,NSET=edge,GENERATE\r\n1,1,1\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "only one explicit"):
                plan_delete_set(generated, "ply1", "node", "edge")

            multiple = root / "multiple.in"
            multiple.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*NSET,NSET=edge\r\n1\r\n*NSET,NSET=edge\r\n2\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "multiple definitions"):
                plan_delete_set(multiple, "ply1", "node", "edge")

            commented = root / "commented.in"
            commented.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
                b"*NSET,NSET=edge\r\n** keep this rationale\r\n1\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "manual review"):
                plan_delete_set(commented, "ply1", "node", "edge")

            crack_region = root / "crack-region.in"
            crack_region.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n*ELEMENT,TYPE=C3D4\r\n"
                b"1,1,2,3,4\r\n*ELSET,ELSET=region\r\n1\r\n"
                b"*CRACK REGION,ADD,ELSET=region\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "targets-element-set"):
                plan_delete_set(crack_region, "ply1", "element", "region")

    def test_add_element_and_sets_to_include_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n"
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n5,1,1,1\r\n"
                b"*ELEMENT,TYPE=C3D4\r\n1,1,2,3,4\r\n"
                b"*NSET,NSET=edge\r\n1\r\n"
            )

            operations = (
                (
                    plan_add_element(source, "ply1", 2, "C3D4", [2, 3, 4, 5]),
                    b"2,2,3,4,5",
                ),
                (plan_create_set(source, "ply1", "node", "face", [1, 2]), b"NSET=face"),
                (plan_add_set_members(source, "ply1", "node", "edge", [2]), b"NSET=edge"),
            )
            for ordinal, (plan, expected) in enumerate(operations, start=1):
                destination = root / f"revision-{ordinal}"
                destination.mkdir()
                plan_path = root / f"plan-{ordinal}.json"
                write_plan(plan, plan_path)
                result = apply_plan(plan_path, destination / "model.in")
                self.assertEqual([str(include.resolve())], plan["affected_files"])
                self.assertIn(expected, (destination / "mesh.inc").read_bytes())
                self.assertEqual(0, result["validation"]["summary"]["errors"])

    def test_import_mesh_into_include_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            mesh = root / "mesh.ele"
            plan_path = root / "import-include-mesh.json"
            destination = root / "revision"
            destination.mkdir()
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n"
            ))
            include.write_bytes(b"*NAME\r\nply1\r\n")
            mesh.write_bytes(
                (Path(__file__).parent / "fixtures" / "abaqus_style_mesh.ele").read_bytes().replace(
                    b"*Surface, name=outer, type=Element\nsolid, S1\n", b"",
                )
            )

            plan = plan_import_mesh(source, mesh, "ply1")
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, destination / "model.in")

            changed_include = (destination / "mesh.inc").read_bytes()
            self.assertIn(b"*DIMENSIONS", changed_include)
            self.assertIn(b"*ELEMENT", changed_include)
            self.assertEqual(0, result["validation"]["summary"]["errors"])

    def test_add_node_to_include_cluster_into_new_source_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "add-include-node.json"
            destination_directory = root / "revision"
            destination_directory.mkdir()
            output = destination_directory / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n"
            ))
            include.write_bytes(b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0")

            plan = plan_add_node(source, "ply1", 2, "1", "2", "3")
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            self.assertEqual(plan["base_sha256"], plan["proposed_sha256"])
            self.assertIn("a/mesh.inc", plan["source_diff"])
            write_plan(plan, plan_path)
            with self.assertRaisesRegex(ChangeError, "separate destination directory"):
                apply_plan(plan_path, root / "same-directory.in")

            result = apply_plan(plan_path, output)

            self.assertEqual(source.read_bytes(), output.read_bytes())
            self.assertNotIn(b"2,1,2,3", include.read_bytes())
            self.assertIn(b"1,0,0,0\r\n*NODE\r\n2,1,2,3\r\n", (
                destination_directory / "mesh.inc"
            ).read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])

    def test_delete_unreferenced_node_from_include_into_new_source_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "delete-include-node.json"
            destination_directory = root / "revision"
            destination_directory.mkdir()
            output = destination_directory / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n"
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,1,1\r\n*STOP\r\n"
            )

            plan = plan_delete_node(source, "ply1", 2)
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            self.assertEqual(plan["base_sha256"], plan["proposed_sha256"])
            self.assertIn("a/mesh.inc", plan["source_diff"])
            write_plan(plan, plan_path)
            with self.assertRaisesRegex(ChangeError, "separate destination directory"):
                apply_plan(plan_path, root / "same-directory.in")

            result = apply_plan(plan_path, output)

            self.assertEqual(source.read_bytes(), output.read_bytes())
            self.assertIn(b"2,1,1,1", include.read_bytes())
            self.assertNotIn(b"2,1,1,1", (destination_directory / "mesh.inc").read_bytes())
            self.assertEqual(0, SourceSet.read(output).inspection()["summary"]["errors"])
            audit = json.loads(Path(result["audit"]).read_text(encoding="utf-8"))
            self.assertEqual(
                [str((destination_directory / "mesh.inc").resolve())],
                audit["affected_files"],
            )

    def test_compose_root_and_include_changes_into_one_source_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            parameter_path = root / "parameter.json"
            node_path = root / "node.json"
            composite_path = root / "composite.json"
            output_directory = root / "revision"
            output_directory.mkdir()
            output = output_directory / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n"
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,1,1\r\n*STOP\r\n"
            )
            write_plan(
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
                ),
                parameter_path,
            )
            write_plan(plan_delete_node(source, "ply1", 2), node_path)

            composite = plan_compose_changes(source, [parameter_path, node_path])
            self.assertEqual(2, len(composite["affected_files"]))
            write_plan(composite, composite_path)
            result = apply_plan(composite_path, output)

            self.assertIn(b"absolute=2", output.read_bytes())
            self.assertNotIn(b"2,1,1,1", (output_directory / "mesh.inc").read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])
            self.assertEqual(2, len(json.loads(
                Path(result["audit"]).read_text(encoding="utf-8")
            )["affected_files"]))

    def test_compose_independent_typed_changes_into_one_reviewed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            first_path = root / "absolute.json"
            second_path = root / "iterations.json"
            composite_path = root / "composite.json"
            output = root / "changed.in"
            source.write_bytes(DECK)
            write_plan(
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
                ),
                first_path,
            )
            write_plan(
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "maxiterations", "30"
                ),
                second_path,
            )

            plan = plan_compose_changes(source, [first_path, second_path])
            self.assertEqual("compose-changes", plan["operation"])
            self.assertEqual(2, len(plan["components"]))
            self.assertEqual(2, len(plan["patches"]))
            self.assertEqual(2, len(plan["changed_model_paths"]))
            self.assertEqual(0, plan["validation"]["summary"]["errors"])
            write_plan(plan, composite_path)
            review = review_plan(composite_path)
            self.assertEqual(plan["proposed_sha256"], review["proposed_sha256"])
            result = apply_plan(composite_path, output)

            self.assertIn(b"absolute=2", output.read_bytes())
            self.assertIn(b"maxiterations=30", output.read_bytes())
            self.assertEqual(2, len(result["changed_lines"]))

    def test_composition_rejects_overlap_and_tampered_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            first_path = root / "first.json"
            second_path = root / "second.json"
            source.write_bytes(DECK)
            write_plan(
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
                ),
                first_path,
            )
            write_plan(
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "3"
                ),
                second_path,
            )
            with self.assertRaisesRegex(ChangeError, "overlap"):
                plan_compose_changes(source, [first_path, second_path])

            second_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ChangeError, "unsupported change-plan schema"):
                plan_compose_changes(source, [first_path, second_path])

    def test_plan_and_apply_legacy_solver_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "solver.json"
            output = root / "current.in"
            source.write_bytes(DECK.replace(
                b"BOUNDARY\r\n",
                b"SOLVER\r\n9\r\n14        Processors #\r\n*indefinite\r\nEND SOLVER\r\n"
                b"BOUNDARY\r\n",
                1,
            ))

            plan = plan_migrate_legacy_solver(source)
            self.assertEqual("migrate-legacy-solver", plan["operation"])
            self.assertEqual("pardiso", plan["selector"]["target_type"])
            write_plan(plan, plan_path)
            review_plan(plan_path)
            apply_plan(plan_path, output)

            self.assertIn(
                b"SOLVER\r\n*type=pardiso\r\nn_threads=14\r\n"
                b"matrix_type=indefinite\r\nend solver\r\nEND SOLVER\r\n",
                output.read_bytes(),
            )
            self.assertNotIn(b"Processors #", output.read_bytes())
            with self.assertRaisesRegex(ChangeError, "already uses current syntax"):
                plan_migrate_legacy_solver(output)

            source.write_bytes(DECK.replace(
                b"BOUNDARY\r\n",
                b"SOLVER\r\n9\r\n14\r\nEND SOLVER\r\nBOUNDARY\r\n",
                1,
            ))
            with self.assertRaisesRegex(ChangeError, "cannot select definite"):
                plan_migrate_legacy_solver(source)

    def test_boundary_condition_rename_updates_loading_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "rename.json"
            output = root / "renamed.in"
            fixture = (Path(__file__).parent / "fixtures" / "semantic_two_cluster.in").read_bytes()
            source.write_bytes(fixture.replace(
                b"BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n",
                b"BOUNDARY\n*type\nmechanical\n"
                b"*boundary condition\n"
                b"type=disp, comp=x, name=pull, value=0, nset=lower_ply.all_nodes\n"
                b"*loading sequence\n"
                b"type=Static, name=step1, nstep=1, incr=1\n"
                b"change=pull, type=disp, value=1\n"
                b"END BOUNDARY\n",
            ))

            plan = plan_rename_boundary_condition(source, "pull", "tension")
            self.assertEqual("rename-boundary-condition", plan["operation"])
            self.assertEqual(2, len(plan["patches"]))
            self.assertEqual(0, plan["validation"]["summary"]["errors"])
            write_plan(plan, plan_path)
            review_plan(plan_path)
            apply_plan(plan_path, output)

            text = output.read_text(encoding="latin-1")
            self.assertIn("name=tension", text)
            self.assertIn("change=tension", text)
            self.assertNotIn("name=pull", text)
            self.assertEqual(0, SourceSet.read(output).inspection()["summary"]["errors"])

            with self.assertRaisesRegex(ChangeError, "must resolve to one exact"):
                plan_rename_boundary_condition(source, "missing", "replacement")

    def test_plan_and_apply_mesh_import_into_empty_template_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.in"
            mesh = root / "mesh.ele"
            plan_path = root / "import.json"
            output = root / "assembled.in"
            template.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*NAME\r\nmesh_cluster\r\n*STOP\r\n"
            ))
            fixture = (Path(__file__).parent / "fixtures" / "abaqus_style_mesh.ele").read_bytes()
            mesh.write_bytes(fixture)
            with self.assertRaisesRegex(ChangeError, "no active cluster dispatch"):
                plan_import_mesh(template, mesh, "mesh_cluster")
            mesh.write_bytes(fixture.replace(
                b"*Surface, name=outer, type=Element\nsolid, S1\n", b"",
            ))

            plan = plan_import_mesh(template, mesh, "mesh_cluster")
            self.assertEqual("import-mesh", plan["operation"])
            self.assertEqual(mesh.resolve(), Path(plan["inputs"][0]["path"]))
            write_plan(plan, plan_path)
            review_plan(plan_path)
            result = apply_plan(plan_path, output)

            inspection = SourceSet.read(output).inspection()
            self.assertEqual(0, inspection["summary"]["errors"])
            self.assertEqual(8, inspection["semantic_model"]["summary"]["entities_by_kind"]["node"])
            self.assertIn(b"*DIMENSIONS\r\n8,1,2,1\r\n", output.read_bytes())
            self.assertEqual(plan["inputs"], result["inputs"])

    def test_mesh_import_plan_is_bound_to_mesh_digest_and_empty_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.in"
            mesh = root / "mesh.ele"
            plan_path = root / "import.json"
            template.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*NAME\r\nmesh_cluster\r\n*STOP\r\n"
            ))
            fixture = (Path(__file__).parent / "fixtures" / "abaqus_style_mesh.ele").read_bytes()
            fixture = fixture.replace(
                b"*Surface, name=outer, type=Element\nsolid, S1\n", b"",
            )
            mesh.write_bytes(fixture)
            write_plan(plan_import_mesh(template, mesh, "mesh_cluster"), plan_path)
            mesh.write_bytes(fixture + b"** changed\n")

            with self.assertRaisesRegex(ChangeError, "mesh input changed"):
                review_plan(plan_path)

            occupied = root / "occupied.in"
            occupied.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nmesh_cluster\r\n*NODE\r\n1,0,0,0\r\n*STOP\r\n",
            ))
            mesh.write_bytes(fixture)
            with self.assertRaisesRegex(ChangeError, "not empty"):
                plan_import_mesh(occupied, mesh, "mesh_cluster")

    def test_typed_set_creation_and_member_addition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            first_plan = root / "create-set.json"
            first_output = root / "with-set.in"
            second_plan = root / "add-members.json"
            second_output = root / "with-members.in"
            source.write_bytes(
                (Path(__file__).parent / "fixtures" / "semantic_two_cluster.in").read_bytes()
            )

            create = plan_create_set(source, "lower_ply", "node", "edge", [1, 2])
            write_plan(create, first_plan)
            apply_plan(first_plan, first_output)
            add = plan_add_set_members(first_output, "lower_ply", "node", "edge", [3, 4])
            write_plan(add, second_plan)
            apply_plan(second_plan, second_output)

            semantic = SourceSet.read(second_output).semantic_index()
            set_entities = [
                item for item in semantic.entities
                if item.key == "cluster:lower_ply/node-set:edge"
            ]
            members = {
                item.target_key for entity in set_entities for item in semantic.references
                if item.source_entity_id == entity.id and item.kind == "contains"
            }
            self.assertEqual(
                {f"cluster:lower_ply/node:{label}" for label in range(1, 5)}, members
            )
            with self.assertRaisesRegex(ChangeError, "already contains"):
                plan_add_set_members(second_output, "lower_ply", "node", "edge", [4])
            with self.assertRaisesRegex(ChangeError, "missing nodes"):
                plan_create_set(source, "lower_ply", "node", "bad", [99])

    def test_typed_element_creation_uses_established_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            source.write_bytes(
                (Path(__file__).parent / "fixtures" / "semantic_two_cluster.in").read_bytes()
            )
            plan_path = root / "add-element.json"
            output = root / "changed.in"

            plan = plan_add_element(
                source, "lower_ply", 2, "C3D4", [1, 2, 3, 4], "added"
            )
            write_plan(plan, plan_path)
            apply_plan(plan_path, output)

            semantic = SourceSet.read(output).semantic_index()
            self.assertIn(
                "cluster:lower_ply/element:2", {item.key for item in semantic.entities}
            )
            with self.assertRaisesRegex(ChangeError, "not established"):
                plan_add_element(source, "lower_ply", 3, "C3D8", [1, 2, 3, 4])
            with self.assertRaisesRegex(ChangeError, "missing nodes"):
                plan_add_element(source, "lower_ply", 3, "C3D4", [1, 2, 3, 99])

    def test_delete_unreferenced_element_from_include(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "delete-element.json"
            destination = root / "revision"
            destination.mkdir()
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE,FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n*ELEMENT,TYPE=C3D4\r\n"
                b"1,1,2,3,4\r\n2,1,2,3,4"
            )

            plan = plan_delete_element(source, "ply1", 2)
            self.assertEqual("delete-element", plan["operation"])
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, destination / "model.in")

            self.assertIn(b"2,1,2,3,4", include.read_bytes())
            self.assertNotIn(b"2,1,2,3,4", (destination / "mesh.inc").read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])

    def test_element_deletion_blocks_set_and_selection_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n*ELEMENT,TYPE=C3D4\r\n"
                b"1,1,2,3,4\r\n2,1,2,3,4\r\n3,1,2,3,4\r\n"
                b"*ELSET,ELSET=kept\r\n1\r\n"
                b"*SELECTION,ID=1,TYPE=ELEMENT\r\n2\r\n*STOP\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "contains"):
                plan_delete_element(source, "ply1", 1)
            with self.assertRaisesRegex(ChangeError, "selects-element"):
                plan_delete_element(source, "ply1", 2)
            self.assertEqual(
                "delete-element", plan_delete_element(source, "ply1", 3)["operation"]
            )

            implicit = Path(directory) / "implicit.in"
            implicit.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n*ELEMENT,TYPE=C3D4,ELSET=solid\r\n"
                b"1,1,2,3,4\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "member-of"):
                plan_delete_element(implicit, "ply1", 1)

    def test_orientation_dependencies_block_structural_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n*ELEMENT,TYPE=C3D4\r\n"
                b"1,1,2,3,4\r\n2,1,2,3,4\r\n*NSET,NSET=edge\r\n1\r\n"
                b"*ELSET,ELSET=solid\r\n1\r\n*ORIENTATION,NAME=ORI-NODE\r\n"
                b"edge,1,0,0,0,0,1,.5\r\n2,1,0,0,0,0,1,.5\r\n"
                b"*ORIENTATION,NAME=ORI-ELE\r\nsolid,1,0,0,0,0,1,.5\r\n"
                b"2,1,0,0,0,0,1,.5\r\n*STOP\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "targets-node"):
                plan_delete_node(source, "ply1", 2)
            with self.assertRaisesRegex(ChangeError, "targets-element"):
                plan_delete_element(source, "ply1", 2)
            with self.assertRaisesRegex(ChangeError, "targets-node-set"):
                plan_delete_set(source, "ply1", "node", "edge")
            with self.assertRaisesRegex(ChangeError, "targets-element-set"):
                plan_delete_set(source, "ply1", "element", "solid")

    def test_generated_and_box_set_memberships_block_structural_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,2,0,0\r\n4,0,1,0\r\n*ELEMENT,TYPE=C3D4\r\n"
                b"1,1,2,3,4\r\n2,1,2,3,4\r\n"
                b"*NSET,NSET=generated,GENERATE\r\n1,2,1\r\n"
                b"*NSET,NSET=boxed,BOX\r\n2,-1,-1,2,1,1\r\n"
                b"*ELSET,ELSET=generated,GENERATE\r\n1,2,1\r\n*STOP\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "contains"):
                plan_delete_node(source, "ply1", 1)
            with self.assertRaisesRegex(ChangeError, "contains"):
                plan_delete_node(source, "ply1", 3)
            with self.assertRaisesRegex(ChangeError, "contains"):
                plan_delete_element(source, "ply1", 2)

    def test_coordinate_and_integration_dependencies_block_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n*ELEMENT,TYPE=X3D8\r\n"
                b"1,1,2,3,4,1,2,3,4\r\n*NSET,NSET=edge\r\n1,2\r\n"
                b"*SHIFT,NSET=edge\r\n1,0,0\r\n*INTEGRATION\r\n"
                b"1,1\r\n0,0,0,1\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "targets-node-set"):
                plan_delete_set(source, "ply1", "node", "edge")
            with self.assertRaisesRegex(ChangeError, "targets-element"):
                plan_delete_element(source, "ply1", 1)

    def test_retarget_coordinate_operation_in_include(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "shift.json"
            destination = root / "revision"
            destination.mkdir()
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE,FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*NSET,NSET=old\r\n1\r\n*NSET,NSET=new\r\n2\r\n"
                b"*SHIFT, NSET = old\r\n1,0,0"
            )

            plan = plan_retarget_coordinate_operation(
                source, "command.shift", "ply1", "old", "new",
            )
            self.assertEqual("retarget-coordinate-operation", plan["operation"])
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, destination / "model.in")

            self.assertIn(b"NSET = old", include.read_bytes())
            self.assertIn(b"NSET = new", (destination / "mesh.inc").read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])
            with self.assertRaisesRegex(ChangeError, "existing node set"):
                plan_retarget_coordinate_operation(
                    source, "command.shift", "ply1", "old", "missing",
                )

            all_target = root / "all.in"
            all_target.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
                b"*NSET,NSET=new\r\n1\r\n*SCALE,ALL\r\n2,2,2\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "no NSET value"):
                plan_retarget_coordinate_operation(
                    all_target, "command.scale", "ply1", "ALL", "new",
                )

    def test_node_generation_dependencies_block_source_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n5,4,0,0\r\n"
                b"*NSET,NSET=source\r\n1\r\n*NGEN\r\n1,5,1\r\n"
                b"*NCOPY\r\nsource,1,10,0,0,1\r\n*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "uses-node-endpoint"):
                plan_delete_node(source, "ply1", 5)
            with self.assertRaisesRegex(ChangeError, "copies-node-set"):
                plan_delete_set(source, "ply1", "node", "source")

    def test_elgen_seed_dependency_blocks_element_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n11,2,0,0\r\n12,3,0,0\r\n"
                b"13,2,1,0\r\n14,2,0,1\r\n*ELEMENT,TYPE=C3D4\r\n"
                b"1,1,2,3,4\r\n*ELGEN,TYPE=C3D4\r\n1,2,1,1,10,0,0\r\n"
                b"*STOP\r\n",
            ))
            with self.assertRaisesRegex(ChangeError, "uses-seed-element"):
                plan_delete_element(source, "ply1", 1)
            with self.assertRaisesRegex(ChangeError, "cannot be deleted as one explicit record"):
                plan_delete_element(source, "ply1", 2)

    def test_typed_node_deletion_blocks_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "delete-node.json"
            output = root / "changed.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*ELEMENT,TYPE=C3D4\r\n1,1,1,1,1\r\n*STOP\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "dependent references"):
                plan_delete_node(source, "ply1", 1)
            write_plan(plan_delete_node(source, "ply1", 2), plan_path)
            apply_plan(plan_path, output)

            self.assertNotIn(b"2,1,0,0", output.read_bytes())
            self.assertEqual(0, SourceSet.read(output).inspection()["summary"]["errors"])

    def test_node_deletion_blocks_cluster_boundary_and_load_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE,FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n"
                b"1,0,0,0\r\n2,1,0,0\r\n3,2,0,0\r\n"
                b"*BOUNDARY\r\n2,1,1,0\r\n*LOAD\r\n3,1,5"
            )

            with self.assertRaisesRegex(ChangeError, "targets-node"):
                plan_delete_node(source, "ply1", 2)
            with self.assertRaisesRegex(ChangeError, "targets-node"):
                plan_delete_node(source, "ply1", 3)
            self.assertEqual(
                "delete-node", plan_delete_node(source, "ply1", 1)["operation"]
            )

    def test_node_deletion_blocks_cluster_field_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*FIELD,VARIABLES=1\r\n2,10\r\n*STOP\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "targets-node"):
                plan_delete_node(source, "ply1", 2)
            self.assertEqual(
                "delete-node", plan_delete_node(source, "ply1", 1)["operation"]
            )

    def test_node_deletion_blocks_direct_selection_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*SELECTION,ID=1\r\n2\r\n*STOP\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "selects-node"):
                plan_delete_node(source, "ply1", 2)
            self.assertEqual(
                "delete-node", plan_delete_node(source, "ply1", 1)["operation"]
            )

    def test_retarget_included_nodal_record_preserves_source_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "retarget.json"
            destination = root / "revision"
            destination.mkdir()
            output = destination / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE,FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*NSET,NSET=edge\r\n1\r\n*BOUNDARY\r\n  2,1,1,0\r\n"
                b"*LOAD\r\n1,1,5"
            )

            plan = plan_retarget_nodal_record(
                source, "command.boundary", "ply1", "2", "edge",
            )
            self.assertEqual("retarget-nodal-record", plan["operation"])
            self.assertEqual([str(include.resolve())], plan["affected_files"])
            self.assertEqual("2", plan["patch"]["old"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, output)

            self.assertIn(b"  2,1,1,0", include.read_bytes())
            self.assertIn(b"  edge,1,1,0", (destination / "mesh.inc").read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])

            list_source = self._write_list_boundary(root)
            with self.assertRaisesRegex(ChangeError, "existing numeric node"):
                plan_retarget_nodal_record(
                    list_source, "command.boundary", "ply1", "1", "edge",
                )

    def test_retarget_nodal_record_requires_unambiguous_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"*LOAD\r\n1,1,5\r\n1,2,6\r\n*STOP\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "ambiguous"):
                plan_retarget_nodal_record(
                    source, "command.load", "ply1", "1", "2",
                )
            plan = plan_retarget_nodal_record(
                source, "command.load", "ply1", "1", "2", 2,
            )
            self.assertEqual(2, plan["selector"]["occurrence"])
            self.assertIn("-1,2,6\n+2,2,6", plan["source_diff"])
            with self.assertRaisesRegex(ChangeError, "existing node set or numeric node"):
                plan_retarget_nodal_record(
                    source, "command.load", "ply1", "1", "99", 1,
                )

    def test_retarget_section_in_include_with_exact_dependency_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "section.json"
            destination = root / "revision"
            destination.mkdir()
            source.write_bytes(DECK.replace(
                b"*STOP\r\n", b"*INCLUDE,FILE=mesh.inc\r\n*STOP\r\n",
            ).replace(
                b"MATERIALS\r\n0\r\nEND MATERIALS\r\n",
                b"MATERIALS\r\n10\r\n1 0 0\r\n1 1 1\r\nEND MATERIALS\r\n",
            ))
            include.write_bytes(
                b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n2,1,0,0\r\n"
                b"3,0,1,0\r\n4,0,0,1\r\n*ELEMENT,TYPE=C3D4\r\n"
                b"1,1,2,3,4\r\n2,1,2,3,4\r\n*ELSET,ELSET=old\r\n1\r\n"
                b"*ELSET,ELSET=new\r\n2\r\n*SECTION, ELSET = old, LAYERS=1\r\n1,1"
            )

            plan = plan_retarget_section(source, "ply1", "old", "new")
            self.assertEqual("retarget-section", plan["operation"])
            self.assertEqual("old", plan["patch"]["old"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, destination / "model.in")

            self.assertIn(b"ELSET = old", include.read_bytes())
            self.assertIn(b"ELSET = new", (destination / "mesh.inc").read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])
            with self.assertRaisesRegex(ChangeError, "existing element set"):
                plan_retarget_section(source, "ply1", "old", "missing")

    @staticmethod
    def _write_list_boundary(root: Path) -> Path:
        source = root / "list-boundary.in"
        source.write_bytes(DECK.replace(
            b"*STOP\r\n",
            b"*NAME\r\nply1\r\n*NODE\r\n1,0,0,0\r\n"
            b"*NSET,NSET=edge\r\n1\r\n*BOUNDARY,FORMAT=LIST\r\n"
            b"1,0,0,0\r\n*STOP\r\n",
        ))
        return source

    def test_plan_and_apply_typed_node_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "add-node.json"
            output = root / "changed.in"
            named = DECK.replace(b"*STOP\r\n", b"*NAME\r\nply1\r\n*STOP\r\n")
            source.write_bytes(named)

            plan = plan_add_node(source, "ply1", 7, "1.0", "2.0", "3.0")
            self.assertEqual("add-node", plan["operation"])
            self.assertEqual(["CLUSTERS[ply1].nodes[7]"], plan["changed_model_paths"])
            write_plan(plan, plan_path)
            result = apply_plan(plan_path, output)

            self.assertIn(b"*NODE\r\n7,1.0,2.0,3.0\r\n*STOP", output.read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])
            with self.assertRaisesRegex(ChangeError, "already exists"):
                plan_add_node(output, "ply1", 7, "0", "0", "0")
            with self.assertRaisesRegex(ChangeError, "finite"):
                plan_add_node(source, "ply1", 8, "nan", "0", "0")

    def test_plan_and_apply_patch_only_value_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            output = root / "model.changed.in"
            source.write_bytes(DECK)

            plan = plan_parameter_change(
                source, "BOUNDARY", "*CONVERGENCE", "d_reduction", "0.5"
            )
            self.assertEqual("0.25", plan["patch"]["old"])
            self.assertEqual("0.5", plan["patch"]["new"])
            self.assertEqual(
                ["BOUNDARY.*CONVERGENCE[1].d_reduction"],
                plan["changed_model_paths"],
            )
            self.assertIn("-d_reduction =0.25", plan["source_diff"])
            self.assertIn("+d_reduction =0.5", plan["source_diff"])
            write_plan(plan, plan_path)
            review = review_plan(plan_path)
            self.assertEqual(plan["proposed_sha256"], review["proposed_sha256"])
            result = apply_plan(plan_path, output)

            self.assertEqual(DECK, source.read_bytes())
            self.assertEqual(
                DECK.replace(b"d_reduction =0.25", b"d_reduction =0.5"),
                output.read_bytes(),
            )
            self.assertNotEqual(result["base_sha256"], result["output_sha256"])
            audit_path = Path(str(output) + ".audit.json")
            self.assertEqual(audit_path.resolve(), Path(result["audit"]))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["plan_digest"], audit["plan"]["digest"])
            self.assertEqual(result["output_sha256"], audit["output_sha256"])
            self.assertEqual(0, audit["validation"]["summary"]["errors"])
            self.assertIsNone(audit["run_directory"])
            audit_content = {
                key: value for key, value in audit.items()
                if key not in {"audit_digest", "audit_id"}
            }
            self.assertEqual(audit["audit_digest"], _plan_digest(audit_content))

    def test_plan_and_apply_verified_absent_optional_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "insert.json"
            output = root / "changed.in"
            source.write_bytes(DECK.replace(b"maxiterations=20\r\n", b""))

            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "maxiterations", "30"
            )
            self.assertEqual("insert-optional-parameter", plan["operation"])
            self.assertEqual("", plan["patch"]["old"])
            self.assertEqual("maxiterations=30\r\n", plan["patch"]["new"])
            self.assertIn("was registered default 20", plan["preview"])
            write_plan(plan, plan_path)
            review_plan(plan_path)
            result = apply_plan(plan_path, output)

            self.assertIn(
                b"d_reduction =0.25\r\nmaxiterations=30\r\nEND BOUNDARY",
                output.read_bytes(),
            )
            self.assertEqual(0, result["validation"]["summary"]["errors"])

            stale_path = root / "stale-insert.json"
            stale_source = root / "stale.in"
            stale_source.write_bytes(source.read_bytes())
            write_plan(
                plan_parameter_change(
                    stale_source, "BOUNDARY", "CONVERGENCE", "maxiterations", "40"
                ),
                stale_path,
            )
            stale_source.write_bytes(stale_source.read_bytes() + b"** later comment\r\n")
            refreshed = plan_refresh_change(stale_source, stale_path)
            self.assertEqual("insert-optional-parameter", refreshed["operation"])
            self.assertEqual("40", refreshed["selector"]["requested_value"])

            with self.assertRaisesRegex(ChangeError, "insertion is not verified"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "mintime", "2"
                )

    def test_plan_and_apply_verified_optional_parameter_removal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "remove.json"
            output = root / "changed.in"
            source.write_bytes(DECK)

            plan = plan_parameter_removal(
                source, "BOUNDARY", "CONVERGENCE", "maxiterations"
            )
            self.assertEqual("remove-optional-parameter", plan["operation"])
            self.assertEqual("", plan["patch"]["new"])
            self.assertIn("restore registered default 20", plan["preview"])
            write_plan(plan, plan_path)
            review_plan(plan_path)
            result = apply_plan(plan_path, output)

            self.assertNotIn(b"maxiterations=20", output.read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])
            convergence = next(
                item for item in SourceSet.read(output).semantic_index().capability_records
                if item.capability_id == "construct.boundary-convergence"
            )
            self.assertNotIn("maxiterations", convergence.parameters)
            self.assertEqual(20, convergence.defaults["maxiterations"])
            with self.assertRaisesRegex(ChangeError, "removal of parameter mintime is not verified"):
                plan_parameter_removal(source, "BOUNDARY", "CONVERGENCE", "mintime")

            shared = root / "shared.in"
            shared.write_bytes(DECK.replace(
                b"maxiterations=20", b"maxiterations=20, mintime=1"
            ))
            with self.assertRaisesRegex(ChangeError, "shares line"):
                plan_parameter_removal(
                    shared, "BOUNDARY", "CONVERGENCE", "maxiterations"
                )

    def test_repeated_last_wins_parameter_values_require_exact_occurrences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "repeated.in"
            source.write_bytes(DECK.replace(
                b"maxiterations=20\r\n",
                b"maxiterations=20\r\nmaxiterations=30\r\n",
            ))

            with self.assertRaisesRegex(ChangeError, "provide parameter_occurrence"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "maxiterations", "25"
                )
            selected = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "maxiterations", "25",
                parameter_occurrence=1,
            )
            self.assertEqual("20", selected["patch"]["old"])
            self.assertEqual(
                ["BOUNDARY.*CONVERGENCE[1].maxiterations[1]"],
                selected["changed_model_paths"],
            )

            insertion_path = root / "append.json"
            insertion_output = root / "appended.in"
            insertion = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "maxiterations", "40",
                insert_repeated=True,
            )
            self.assertEqual("insert-repeated-parameter", insertion["operation"])
            self.assertEqual(3, insertion["selector"]["parameter_occurrence"])
            self.assertEqual(
                ["BOUNDARY.*CONVERGENCE[1].maxiterations[3]"],
                insertion["changed_model_paths"],
            )
            write_plan(insertion, insertion_path)
            review_plan(insertion_path)
            apply_plan(insertion_path, insertion_output)
            self.assertEqual(3, insertion_output.read_bytes().count(b"maxiterations="))
            self.assertIn(b"maxiterations=40\r\nEND BOUNDARY", insertion_output.read_bytes())

            removal_path = root / "remove-repeated.json"
            removal_output = root / "removed-repeated.in"
            removal = plan_parameter_removal(
                source, "BOUNDARY", "CONVERGENCE", "maxiterations",
                parameter_occurrence=2,
            )
            self.assertEqual("remove-repeated-parameter", removal["operation"])
            self.assertIn("effective value becomes 20", removal["preview"])
            write_plan(removal, removal_path)
            review_plan(removal_path)
            apply_plan(removal_path, removal_output)
            self.assertEqual(1, removal_output.read_bytes().count(b"maxiterations="))
            self.assertIn(b"maxiterations=20", removal_output.read_bytes())

            with self.assertRaisesRegex(ChangeError, "not registered as repeated"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "2",
                    parameter_occurrence=1,
                )

    def test_plan_and_apply_verified_boolean_flag_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            enable_path = root / "enable.json"
            enabled = root / "enabled.in"
            disable_path = root / "disable.json"
            disabled = root / "disabled.in"
            source.write_bytes(DECK.replace(
                b"*convergence\r\n", b"*g-control # retained\r\n*convergence\r\n"
            ))

            enable = plan_parameter_change(
                source, "BOUNDARY", "G-CONTROL", "DAMP", "true"
            )
            self.assertEqual("insert-optional-flag", enable["operation"])
            self.assertEqual(",DAMP", enable["patch"]["new"])
            write_plan(enable, enable_path)
            apply_plan(enable_path, enabled)
            self.assertIn(b"*g-control,DAMP # retained", enabled.read_bytes())

            disable = plan_parameter_change(
                enabled, "BOUNDARY", "G-CONTROL", "DAMP", "false"
            )
            self.assertEqual("remove-optional-flag", disable["operation"])
            write_plan(disable, disable_path)
            result = apply_plan(disable_path, disabled)
            self.assertIn(b"*g-control # retained", disabled.read_bytes())
            self.assertNotIn(b"DAMP", disabled.read_bytes())
            self.assertEqual(0, result["validation"]["summary"]["errors"])

            with self.assertRaisesRegex(ChangeError, "not a valid flag"):
                plan_parameter_change(
                    source, "BOUNDARY", "G-CONTROL", "DAMP", "yes"
                )
            with self.assertRaisesRegex(ChangeError, "insert of flag parameter UPDATE is not verified"):
                plan_parameter_change(
                    source, "BOUNDARY", "G-CONTROL", "UPDATE", "true"
                )

    def test_diff_cli_revalidates_and_returns_review_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            source.write_bytes(DECK)
            write_plan(
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "maxiterations", "30"
                ),
                plan_path,
            )

            output = io.StringIO()
            with redirect_stdout(output):
                status = cli.main(["diff", str(plan_path), "--compact"])
            review = json.loads(output.getvalue())
            self.assertEqual(0, status)
            self.assertEqual(
                ["BOUNDARY.*CONVERGENCE[1].maxiterations"],
                review["changed_model_paths"],
            )
            self.assertIn("-maxiterations=20", review["source_diff"])
            self.assertIn("+maxiterations=30", review["source_diff"])

    def test_stale_plan_is_rejected_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            output = root / "model.changed.in"
            source.write_bytes(DECK)
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "maxiterations", "30"
            )
            write_plan(plan, plan_path)
            source.write_bytes(DECK + b"** changed after planning\r\n")

            with self.assertRaisesRegex(ChangeError, "source changed after planning"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ChangeError, "source changed after planning"):
                review_plan(plan_path)

    def test_in_place_and_ambiguous_changes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "change.json"
            source.write_bytes(DECK)
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
            )
            write_plan(plan, plan_path)
            with self.assertRaisesRegex(ChangeError, "in-place"):
                apply_plan(plan_path, source)

            output = root / "output.in"
            audit = Path(str(output) + ".audit.json")
            audit.write_text("existing", encoding="ascii")
            with self.assertRaisesRegex(ChangeError, "audit destination already exists"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())

            duplicate = root / "duplicate.in"
            duplicate.write_bytes(DECK.replace(b"absolute=1", b"absolute=1, absolute=2"))
            with self.assertRaisesRegex(ChangeError, "ambiguous"):
                plan_parameter_change(
                    duplicate, "BOUNDARY", "CONVERGENCE", "absolute", "3"
                )

    def test_unregistered_and_invalid_values_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            source.write_bytes(DECK)
            with self.assertRaisesRegex(ChangeError, "untyped edits are blocked"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "mystery", "1"
                )
            with self.assertRaisesRegex(ChangeError, "not a valid real"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "d_reduction", "nan"
                )

    def test_change_planning_rejects_unresolved_semantic_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.in"
            invalid = DECK.replace(
                b"*STOP\r\n",
                b"*ELEMENT,TYPE=C3D4\r\n1,99,99,99,99\r\n*STOP\r\n",
            )
            source.write_bytes(invalid)

            with self.assertRaisesRegex(ChangeError, "dependency validation"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
                )
            with self.assertRaisesRegex(ChangeError, "must be positive"):
                plan_parameter_change(
                    source, "BOUNDARY", "CONVERGENCE", "absolute", "-1"
                )

    def test_redigested_forged_plan_cannot_bypass_registered_typing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            plan_path = root / "forged.json"
            output = root / "changed.in"
            source.write_bytes(DECK)
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "absolute", "2"
            )
            plan["patch"]["new"] = "-1"
            content = {
                key: value for key, value in plan.items()
                if key not in {"plan_digest", "plan_id"}
            }
            digest = _plan_digest(content)
            plan["plan_digest"] = digest
            plan["plan_id"] = digest[:16]
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(ChangeError, "must be positive"):
                review_plan(plan_path)
            with self.assertRaisesRegex(ChangeError, "must be positive"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())

    def test_plan_is_bound_to_includes_and_preserves_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "model.in"
            include = root / "mesh.inc"
            plan_path = root / "change.json"
            output = root / "model.changed.in"
            source.write_bytes(DECK.replace(
                b"*STOP\r\n",
                b"*INCLUDE, FILE=mesh.inc\r\n*STOP\r\n",
            ))
            include.write_bytes(b"*NODE\r\n1, 0, 0, 0\r\n")
            plan = plan_parameter_change(
                source, "BOUNDARY", "CONVERGENCE", "d_reduction", "0.5"
            )
            self.assertIn("base_source_set_sha256", plan)
            self.assertIn("proposed_source_set_sha256", plan)
            write_plan(plan, plan_path)

            legacy = dict(plan)
            for field in (
                "workspace_root",
                "base_source_set_sha256",
                "proposed_source_set_sha256",
                "plan_digest",
                "plan_id",
            ):
                legacy.pop(field, None)
            legacy["schema_version"] = "1.1.0"
            legacy_digest = _plan_digest(legacy)
            legacy["plan_digest"] = legacy_digest
            legacy["plan_id"] = legacy_digest[:16]
            legacy_path = root / "legacy.json"
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
            with self.assertRaisesRegex(ChangeError, "legacy change plan"):
                review_plan(legacy_path)

            include.write_bytes(include.read_bytes() + b"** changed\r\n")
            with self.assertRaisesRegex(ChangeError, "source set changed after planning"):
                review_plan(plan_path)
            with self.assertRaisesRegex(ChangeError, "source set changed after planning"):
                apply_plan(plan_path, output)
            self.assertFalse(output.exists())

            include.write_bytes(b"*NODE\r\n1, 0, 0, 0\r\n")
            outside_directory = root / "revision"
            outside_directory.mkdir()
            copied_result = apply_plan(plan_path, outside_directory / "model.changed.in")
            self.assertEqual(
                include.read_bytes(), (outside_directory / "mesh.inc").read_bytes()
            )
            self.assertEqual(2, len(copied_result["output_files"]))
            self.assertEqual(
                copied_result["output_source_set_sha256"],
                SourceSet.read(outside_directory / "model.changed.in").sha256,
            )

            conflict_directory = root / "conflict-revision"
            conflict_directory.mkdir()
            (conflict_directory / "mesh.inc").write_bytes(b"occupied")
            with self.assertRaisesRegex(ChangeError, "source-set output already exists"):
                apply_plan(plan_path, conflict_directory / "model.changed.in")
            self.assertFalse((conflict_directory / "model.changed.in").exists())

            result = apply_plan(plan_path, output)
            self.assertEqual(
                plan["proposed_source_set_sha256"],
                result["output_source_set_sha256"],
            )
            self.assertEqual(
                result["output_source_set_sha256"],
                SourceSet.read(output).sha256,
            )
            audit = json.loads(Path(result["audit"]).read_text(encoding="utf-8"))
            self.assertEqual(
                result["output_source_set_sha256"],
                audit["output_source_set_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
