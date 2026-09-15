from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tools import registry_tools


class RegistryToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry_path = registry_tools.DEFAULT_REGISTRY
        cls.registry = registry_tools.load_registry(cls.registry_path)

    def test_every_active_construct_has_a_typed_read_contract(self) -> None:
        active = [
            *self.registry["top_level_blocks"],
            *self.registry["cluster_commands"],
            *self.registry["nested_constructs"],
        ]

        self.assertEqual(54, len(active))
        self.assertEqual([], [
            item["id"] for item in active
            if any(
                item.get("operations", {}).get(operation)
                not in {"implemented", "verified"}
                for operation in ("parse", "semantic", "inspect")
            )
        ])

    def test_registry_invariants(self) -> None:
        counts = registry_tools.validate_registry(self.registry)
        self.assertEqual(13, counts["blocks"])
        self.assertEqual(29, counts["commands"])
        self.assertEqual(12, counts["constructs"])
        self.assertEqual(1, counts["generation_profiles"])
        self.assertEqual(3, counts["transformations"])
        self.assertEqual(3, counts["dependency_classes"])
        self.assertEqual(44, counts["primary_entity_capabilities"])
        self.assertEqual(13, counts["additional_entity_outputs"])
        self.assertEqual(25, counts["reference_contracts"])
        self.assertEqual(4, counts["read_routes"])
        self.assertEqual(23, counts["mutation_routes"])
        self.assertEqual(5, counts["repository_checks"])
        self.assertEqual(2, counts["generated_artifacts"])
        self.assertEqual(11, counts["operation_impacts"])
        self.assertEqual(10, counts["clarification_triggers"])
        self.assertEqual(5, counts["obsolete_tokens"])
        self.assertEqual(85, counts["evidence"])

    def test_execution_contract_includes_guarded_tric_evidence(self) -> None:
        execution = self.registry["execution_contract"]
        self.assertIn("evidence.runtime-tric-guarded-execution", execution["evidence_ids"])

    def test_every_capability_has_an_explicit_entity_output(self) -> None:
        active = [
            *self.registry["top_level_blocks"],
            *self.registry["cluster_commands"],
            *self.registry["nested_constructs"],
        ]
        contract = self.registry["entity_contract"]
        no_primary = set(contract["no_primary_entity_capabilities"])
        self.assertEqual(
            no_primary,
            {item["id"] for item in active if not item.get("entity_kind")},
        )
        self.assertEqual(44, sum(bool(item.get("entity_kind")) for item in active))
        additional = {
            (capability_id, item["entity_kind"])
            for item in contract["additional_entity_outputs"]
            for capability_id in item["capability_ids"]
        }
        self.assertIn(("command.ngen", "node"), additional)
        self.assertIn(("command.elgen", "element"), additional)
        self.assertIn(("block.materials", "material-parameter"), additional)
        self.assertIn(("block.materials", "structured-material"), additional)
        self.assertIn(("command.node", "node-set"), additional)
        self.assertIn(("command.element", "element-set"), additional)
        self.assertIn(("construct.boundary-solver-schedule", "solver"), additional)
        self.assertIn(
            ("construct.boundary-loading-sequence", "load-change"), additional,
        )

    def test_dependency_and_decision_classes_are_disjoint(self) -> None:
        contract = self.registry["dependency_contract"]
        classes = {item["id"]: item for item in contract["classes"]}
        self.assertEqual({
            "structural-reference", "bsam-semantic-constraint", "engineering-decision",
        }, set(classes))
        structural = set(classes["structural-reference"]["reference_kinds"])
        semantic = set(classes["bsam-semantic-constraint"]["reference_kinds"])
        self.assertEqual(set(), structural & semantic)
        self.assertEqual(36, len(structural | semantic))
        self.assertEqual([], classes["engineering-decision"]["reference_kinds"])
        contracts = contract["reference_contracts"]
        contracted = {kind for item in contracts for kind in item["kinds"]}
        self.assertEqual(structural | semantic, contracted)
        self.assertTrue(all(item["forward_policy"] for item in contracts))
        self.assertTrue(all(item["reverse_policy"] for item in contracts))
        sources = {
            item["id"]: item["requires_user_input"]
            for item in contract["decision_sources"]
        }
        self.assertEqual({"user-approved": True, "source-derived": False}, sources)

    def test_every_reference_kind_is_named_by_a_regression_test(self) -> None:
        test_root = Path(__file__).parent
        test_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in test_root.glob("test_*.py")
            if path.name != Path(__file__).name
        )
        kinds = {
            kind
            for item in self.registry["dependency_contract"]["reference_contracts"]
            for kind in item["kinds"]
        }
        missing = sorted(
            kind for kind in kinds
            if re.search(rf"['\"]{re.escape(kind)}['\"]", test_text) is None
        )
        self.assertEqual([], missing)

    def test_every_active_canonical_family_is_named_by_a_regression_test(self) -> None:
        test_root = Path(__file__).parent
        test_text = "\n".join(
            path.read_text(encoding="utf-8").casefold()
            for path in test_root.glob("test_*.py")
            if path.name != Path(__file__).name
        )
        active = [
            *self.registry["top_level_blocks"],
            *self.registry["cluster_commands"],
            *self.registry["nested_constructs"],
        ]
        self.assertEqual([], [
            item["id"] for item in active
            if item["canonical"].casefold() not in test_text
        ])

    def test_every_classified_diagnostic_code_is_named_by_a_regression_test(self) -> None:
        test_root = Path(__file__).parent
        test_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in test_root.glob("test_*.py")
            if path.name != Path(__file__).name
        )
        document_source = (
            registry_tools.REPO_ROOT / "src" / "bsam_agent" / "document.py"
        ).read_text(encoding="utf-8")
        classified = set(re.findall(r'"(BSAM-[EWI][0-9]{3})":', document_source))
        self.assertEqual([], sorted(
            code for code in classified if code not in test_text
        ))

    def test_engineering_clarifications_cover_registered_user_choices(self) -> None:
        triggers = self.registry["dependency_contract"]["clarification_triggers"]
        self.assertEqual(10, len(triggers))
        self.assertTrue(all(
            item["decision_source"] == "user-approved"
            and item["condition"] and item["required_choices"]
            for item in triggers
        ))
        profile = self.registry["generation_profiles"][0]
        profile_choices = {
            choice for item in triggers
            if profile["id"] in item["scope_ids"] and "generate" in item["operations"]
            for choice in item["required_choices"]
        }
        self.assertEqual(set(profile["required_choices"]), profile_choices)
        for transformation in self.registry["transformations"]:
            expected = {
                item["name"] for item in transformation["decisions"]
                if item["source"] == "user-approved"
            }
            actual = {
                choice for item in triggers
                if transformation["id"] in item["scope_ids"]
                and "transform" in item["operations"]
                for choice in item["required_choices"]
            }
            self.assertEqual(expected, actual, transformation["id"])

    def test_change_impacts_cover_every_supported_entity_operation(self) -> None:
        active = [
            *self.registry["top_level_blocks"],
            *self.registry["cluster_commands"],
            *self.registry["nested_constructs"],
        ]
        expected = {
            (operation, item["id"])
            for item in active
            for operation in ("create", "delete", "rename")
            if item.get("operations", {}).get(operation) in {"implemented", "verified"}
        }
        contract = self.registry["change_contract"]
        actual = {
            (item["operation"], capability_id)
            for item in contract["operation_impacts"]
            for capability_id in item["capability_ids"]
        }
        self.assertEqual(expected, actual)
        self.assertEqual(11, len(actual))
        self.assertTrue(all(
            item["direct_impacts"] and item["dependent_checks"]
            for item in contract["operation_impacts"]
        ))
        self.assertEqual(
            {item["id"] for item in self.registry["transformations"]},
            set(contract["transformation_ids"]),
        )

    def test_consumer_routes_cover_every_supported_capability_operation(self) -> None:
        active = [
            *self.registry["top_level_blocks"],
            *self.registry["cluster_commands"],
            *self.registry["nested_constructs"],
        ]
        contract = self.registry["consumer_contract"]
        self.assertEqual(
            {"parse", "semantic", "inspect", "static_validation"},
            {
                operation
                for item in contract["read_routes"]
                for operation in item["operations"]
            },
        )
        expected = {
            (operation, item["id"])
            for item in active
            for operation in ("modify", "create", "delete", "rename")
            if item.get("operations", {}).get(operation) in {"implemented", "verified"}
        }
        actual = {
            (item["operation"], capability_id)
            for item in contract["mutation_routes"]
            for capability_id in item["capability_ids"]
        }
        self.assertEqual(expected, actual)
        self.assertEqual(23, len(actual))
        self.assertEqual(
            {
                "preview_parameter_change", "preview_parameter_removal",
                "preview_modify_entity", "preview_create_entity",
                "preview_delete_entity", "preview_rename_entity",
            },
            {tool for item in contract["mutation_routes"] for tool in item["tools"]},
        )

    def test_repository_checks_cover_generated_specification_artifacts(self) -> None:
        contract = self.registry["repository_check_contract"]
        self.assertEqual({
            "registry-invariants", "schema-version-binding", "generated-reference",
            "committed-dispatch-coverage", "ci-command-binding",
        }, set(contract["required_checks"]))
        self.assertEqual({
            "docs/bsam/reference/BSAM_2_4_INPUT_API.md",
            "docs/bsam/DISPATCH_AUDIT.md",
        }, {item["path"] for item in contract["generated_artifacts"]})
        self.assertEqual(
            ["live-source-dispatch"],
            [item["id"] for item in contract["optional_checks"]],
        )

    def test_pinned_baseline(self) -> None:
        target = self.registry["target"]
        self.assertEqual("2.4", target["product_version"])
        self.assertEqual(
            "9954027f1c325c63d58aeb836e8fec41a4b363af",
            target["source_commit"],
        )
        self.assertEqual(
            "7AE34D9821C6FE017897B020D615BFFA8A33F33F6D3734EBA3FD5A435788FB2A",
            target["executable_sha256"],
        )

    def test_generation_profile_requires_explicit_engineering_choices(self) -> None:
        profile = self.registry["generation_profiles"][0]
        self.assertEqual("generation.mechanical-isotropic-solid-v1", profile["id"])
        self.assertEqual("verified", profile["status"])
        self.assertIn("material.youngs_modulus", profile["required_choices"])
        self.assertIn("constraints", profile["required_choices"])
        self.assertIn("loads", profile["required_choices"])
        self.assertEqual("1.3.0", profile["profile_version"])
        self.assertIn("command.selection", profile["capabilities"])

    def test_required_current_block_names(self) -> None:
        blocks = {item["canonical"]: item for item in self.registry["top_level_blocks"]}
        self.assertTrue(blocks["INPUT"]["required"])
        self.assertTrue(blocks["CLUSTERS"]["required"])
        self.assertEqual("exact-case-sensitive", blocks["CLUSTERS"]["match_rule"])
        self.assertTrue(blocks["MATERIALS"]["required"])
        self.assertEqual("exact-case-sensitive", blocks["MATERIALS"]["match_rule"])
        self.assertEqual("SOLVER", blocks["SOLVER"]["lookup_token"])
        self.assertIn("STATISTICAL", blocks)
        for name, block in blocks.items():
            if name != "INPUT":
                self.assertEqual("exact-case-sensitive", block["match_rule"], name)

    def test_current_input_mode_is_fully_bounded(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "INPUT")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        variant = block["body"]["variants"][0]
        self.assertEqual("const(3)", variant["rows"][0]["fields"][0]["value_type"])

    def test_command_dispatch_prefixes_are_five_characters(self) -> None:
        for command in self.registry["cluster_commands"]:
            self.assertEqual(5, len(command["dispatch_prefix"]), command["id"])
            self.assertTrue(command["dispatch_prefix"].startswith("*"), command["id"])

    def test_core_edit_dependencies_are_structured(self) -> None:
        commands = {item["canonical"]: item for item in self.registry["cluster_commands"]}
        for token in ("*DIMENSIONS", "*NODE", "*ELEMENT", "*NSET", "*ELSET", "*INTEGRATION", "*ORIENTATION", "*SECTION"):
            self.assertIn("body", commands[token], token)
        self.assertEqual("verified", commands["*ORIENTATION"]["operations"]["static_validation"])
        self.assertEqual([], commands["*ORIENTATION"]["remaining_work"])
        section = commands["*SECTION"]
        self.assertEqual("count-from-command-parameter", section["body"]["variants"][0]["rows"][0]["repetition"])
        self.assertTrue(any("atomically" in item for item in section["body"]["dependencies"]))

    def test_cluster_control_and_load_grammars_are_registered(self) -> None:
        commands = {item["canonical"]: item for item in self.registry["cluster_commands"]}
        for token in ("*TYPE", "*NAME", "*CONSTITUTIVE", "*LOAD", "*BUILD", "*SPACING"):
            self.assertEqual("documented", commands[token]["coverage"], token)
            self.assertIn("body", commands[token], token)
        self.assertEqual(["solid"], commands["*TYPE"]["parameters"][0]["allowed_values"])
        load_text = json.dumps(commands["*LOAD"]).lower()
        self.assertIn("integer(1..3)", load_text)
        self.assertIn("replace earlier values", load_text)
        self.assertEqual("verified", commands["*LOAD"]["operations"]["static_validation"])
        spacing = {item["name"]: item for item in commands["*SPACING"]["parameters"]}
        self.assertEqual(["STRICT", "VALUE", "RELAXED"], spacing["mode"]["allowed_values"])
        self.assertEqual("STRICT", spacing["mode"]["default"])
        self.assertEqual("verified", commands["*SPACING"]["operations"]["static_validation"])
        self.assertIn("idempotent", json.dumps(commands["*BUILD"]).lower())
        self.assertEqual("verified", commands["*BUILD"]["operations"]["static_validation"])
        for token in ("*TYPE", "*NAME", "*CONSTITUTIVE"):
            self.assertEqual("verified", commands[token]["operations"]["static_validation"])
            self.assertEqual("verified", commands[token]["operations"]["generate"])
            self.assertEqual("verified", commands[token]["operations"]["execute"])
        self.assertEqual("verified", commands["*STOP"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*STOP"]["operations"]["generate"])
        self.assertEqual("verified", commands["*STOP"]["operations"]["execute"])

    def test_field_selection_and_coordinate_operation_grammars_are_registered(self) -> None:
        commands = {item["canonical"]: item for item in self.registry["cluster_commands"]}
        for token in ("*FIELD", "*SELECTION", "*TOLERANCE", "*SHIFT", "*SCALE", "*EXCLUSION", "*FLIP"):
            self.assertEqual("documented", commands[token]["coverage"], token)
            self.assertIn("body", commands[token], token)
        field_text = json.dumps(commands["*FIELD"]).lower()
        self.assertIn("integer(1..10)", field_text)
        self.assertIn("generation is blocked", field_text)
        selection_text = json.dumps(commands["*SELECTION"]).lower()
        self.assertIn("at most ten", selection_text)
        self.assertIn("blocks individual element labels", selection_text)
        self.assertEqual("verified", commands["*SELECTION"]["operations"]["generate"])
        self.assertEqual("unsupported", commands["*SELECTION"]["operations"]["create"])
        self.assertEqual("verified", commands["*SELECTION"]["operations"]["execute"])
        self.assertEqual("verified", commands["*SELECTION"]["operations"]["static_validation"])
        self.assertEqual("positive-integer", {
            item["name"]: item for item in commands["*SELECTION"]["parameters"]
        }["ID"]["value_type"])
        self.assertEqual("unsupported", commands["*FIELD"]["operations"]["generate"])
        self.assertEqual("unassessed", commands["*FIELD"]["operations"]["execute"])
        self.assertEqual("verified", commands["*FIELD"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*DIMENSIONS"]["operations"]["generate"])
        self.assertEqual("verified", commands["*DIMENSIONS"]["operations"]["execute"])
        self.assertEqual("verified", commands["*DIMENSIONS"]["operations"]["static_validation"])
        dimension_fields = commands["*DIMENSIONS"]["body"]["variants"][0]["rows"][0]["fields"]
        self.assertTrue(all(item["value_type"] == "nonnegative-integer" for item in dimension_fields))
        self.assertIn("zero is valid", json.dumps(commands["*DIMENSIONS"]).lower())
        tolerance = {item["name"]: item for item in commands["*TOLERANCE"]["parameters"]}
        self.assertEqual("PTOL", tolerance["TYPE"]["default"])
        self.assertEqual("verified", commands["*TOLERANCE"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*SHIFT"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*SCALE"]["operations"]["static_validation"])
        exclusion = {item["name"]: item for item in commands["*EXCLUSION"]["parameters"]}
        self.assertEqual("BOX", exclusion["shape"]["default"])
        self.assertEqual("verified", commands["*EXCLUSION"]["operations"]["static_validation"])
        self.assertIn("xy=(-y,x,z)", json.dumps(commands["*FLIP"]).lower())
        self.assertEqual("verified", commands["*FLIP"]["operations"]["static_validation"])

    def test_generation_element_and_cluster_boundary_grammars_are_registered(self) -> None:
        commands = {item["canonical"]: item for item in self.registry["cluster_commands"]}
        for token in ("*NGEN", "*NCOPY", "*ELEMENT", "*ELGEN", "*BOUNDARY"):
            self.assertEqual("documented", commands[token]["coverage"], token)
            self.assertIn("body", commands[token], token)
        ngen_variants = {item["name"] for item in commands["*NGEN"]["body"]["variants"]}
        self.assertEqual(
            {"straight-between-nodes", "straight-between-paired-node-sets", "circular-arc"},
            ngen_variants,
        )
        self.assertEqual("verified", commands["*NCOPY"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*ELGEN"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*INTEGRATION"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*SECTION"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*BOUNDARY"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*NGEN"]["operations"]["static_validation"])
        self.assertEqual("verified", commands["*CRACK"]["operations"]["static_validation"])
        element_types = commands["*ELEMENT"]["parameters"][0]["allowed_values"]
        self.assertEqual(["C3D8", "Y3D8", "X3D8", "LC3D8", "C3D4", "C3D10", "B3D10"], element_types)
        self.assertNotIn("B3D10", commands["*ELGEN"]["parameters"][0]["allowed_values"])
        boundary_variants = {item["name"] for item in commands["*BOUNDARY"]["body"]["variants"]}
        self.assertEqual({"abaqus-style", "list-directed", "polynomial"}, boundary_variants)
        self.assertIn("stale loop variable", json.dumps(commands["*BOUNDARY"]).lower())

        clusters = next(
            item for item in self.registry["top_level_blocks"]
            if item["id"] == "block.clusters"
        )
        self.assertEqual("verified", clusters["operations"]["static_validation"])
        boundary = next(
            item for item in self.registry["top_level_blocks"]
            if item["id"] == "block.boundary"
        )
        self.assertEqual("verified", boundary["operations"]["static_validation"])

    def test_every_cluster_command_has_a_documented_grammar(self) -> None:
        self.assertEqual(
            [],
            [item["canonical"] for item in self.registry["cluster_commands"] if item["coverage"] != "documented"],
        )
        commands = {item["canonical"]: item for item in self.registry["cluster_commands"]}
        crack_variants = {item["name"] for item in commands["*CRACK"]["body"]["variants"]}
        self.assertIn("blocked-definition", crack_variants)
        self.assertIn("region-by-cylinder", crack_variants)
        self.assertIn("parsed but ignored", json.dumps(commands["*TRANSFORM"]).lower())
        self.assertEqual(
            "verified", commands["*TRANSFORM"]["operations"]["static_validation"],
        )
        self.assertIn("root cluster stream", json.dumps(commands["*STOP"]).lower())
        self.assertIn("include cycles", json.dumps(commands["*INCLUDE"]).lower())

    def test_boundary_active_constructs_are_registered(self) -> None:
        tokens = {item["canonical"] for item in self.registry["nested_constructs"]}
        self.assertTrue({"*TYPE", "*BOUNDARY CONDITION", "*LOADING SEQUENCE", "*CONVERGENCE", "*OUTPUT"} <= tokens)

    def test_boundary_problem_control_and_condition_grammars_are_registered(self) -> None:
        constructs = {item["canonical"]: item for item in self.registry["nested_constructs"]}
        for token in ("*TYPE", "*G-CONTROL", "*NAME", "*STATUS", "*CLUSTERS", "*BOUNDARY CONDITION"):
            self.assertEqual("documented", constructs[token]["coverage"], token)
            self.assertIn("body", constructs[token], token)
        type_variants = {item["name"] for item in constructs["*TYPE"]["body"]["variants"]}
        self.assertEqual({"mechanical", "thermal", "blocked-contact"}, type_variants)
        self.assertEqual(
            "case-normalized-prefix-record(mech,ther,cont)",
            constructs["*TYPE"]["parameters"][0]["value_type"],
        )
        self.assertEqual("verified", constructs["*TYPE"]["operations"]["static_validation"])
        self.assertEqual("unsupported", constructs["*TYPE"]["operations"]["generate"])
        self.assertEqual("unassessed", constructs["*TYPE"]["operations"]["execute"])
        g_params = {item["name"]: item for item in constructs["*G-CONTROL"]["parameters"]}
        self.assertEqual(1000, g_params["G_ITER"]["default"])
        self.assertEqual(
            "verified", constructs["*G-CONTROL"]["operations"]["static_validation"],
        )
        self.assertEqual("restart", constructs["*STATUS"]["parameters"][0]["default"])
        condition_text = json.dumps(constructs["*BOUNDARY CONDITION"]).lower()
        self.assertIn("global-local-file", condition_text)
        self.assertIn("surface-stress", condition_text)
        self.assertIn("multi-file plan", condition_text)
        self.assertEqual("verified", constructs["*NAME"]["operations"]["static_validation"])
        self.assertEqual("verified", constructs["*NAME"]["operations"]["generate"])
        self.assertEqual("verified", constructs["*NAME"]["operations"]["execute"])

    def test_major_boundary_record_groups_have_structured_bodies(self) -> None:
        constructs = {item["canonical"]: item for item in self.registry["nested_constructs"]}
        for token in ("*CONNECTIONS", "*LOADING SEQUENCE", "*CONVERGENCE", "*OUTPUT"):
            self.assertEqual("documented", constructs[token]["coverage"], token)
            self.assertEqual([], constructs[token]["remaining_work"], token)
            self.assertIn("body", constructs[token], token)
            self.assertTrue(constructs[token]["body"]["dependencies"], token)
        convergence_text = json.dumps(constructs["*CONVERGENCE"]).lower()
        self.assertIn("maxiterations", convergence_text)
        self.assertIn("d_reduction", convergence_text)
        self.assertIn("long vtms labels are accepted", convergence_text)
        self.assertIn("d_aa", convergence_text)
        self.assertIn("twelve convergence records", convergence_text)
        connection_text = json.dumps(constructs["*CONNECTIONS"]).lower()
        self.assertEqual(
            "verified", constructs["*CONNECTIONS"]["operations"]["static_validation"],
        )
        self.assertIn("surface-contact", connection_text)
        self.assertIn("no -21 execution case", connection_text)
        loading_text = json.dumps(constructs["*LOADING SEQUENCE"]).lower()
        self.assertEqual(
            "verified",
            constructs["*LOADING SEQUENCE"]["operations"]["static_validation"],
        )
        self.assertIn("allocated fatigue fields have no source defaults", loading_text)
        self.assertIn("omit internal types 21, 22, and 31", loading_text)
        output_text = json.dumps(constructs["*OUTPUT"]).lower()
        self.assertIn("enum-prefix(tecplot,vtk,para)", output_text)
        self.assertIn("do not consume it", output_text)
        self.assertIn("evidence.runtime-vtk-data-file", constructs["*OUTPUT"]["evidence_ids"])
        self.assertIn("single-cluster mechanical-isotropic", output_text)
        self.assertIn("paraview/sheff", output_text)
        self.assertEqual("unassessed", constructs["*OUTPUT"]["operations"]["execute"])

    def test_every_boundary_construct_has_a_documented_grammar(self) -> None:
        self.assertEqual(
            [],
            [item["canonical"] for item in self.registry["nested_constructs"] if item["coverage"] != "documented"],
        )
        boundary = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "BOUNDARY")
        self.assertEqual("documented", boundary["coverage"])
        self.assertEqual([], boundary["remaining_work"])

    def test_boundary_solver_schedule_is_registered(self) -> None:
        constructs = {item["canonical"]: item for item in self.registry["nested_constructs"]}
        schedule = constructs["*SOLVER"]
        self.assertEqual([1, 2], schedule["parameters"][0]["allowed_values"])

    def test_solver_grammar_and_legacy_policy_are_registered(self) -> None:
        solver = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "SOLVER")
        self.assertEqual("documented", solver["coverage"])
        self.assertEqual([], solver["remaining_work"])
        parameters = {item["name"]: item for item in solver["parameters"]}
        self.assertEqual(["mkl", "petsc"], parameters["backend"]["allowed_values"])
        self.assertEqual("cg", parameters["solver"]["default"])
        self.assertIn("gmes", parameters["solver"]["allowed_values"])
        self.assertNotIn("gmres", parameters["solver"]["allowed_values"])
        variants = {item["name"]: item for item in solver["body"]["variants"]}
        self.assertIn("current-pardiso", variants)
        self.assertIn("current-sheff", variants)
        legacy = json.dumps(variants["legacy-numeric"]).lower()
        self.assertIn("diagnostics only", legacy)
        self.assertIn("notch_v1", legacy)

    def test_ufunction_spline_contract_is_registered(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "UFUNCTIONS")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        variant = block["body"]["variants"][0]
        rows = {item["name"]: item for item in variant["rows"]}
        self.assertEqual(["x", "y"], [item["name"] for item in rows["data-point"]["fields"]])
        contract = json.dumps(block).lower()
        self.assertIn("strictly increasing or strictly decreasing", contract)
        self.assertIn("ufunc_<name>", contract)
        self.assertIn("must be lowercase", contract)

    def test_moisture_external_integration_is_bounded(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "MOISTURE")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        self.assertEqual("mdsim", parameters["program"]["default"])
        self.assertEqual("positive-integer-list", parameters["steps"]["value_type"])
        contract = json.dumps(block).lower()
        self.assertIn("blocked by default", contract)
        self.assertIn("mdsim.conf", contract)
        self.assertIn("disables moisture rather than stopping", contract)
        self.assertEqual("verified", block["operations"]["static_validation"])

    def test_global_crack_static_contract_is_verified(self) -> None:
        block = next(
            item for item in self.registry["top_level_blocks"]
            if item["id"] == "block.crack"
        )
        self.assertEqual("verified", block["operations"]["static_validation"])
        self.assertIn("fewer than 250", json.dumps(block).lower())

    def test_numeric_user_static_contract_is_verified(self) -> None:
        block = next(
            item for item in self.registry["top_level_blocks"]
            if item["id"] == "block.user"
        )
        self.assertEqual("verified", block["operations"]["static_validation"])
        self.assertIn("disabled-sentinel", {
            item["name"] for item in block["body"]["variants"]
        })

    def test_material_static_contract_is_verified(self) -> None:
        block = next(
            item for item in self.registry["top_level_blocks"]
            if item["id"] == "block.materials"
        )
        self.assertEqual("verified", block["operations"]["static_validation"])
        self.assertEqual(28, len(block["parameters"][0]["allowed_values"]) - 1)

    def test_explicit_mesh_record_limits_are_closed(self) -> None:
        commands = {item["id"]: item for item in self.registry["cluster_commands"]}
        for capability in ("command.node", "command.element"):
            self.assertEqual([], commands[capability]["remaining_work"])
            self.assertIn("999999", json.dumps(commands[capability]))

    def test_mesh_set_membership_limits_are_closed(self) -> None:
        commands = {item["id"]: item for item in self.registry["cluster_commands"]}
        for capability in ("command.nset", "command.elset"):
            self.assertEqual([], commands[capability]["remaining_work"])
            contract = json.dumps(commands[capability]).lower()
            self.assertIn("duplicate membership", contract)
            self.assertIn("100000", contract)

    def test_cluster_reverse_dependency_gap_is_closed(self) -> None:
        clusters = next(
            item for item in self.registry["top_level_blocks"]
            if item["id"] == "block.clusters"
        )
        self.assertEqual([], clusters["remaining_work"])

    def test_table_grid_and_interpolation_contract_is_registered(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "TABLES")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        self.assertEqual(["temp", "moisture", "time", "fvf"], parameters["row_label"]["allowed_values"])
        variant = block["body"]["variants"][0]
        rows = {item["name"]: item for item in variant["rows"]}
        self.assertEqual("real-list(horizontal-count)", rows["data-row"]["fields"][1]["value_type"])
        contract = json.dumps(block).lower()
        self.assertIn("strictly increasing", contract)
        self.assertIn("bilinear interpolation", contract)
        self.assertIn("table_<name>", contract)
        self.assertIn("clamp", contract)

    def test_statistical_weibull_contract_is_registered(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "STATISTICAL")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        self.assertEqual([3], parameters["type"]["allowed_values"])
        self.assertEqual(["coordinates", "fiber", "fibers"], parameters["seeding"]["allowed_values"])
        variant = block["body"]["variants"][0]
        rows = {item["name"]: item for item in variant["rows"]}
        self.assertEqual("<seeding-value>", rows["seed-grid"]["fields"][0]["name"])
        contract = json.dumps(block).lower()
        self.assertIn("must follow seeding", contract)
        self.assertIn("exactly three positive", contract)
        self.assertIn("stat_<name>_<initial-value>", contract)
        self.assertIn("generation=0", contract)

    def test_material_types_and_structured_grammars_are_registered(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "MATERIALS")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        numeric_types = [value for value in parameters["type"]["allowed_values"] if isinstance(value, int)]
        self.assertEqual(28, len(numeric_types))
        self.assertIn("mises", parameters["type"]["allowed_values"])
        self.assertIn("hkin", parameters["structured_bulk_key"]["allowed_values"])
        self.assertIn("penalty_stiffness", parameters["structured_interface_key"]["allowed_values"])
        variants = {item["name"]: item for item in block["body"]["variants"]}
        self.assertEqual(15, len(variants))
        for name in (
            "legacy-orthotropic-family",
            "legacy-isotropic-type-10",
            "legacy-interface-type-12",
            "legacy-anisotropic-types-2-and-3",
            "heterogeneous-types-200-and-210",
            "compro-type-800",
        ):
            self.assertIn(name, variants)
        contract = json.dumps(block).lower()
        self.assertIn("load_vector keyword has no dispatch case", contract)
        self.assertIn("canonical generation uses initval", contract)
        self.assertIn("table_<name>", contract)
        self.assertIn("replace the entire type-specific body atomically", contract)
        self.assertIn("eight rows per element", contract)
        self.assertIn("blocks creation until a runtime-verified", contract)
        self.assertIn("types 15, 300, 500, and 998", contract)
        self.assertIn("b3d10 input alias normalized to c3d10", contract)
        self.assertIn("stress-per-length", contract)
        self.assertIn("mass-per-volume", contract)
        self.assertIn("return huge", contract)
        self.assertIn("as ply thickness", contract)
        self.assertIn("rho/density", contract)

    def test_numeric_user_function_variants_are_bounded(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "USER")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        self.assertEqual([1, 2, 3, 4, 5, 101, 201], parameters["type"]["allowed_values"])
        variants = {item["name"]: item for item in block["body"]["variants"]}
        self.assertEqual(8, len(variants))
        self.assertIn("inline-spline-type-101", variants)
        self.assertIn("inline-curve-type-201", variants)
        blocked_external = json.dumps(variants["external-spline-type-100"]).lower()
        blocked_sparse = json.dumps(variants["blocked-sparse-matrix-type-301"]).lower()
        self.assertIn("blocked from agent generation", blocked_external)
        self.assertIn("blocked from generation", blocked_sparse)
        self.assertIn("uninitialized nparam/ncoeff", blocked_sparse)

    def test_active_crack_grammar_is_bounded(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "CRACK")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        self.assertEqual([101, 201, 301], parameters["type"]["allowed_values"])
        self.assertEqual("fiber", parameters["orientation"]["default"])
        active = next(
            item for item in block["body"]["variants"]
            if item["name"] == "active-fe-crack-types"
        )
        rows = {item["name"]: item for item in active["rows"]}
        self.assertEqual("predefined_count-times", rows["predefined-crack"]["repetition"])
        contract = json.dumps(block)
        self.assertIn("*MODE_CRACKS", contract)
        self.assertIn("at most eight option slots", contract)
        self.assertIn("unreachable and blocked from generation", contract)

    def test_constitutive_variants_and_blocked_wrappers_are_registered(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "CONSTITUTIVE")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8, 10], parameters["type"]["allowed_values"])
        variants = {item["name"]: item for item in block["body"]["variants"]}
        self.assertIn("optional-common-modifiers", variants)
        self.assertIn("blocked-time-step-wrapper-type-21", variants)
        self.assertIn("blocked-indexed-interval-types-11-to-13", variants)
        self.assertIn("blocked-coordinate-interval-types-110-120-130", variants)
        modifiers = json.dumps(variants["optional-common-modifiers"])
        self.assertIn("one-to-three-positive-constitutive-ids", modifiers)
        self.assertIn("no active consumer", modifiers)
        blocked = json.dumps([variant for name, variant in variants.items() if name.startswith("blocked-")]).lower()
        self.assertIn("uninitialized local nx, ny, or nz", blocked)
        self.assertIn("current active finite-element path does not call", blocked)

    def test_failure_families_and_wrapper_dependencies_are_registered(self) -> None:
        block = next(item for item in self.registry["top_level_blocks"] if item["canonical"] == "FAILURE")
        self.assertEqual("documented", block["coverage"])
        self.assertEqual([], block["remaining_work"])
        parameters = {item["name"]: item for item in block["parameters"]}
        self.assertEqual(37, len(parameters["type"]["allowed_values"]))
        self.assertEqual(10, parameters["cfactor"]["default"])
        variants = {item["name"]: item for item in block["body"]["variants"]}
        self.assertEqual(8, len(variants))
        self.assertIn("critical-failure-volume-type-18", variants)
        self.assertIn("cohesive-fatigue-wrappers-22-and-29", variants)
        maximum_stress = json.dumps(variants["maximum-stress-degradation-types-1-and-2"])
        self.assertIn("10-times-for-type-1-or-11-times-for-type-2", maximum_stress)
        larc04 = json.dumps(variants["larc04-type-26"])
        self.assertIn("must be on the type line", larc04)
        self.assertIn("initializes CFACTOR to 10", larc04)
        dependencies = " ".join(block["body"]["dependencies"])
        self.assertIn("without cycles", dependencies)

    def test_notch_transformation_rules_are_registered(self) -> None:
        transformations = self.registry["transformations"]
        self.assertEqual(3, len(transformations))
        transformation = next(
            item for item in transformations if item["id"] == "transformation.notch-expand-plies"
        )
        self.assertEqual("transformation.notch-expand-plies", transformation["id"])
        self.assertEqual("1.0.0", transformation["algorithm_version"])
        self.assertEqual("runtime-verified", transformation["coverage"])
        self.assertEqual("preview_expand_notch_plies", transformation["tool"])
        paths = {item["path"] for item in transformation["applicability"]}
        self.assertIn("CLUSTERS.z_extents", paths)
        decisions = {item["name"]: item for item in transformation["decisions"]}
        self.assertEqual(2.0, decisions["total_thickness"]["value"])
        self.assertEqual("user-approved", decisions["interface_constitutive"]["source"])

    def test_solver_migration_rules_are_registered(self) -> None:
        transformation = next(
            item for item in self.registry["transformations"]
            if item["id"] == "transformation.migrate-legacy-solver"
        )
        self.assertEqual("1.1.0", transformation["algorithm_version"])
        self.assertEqual("runtime-verified", transformation["coverage"])
        self.assertEqual("preview_migrate_legacy_solver", transformation["tool"])
        paths = {item["path"] for item in transformation["applicability"]}
        self.assertIn("BASELINE.execution_mode", paths)
        decisions = {item["name"]: item for item in transformation["decisions"]}
        self.assertEqual("pardiso", decisions["target_solver"]["value"])

    def test_structured_cluster_copy_contract_separates_choices_and_invariants(self) -> None:
        transformation = next(
            item for item in self.registry["transformations"]
            if item["id"] == "transformation.structured-cluster-copy"
        )
        self.assertEqual("0.1.0", transformation["algorithm_version"])
        self.assertEqual("identified", transformation["coverage"])
        self.assertEqual("preview_structured_construction", transformation["tool"])
        decisions = {item["name"]: item["source"] for item in transformation["decisions"]}
        self.assertEqual("user-approved", decisions["instance_names_and_transforms"])
        self.assertEqual("user-approved", decisions["orientation_policy"])
        self.assertEqual("source-derived", decisions["local_label_policy"])
        self.assertEqual("source-derived", decisions["topology_and_set_policy"])
        trigger = next(
            item for item in self.registry["dependency_contract"]["clarification_triggers"]
            if item["id"] == "clarification.structured-cluster-copy"
        )
        self.assertEqual(
            {
                "source_cluster", "instance_names_and_transforms",
                "material_and_section_policy", "orientation_policy",
            },
            set(trigger["required_choices"]),
        )

    def test_last_record_wins_parameter_cardinality_is_explicit(self) -> None:
        solver = next(
            item for item in self.registry["top_level_blocks"]
            if item["id"] == "block.solver"
        )
        convergence = next(
            item for item in self.registry["nested_constructs"]
            if item["id"] == "construct.boundary-convergence"
        )
        repeated = {
            (record["id"], parameter["name"])
            for record in (solver, convergence)
            for parameter in record["parameters"]
            if parameter.get("cardinality") == "repeated-last-wins"
        }
        self.assertEqual({
            ("block.solver", "relative_tolerance"),
            ("construct.boundary-convergence", "maxiterations"),
        }, repeated)

    def test_obsolete_tokens_have_current_replacements(self) -> None:
        obsolete = {item["token"]: item for item in self.registry["obsolete_tokens"]}
        self.assertEqual("SOLVER", obsolete["SOLVE"]["replacement"])
        self.assertEqual("MATERIALS", obsolete["MATERIAL"]["replacement"])
        self.assertEqual("CLUSTERS", obsolete["APPROXIMATION"]["replacement"])
        self.assertEqual("STATISTICAL", obsolete["STATISTICAL DISTRIBUTIONS"]["replacement"])
        self.assertEqual("accepted-compatibility", obsolete["END APPROXIMATION"]["behavior"])

    def test_json_schema_is_local_and_parseable(self) -> None:
        schema_path = (self.registry_path.parent / self.registry["$schema"]).resolve()
        self.assertTrue(schema_path.is_relative_to(registry_tools.REPO_ROOT))
        with schema_path.open("r", encoding="utf-8") as stream:
            schema = json.load(stream)
        self.assertEqual("BSAM capability registry", schema["title"])
        self.assertEqual(self.registry["schema_version"], schema["properties"]["schema_version"]["const"])

    def test_generated_reference_is_deterministic_and_current(self) -> None:
        first = registry_tools.render_reference(self.registry, self.registry_path)
        second = registry_tools.render_reference(self.registry, self.registry_path)
        self.assertEqual(first, second)
        current = registry_tools.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(first, current)

    def test_source_evidence_contains_only_relative_locators(self) -> None:
        for evidence in self.registry["evidence"]:
            if evidence["kind"] != "source":
                continue
            locator = Path(evidence["locator"])
            self.assertFalse(locator.is_absolute())
            self.assertNotIn("..", locator.parts)
            self.assertIn(locator.parts[0], {"source", "sheff_modules"})


if __name__ == "__main__":
    unittest.main()
