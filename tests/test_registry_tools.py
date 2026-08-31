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
        self.assertEqual(34, counts["evidence"])

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
            self.assertEqual("source", locator.parts[0])


if __name__ == "__main__":
    unittest.main()
