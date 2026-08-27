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
        self.assertEqual(11, counts["constructs"])
        self.assertGreaterEqual(counts["evidence"], 27)

    def test_pinned_baseline(self) -> None:
        target = self.registry["target"]
        self.assertEqual("2.4", target["product_version"])
        self.assertEqual(
            "7e414be55abae10e2a648bd39bcc07b4904e9edc",
            target["source_commit"],
        )
        self.assertEqual(
            "580B7AF434BF4F453B8137802246FEB292DD89A04FDB3DD54000EC9A225E146F",
            target["executable_sha256"],
        )

    def test_required_current_block_names(self) -> None:
        blocks = {item["canonical"]: item for item in self.registry["top_level_blocks"]}
        self.assertTrue(blocks["INPUT"]["required"])
        self.assertTrue(blocks["CLUSTERS"]["required"])
        self.assertEqual("exact", blocks["CLUSTERS"]["match_rule"])
        self.assertTrue(blocks["MATERIALS"]["required"])
        self.assertEqual("exact", blocks["MATERIALS"]["match_rule"])

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
