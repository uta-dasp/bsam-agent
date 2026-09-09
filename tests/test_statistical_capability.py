from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import LocalAgentApi
from bsam_agent.capabilities import capability_manifest
from bsam_agent.orchestrator import ChatOrchestrator
from bsam_agent.provider import ProviderConfig
from bsam_agent.source_set import SourceSet


def statistical_deck(reference: str = "stat_strength_1.0") -> bytes:
    return (
        "INPUT\n3\nEND INPUT\n"
        "STATISTICAL\n"
        "stat-strength\n"
        "type=3\n"
        "approx=1\n"
        "seeding=coordinates\n"
        "coordinates=1,2,3\n"
        "alpha=13\n"
        "v0=6250\n"
        "generation=7\n"
        "*end\n"
        "END STATISTICAL DISTRIBUTIONS\n"
        "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        "MATERIALS\n999\n"
        f"E11={reference}\n"
        "*end\nEND MATERIALS\n"
        "CLUSTERS\n*type\nsolid\n*NAME\nply1\n*STOP\nEND CLUSTERS\n"
    ).encode("latin-1")


class StatisticalCapabilityTests(unittest.TestCase):
    def test_distribution_cluster_and_material_references_resolve(self) -> None:
        raw = statistical_deck()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            source_set = SourceSet.read(path)
            inspection = source_set.inspection()
            rendered = source_set.render_files()[path.resolve()]

        semantic = inspection["semantic_model"]
        distribution = next(
            item for item in semantic["entities"]
            if item["kind"] == "statistical-distribution"
        )
        references = [
            item for item in semantic["references"]
            if item["kind"] in {"uses-seed-cluster", "uses-statistical-distribution"}
        ]
        self.assertEqual("strength", distribution["name"])
        self.assertEqual([1.0, 2.0, 3.0], distribution["attributes"]["seed_dimensions"])
        self.assertEqual(2, len(references))
        self.assertTrue(all(item["status"] == "resolved" for item in references))
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(raw, rendered)

    def test_distribution_is_queryable_with_source_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(statistical_deck())
            result = LocalAgentApi(root).dispatch("query_model", {
                "source": "model.in", "query": "inspect-capability",
                "capability": "block.statistical-distributions",
            })

        self.assertEqual(1, result["summary"]["matches"])
        record = result["matches"][0]
        self.assertEqual("strength", record["parameters"]["name"][0]["value"])
        self.assertEqual("1,2,3", record["parameters"]["seed_dimensions"][0]["value"])
        self.assertEqual("verified", record["operations"]["static_validation"])

    def test_missing_duplicate_and_unresolved_distributions_are_diagnostics(self) -> None:
        missing = statistical_deck("stat_missing_1.0")
        duplicate = statistical_deck().replace(
            b"END STATISTICAL DISTRIBUTIONS",
            b"stat-strength\ntype=3\napprox=1\nseeding=coordinates\n"
            b"coordinates=1,2,3\nalpha=1\nv0=1\ngeneration=1\n*end\n"
            b"END STATISTICAL DISTRIBUTIONS",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing_path = root / "missing.in"
            duplicate_path = root / "duplicate.in"
            missing_path.write_bytes(missing)
            duplicate_path.write_bytes(duplicate)
            missing_codes = [
                item["code"] for item in SourceSet.read(missing_path).inspection()["diagnostics"]
            ]
            duplicate_codes = [
                item["code"] for item in SourceSet.read(duplicate_path).inspection()["diagnostics"]
            ]

        self.assertIn("BSAM-E301", missing_codes)
        self.assertIn("BSAM-E300", duplicate_codes)
        self.assertIn("BSAM-E303", duplicate_codes)

    def test_dynamic_key_order_and_generation_constraints_are_rejected(self) -> None:
        invalid = statistical_deck().replace(
            b"type=3\napprox=1\nseeding=coordinates\ncoordinates=1,2,3\n"
            b"alpha=13\nv0=6250\ngeneration=7",
            b"type=4\napprox=0\ncoordinates=1,-2,3\nseeding=coordinates\n"
            b"alpha=0\nv0=nan\ngeneration=0",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.in"
            path.write_bytes(invalid)
            inspection = SourceSet.read(path).inspection()
        errors = [item for item in inspection["diagnostics"] if item["code"] == "BSAM-E340"]
        self.assertGreaterEqual(len(errors), 6)
        self.assertTrue(any("must follow seeding" in item["message"] for item in errors))

    def test_operational_support_is_explicit(self) -> None:
        distribution = next(
            item for item in capability_manifest()
            if item["id"] == "block.statistical-distributions"
        )
        self.assertEqual("verified", distribution["operations"]["semantic"])
        self.assertEqual("verified", distribution["operations"]["static_validation"])
        self.assertEqual("unsupported", distribution["operations"]["modify"])

    def test_natural_distribution_listing_is_deterministic(self) -> None:
        class NoCallProvider:
            def complete(self, _request):  # pragma: no cover - a call fails the test
                raise AssertionError("distribution listing should not call the provider")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(statistical_deck())
            agent = ChatOrchestrator(
                NoCallProvider(),
                ProviderConfig(
                    "fake", "fake", "http://127.0.0.1", None, 1, 10000, 128, "local-only",
                ),
                LocalAgentApi(root),
            )
            result = agent.turn("List the statistical distributions in model.in.")

        self.assertEqual("query_model", result.tool)
        self.assertEqual(1, result.tool_result["summary"]["matches"])
        self.assertEqual("statistical-distribution", result.tool_result["matches"][0]["kind"])


if __name__ == "__main__":
    unittest.main()
