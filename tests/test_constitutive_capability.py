from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.source_set import SourceSet
from bsam_agent.api import LocalAgentApi
from bsam_agent.orchestrator import ChatOrchestrator
from bsam_agent.provider import ProviderConfig


def constitutive_deck(body: str) -> bytes:
    return (
        "INPUT\n3\nEND INPUT\n"
        "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        f"CONSTITUTIVE\n{body}END CONSTITUTIVE\n"
        "FAILURE\n4\nEND FAILURE\n"
        "MATERIALS\n999\nE11=1\n*end\nEND MATERIALS\n"
        "CLUSTERS\n*type\nsolid\n*NAME\nply1\n*STOP\nEND CLUSTERS\n"
    ).encode("latin-1")


class ConstitutiveCapabilityTests(unittest.TestCase):
    def test_cluster_assignment_is_typed_resolved_and_registry_queryable(self) -> None:
        class NoCallProvider:
            def complete(self, _request):  # pragma: no cover - a call fails the test
                raise AssertionError("registry entity query should not call the provider")

        raw = constitutive_deck("1\n1 1 0\n").replace(
            b"*STOP", b"*CONSTITUTIVE\n1\n*STOP",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "model.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()
            result = ChatOrchestrator(
                NoCallProvider(),
                ProviderConfig(
                    "fake", "fake", "http://127.0.0.1", None,
                    1, 10000, 128, "local-only",
                ),
                LocalAgentApi(root),
            ).turn("List cluster assignments in model.in.")

        assignment = next(
            item for item in inspection["semantic_model"]["entities"]
            if item["kind"] == "cluster-constitutive"
        )
        reference = next(
            item for item in inspection["semantic_model"]["references"]
            if item["source_entity_id"] == assignment["id"]
        )
        self.assertEqual("cluster:ply1/cluster-constitutive:assignment", assignment["key"])
        self.assertEqual(1, assignment["attributes"]["constitutive"])
        self.assertEqual("constitutive:1", reference["target_key"])
        self.assertEqual("resolved", reference["status"])
        self.assertEqual("query_model", result.tool)
        self.assertEqual(1, result.tool_result["summary"]["matches"])
        self.assertEqual("cluster-constitutive", result.tool_result["matches"][0]["kind"])

    def test_registry_entity_terms_route_declaration_queries_without_provider(self) -> None:
        class NoCallProvider:
            def complete(self, _request):  # pragma: no cover - a call fails the test
                raise AssertionError("registry entity query should not call the provider")

        raw = constitutive_deck("1\n1 1 0\n11\n1\n1 1\n")
        prompts = (
            ("Show all constitutive definitions in model.in.", "constitutive", 2),
            ("List failure definitions in model.in.", "failure", 1),
            ("Show material definitions in model.in.", "material", 1),
            ("Show references for constitutive law 1 in model.in.", None, 1),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(raw)
            for prompt, kind, count in prompts:
                agent = ChatOrchestrator(
                    NoCallProvider(),
                    ProviderConfig(
                        "fake", "fake", "http://127.0.0.1", None,
                        1, 10000, 128, "local-only",
                    ),
                    LocalAgentApi(root),
                )
                result = agent.turn(prompt)
                self.assertEqual("query_model", result.tool)
                self.assertEqual(count, result.tool_result["summary"]["matches"])
                if kind is not None:
                    self.assertTrue(all(
                        item["kind"] == kind for item in result.tool_result["matches"]
                    ))

    def test_all_direct_layouts_and_wrapper_bodies_are_consumed_in_order(self) -> None:
        raw = constitutive_deck(
            "1 # direct one\n"
            "\t*xyzload\n\t*mic= 2,3\n\t*fatigue 4\n\t1 1 0\n"
            "2\n\t1 1 0 0 0\n"
            "3\n\t1 1 0 1 2 3 4 0\n"
            "4\n\t1 1 0 1 2 3 4 5 6 0\n"
            "5\n\t1 1 1\n"
            "6\n\t1 1 1 2\n"
            "7\n\t1 1\n"
            "8\n\t1 1\n"
            "10\n\t1 1 0\n"
            "11\n\t2\n\t1 1\n\t2 2\n"
            "110\n\t1 7\n\t1 3\n"
            "21\n\t1\n\t1 4\n"
        ).replace(
            b"CLUSTERS\n",
            b"USER\n" + b"1\n0\n1\n" * 6 + b"END USER\nCLUSTERS\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            source_set = SourceSet.read(path)
            inspection = source_set.inspection()
            rendered = source_set.render_files()[path.resolve()]

        semantic = inspection["semantic_model"]
        entities = [item for item in semantic["entities"] if item["kind"] == "constitutive"]
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 110, 21], [
            item["attributes"]["type"] for item in entities
        ])
        self.assertEqual([1, 2], entities[9]["attributes"]["constitutive_ids"])
        self.assertEqual(7, entities[10]["attributes"]["property_subdivision_id"])
        references = [
            item for item in semantic["references"] if item["kind"] == "uses-constitutive"
        ]
        self.assertEqual(6, len(references))
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(9, len([
            item for item in semantic["references"] if item["kind"] == "uses-material"
        ]))
        self.assertEqual(9, len([
            item for item in semantic["references"] if item["kind"] == "uses-failure"
        ]))
        records = [
            item for item in semantic["capability_records"]
            if item["capability_id"] == "block.constitutive"
        ]
        self.assertEqual(12, len(records))
        self.assertTrue(all(item["operations"]["parse"] == "verified" for item in records))
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(raw, rendered)

    def test_incomplete_wrapper_stops_without_inventing_later_declarations(self) -> None:
        raw = constitutive_deck("11\n2\n1 1\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()

        semantic = inspection["semantic_model"]
        self.assertFalse(any(
            item["kind"] == "constitutive" for item in semantic["entities"]
        ))
        self.assertIn("BSAM-E360", [item["code"] for item in inspection["diagnostics"]])

    def test_missing_direct_material_reference_is_reported(self) -> None:
        raw = constitutive_deck("1\n2 1 0\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.in"
            path.write_bytes(raw)
            inspection = SourceSet.read(path).inspection()

        missing = [
            item for item in inspection["semantic_model"]["references"]
            if item["kind"] == "uses-material"
        ]
        self.assertEqual("material:2", missing[0]["target_key"])
        self.assertEqual("unresolved", missing[0]["status"])
        self.assertIn("BSAM-E301", [item["code"] for item in inspection["diagnostics"]])


if __name__ == "__main__":
    unittest.main()
