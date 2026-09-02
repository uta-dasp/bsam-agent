from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import registry_tools


class RegistryToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry_path = registry_tools.DEFAULT_REGISTRY
        cls.registry = registry_tools.load_registry(cls.registry_path)

    def test_registry_invariants(self) -> None:
        counts = registry_tools.validate_registry(self.registry)
        self.assertEqual(13, counts["blocks"])
        self.assertEqual(29, counts["commands"])
        self.assertEqual(12, counts["constructs"])
        self.assertEqual(1, counts["transformations"])
        self.assertEqual(5, counts["obsolete_tokens"])
        self.assertEqual(44, counts["evidence"])

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
        section = commands["*SECTION"]
        self.assertEqual("count-from-command-parameter", section["body"]["variants"][0]["rows"][0]["repetition"])
        self.assertTrue(any("atomically" in item for item in section["body"]["dependencies"]))

    def test_boundary_active_constructs_are_registered(self) -> None:
        tokens = {item["canonical"] for item in self.registry["nested_constructs"]}
        self.assertTrue({"*TYPE", "*BOUNDARY CONDITION", "*LOADING SEQUENCE", "*CONVERGENCE", "*OUTPUT"} <= tokens)

    def test_major_boundary_record_groups_have_structured_bodies(self) -> None:
        constructs = {item["canonical"]: item for item in self.registry["nested_constructs"]}
        for token in ("*CONNECTIONS", "*LOADING SEQUENCE", "*CONVERGENCE", "*OUTPUT"):
            self.assertIn("body", constructs[token], token)
            self.assertTrue(constructs[token]["body"]["dependencies"], token)
        convergence_text = json.dumps(constructs["*CONVERGENCE"]).lower()
        self.assertIn("maxiterations", convergence_text)
        self.assertIn("d_reduction", convergence_text)
        self.assertIn("long vtms labels are accepted", convergence_text)
        self.assertIn("d_aa", convergence_text)
        self.assertIn("twelve convergence records", convergence_text)
        connection_text = json.dumps(constructs["*CONNECTIONS"]).lower()
        self.assertIn("surface-contact", connection_text)

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

    def test_notch_transformation_rules_are_registered(self) -> None:
        transformations = self.registry["transformations"]
        self.assertEqual(1, len(transformations))
        transformation = transformations[0]
        self.assertEqual("transformation.notch-expand-plies", transformation["id"])
        self.assertEqual("1.0.0", transformation["algorithm_version"])
        self.assertEqual("runtime-verified", transformation["coverage"])
        self.assertEqual("preview_expand_notch_plies", transformation["tool"])
        paths = {item["path"] for item in transformation["applicability"]}
        self.assertIn("CLUSTERS.z_extents", paths)
        decisions = {item["name"]: item for item in transformation["decisions"]}
        self.assertEqual(2.0, decisions["total_thickness"]["value"])
        self.assertEqual("user-approved", decisions["interface_constitutive"]["source"])

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
