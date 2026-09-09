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


def function_deck(reference: str = "ufunc_curve") -> bytes:
    return (
        "INPUT\n3\nEND INPUT\n"
        "UFUNCTIONS\n"
        "user-function-curve\n"
        "0 0\n1 2\n2 3\n"
        "*end\n"
        "descending\n"
        "2 4\n1 1\n0 0\n"
        "*end\n"
        "END UFUNCTIONS\n"
        "BOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
        "CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        "MATERIALS\n998\n"
        f"K={reference}\n"
        "*end\nEND MATERIALS\n"
        "CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
    ).encode("latin-1")


class UserFunctionCapabilityTests(unittest.TestCase):
    def test_named_functions_and_material_references_resolve(self) -> None:
        raw = function_deck()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(raw)
            source_set = SourceSet.read(path)
            inspection = source_set.inspection()
            rendered = source_set.render_files()[path.resolve()]

        semantic = inspection["semantic_model"]
        functions = [
            item for item in semantic["entities"] if item["kind"] == "user-function"
        ]
        references = [
            item for item in semantic["references"]
            if item["kind"] == "uses-user-function"
        ]
        curve = next(item for item in functions if item["name"] == "curve")
        self.assertEqual(3, curve["attributes"]["point_count"])
        self.assertEqual([[0.0, 0.0], [1.0, 2.0], [2.0, 3.0]], curve["attributes"]["points"])
        self.assertEqual(2, len(functions))
        self.assertEqual("resolved", references[0]["status"])
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(raw, rendered)

    def test_function_records_are_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(function_deck())
            result = LocalAgentApi(root).dispatch("query_model", {
                "source": "model.in", "query": "inspect-capability",
                "capability": "block.ufunctions",
            })

        self.assertEqual(2, result["summary"]["matches"])
        self.assertEqual("curve", result["matches"][0]["parameters"]["name"][0]["value"])
        self.assertEqual(3, result["matches"][0]["attributes"]["point_count"])

    def test_missing_and_duplicate_function_targets_are_diagnostics(self) -> None:
        missing = function_deck("ufunc_missing")
        duplicate = function_deck().replace(
            b"END UFUNCTIONS",
            b"curve\n0 0\n1 1\n*end\nEND UFUNCTIONS",
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

    def test_invalid_width_count_and_monotonicity_are_rejected(self) -> None:
        invalid = function_deck().replace(
            b"0 0\n1 2\n2 3", b"0 0\n1 2 3\n0 4",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.in"
            path.write_bytes(invalid)
            inspection = SourceSet.read(path).inspection()
        codes = [item["code"] for item in inspection["diagnostics"]]
        self.assertIn("BSAM-E330", codes)
        self.assertIn("BSAM-E331", codes)

    def test_operational_support_is_explicit(self) -> None:
        function = next(
            item for item in capability_manifest() if item["id"] == "block.ufunctions"
        )
        self.assertEqual("verified", function["operations"]["parse"])
        self.assertEqual("verified", function["operations"]["static_validation"])
        self.assertEqual("unsupported", function["operations"]["create"])

    def test_natural_function_listing_is_deterministic(self) -> None:
        class NoCallProvider:
            def complete(self, _request):  # pragma: no cover - a call fails the test
                raise AssertionError("function listing should not call the provider")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(function_deck())
            agent = ChatOrchestrator(
                NoCallProvider(),
                ProviderConfig(
                    "fake", "fake", "http://127.0.0.1", None, 1, 10000, 128, "local-only",
                ),
                LocalAgentApi(root),
            )
            result = agent.turn("List the user functions in model.in.")

        self.assertEqual("query_model", result.tool)
        self.assertEqual(2, result.tool_result["summary"]["matches"])
        self.assertTrue(all(
            item["kind"] == "user-function" for item in result.tool_result["matches"]
        ))


if __name__ == "__main__":
    unittest.main()
