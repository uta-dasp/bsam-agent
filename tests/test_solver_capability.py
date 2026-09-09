from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import ApiError, LocalAgentApi
from bsam_agent.orchestrator import ChatOrchestrator
from bsam_agent.provider import ProviderConfig
from bsam_agent.source_set import SourceSet


CURRENT_SOLVERS = (
    b"SOLVER\n"
    b"*type=pardiso\nn_threads=2\nmatrix_type=indefinite\nend solver\n"
    b"*type=sheff\nbackend=mkl\nsolver=cg\nmaximum_iterations=500\nend solver\n"
    b"END SOLVER\n"
)


def deck(solver: bytes = CURRENT_SOLVERS, schedule: bytes = b"2") -> bytes:
    return (
        b"INPUT\n3\nEND INPUT\n" + solver +
        b"BOUNDARY\n*type\nmechanical\n*solver\n" + schedule + b"\nEND BOUNDARY\n"
        b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
        b"MATERIALS\n0\nEND MATERIALS\n"
        b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
    )


class NoCallProvider:
    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):  # pragma: no cover
        self.requests.append(request)
        raise AssertionError("deterministic solver request should not call the provider")


def config() -> ProviderConfig:
    return ProviderConfig(
        "cpu-local", "test", "http://127.0.0.1:1", None,
        1.0, 24000, 512, "local-private",
    )


class SolverCapabilityTests(unittest.TestCase):
    def test_current_solvers_and_boundary_schedule_are_semantic_and_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(deck())
            inspection = SourceSet.read(path).inspection()
        semantic = inspection["semantic_model"]
        solvers = [item for item in semantic["entities"] if item["kind"] == "solver"]
        schedules = [item for item in semantic["entities"] if item["kind"] == "solver-schedule"]
        records = [
            item for item in semantic["capability_records"]
            if item["capability_id"] == "block.solver"
        ]
        references = [item for item in semantic["references"] if item["kind"] == "uses-solver"]
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(["pardiso", "sheff"], [item["attributes"]["type"] for item in solvers])
        self.assertEqual(2, len(records))
        self.assertEqual("current", records[0]["attributes"]["syntax"])
        self.assertEqual("2", records[0]["parameters"]["n_threads"][0]["value"])
        self.assertEqual(2, schedules[0]["attributes"]["schedule"])
        self.assertEqual(2, len(references))
        self.assertTrue(all(item["status"] == "resolved" for item in references))

    def test_schedule_two_requires_two_solver_definitions(self) -> None:
        one = (
            b"SOLVER\n*type=pardiso\nn_threads=1\nmatrix_type=definite\n"
            b"end solver\nEND SOLVER\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(deck(one))
            inspection = SourceSet.read(path).inspection()
        unresolved = [
            item for item in inspection["semantic_model"]["references"]
            if item["kind"] == "uses-solver" and item["status"] == "unresolved"
        ]
        self.assertEqual(1, len(unresolved))
        self.assertEqual("solver:2", unresolved[0]["target_key"])
        self.assertIn("BSAM-E301", {item["code"] for item in inspection["diagnostics"]})

    def test_current_pardiso_requires_explicit_safe_options(self) -> None:
        incomplete = b"SOLVER\n*type=pardiso\nend solver\nEND SOLVER\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.in"
            path.write_bytes(deck(incomplete, b"1"))
            inspection = SourceSet.read(path).inspection()
        errors = [item for item in inspection["diagnostics"] if item["code"] == "BSAM-E311"]
        self.assertEqual(2, len(errors))
        self.assertIn("n_threads", errors[0]["message"] + errors[1]["message"])
        self.assertIn("matrix_type", errors[0]["message"] + errors[1]["message"])

    def test_legacy_solver_is_inspectable_but_generic_edit_is_blocked(self) -> None:
        legacy = b"SOLVER\n9\n14\n*indefinite\nEND SOLVER\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck(legacy, b"1"))
            api = LocalAgentApi(root)
            query = api.dispatch("query_model", {
                "source": "model.in", "query": "get-parameter",
                "capability": "block.solver", "parameter": "n_threads",
            })
            inspection = api.dispatch("query_model", {
                "source": "model.in", "query": "inspect-capability",
                "capability": "block.solver",
            })
            with self.assertRaisesRegex(ApiError, "occurrence 1 was not found"):
                api.dispatch("preview_parameter_change", {
                    "source": "model.in", "block": "SOLVER", "construct": "block.solver",
                    "parameter": "n_threads", "value": "2", "plan_path": "change.json",
                })
        self.assertEqual("legacy", inspection["matches"][0]["attributes"]["syntax"])
        self.assertEqual("unsupported", query["matches"][0]["operations"]["modify"])
        self.assertEqual("14", query["matches"][0]["values"][0]["value"])

    def test_capability_id_edit_and_natural_language_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck())
            api = LocalAgentApi(root)
            plan = api.dispatch("preview_parameter_change", {
                "source": "model.in", "block": "SOLVER", "construct": "block.solver",
                "parameter": "n_threads", "value": "3", "plan_path": "manual.json",
            })
            self.assertEqual("3", plan["patch"]["new"])
            provider = NoCallProvider()
            agent = ChatOrchestrator(provider, config(), api)
            preview = agent.turn("Change n_threads in model.in to 4 and validate the result.")
            applied = agent.turn("/confirm")
            output = (root / "model.changed.in").read_text(encoding="latin-1")
        self.assertTrue(preview.requires_confirmation)
        self.assertIn("n_threads=4", output)
        self.assertEqual("complete", agent.state.task.status)
        self.assertEqual(0, applied.tool_result["post_apply_validation"]["summary"]["errors"])
        self.assertEqual([], provider.requests)

    def test_optional_sheff_record_insertion_and_removal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck())
            api = LocalAgentApi(root)
            inserted = api.dispatch("preview_parameter_change", {
                "source": "model.in", "block": "SOLVER", "construct": "block.solver",
                "parameter": "relative_tolerance", "value": "1e-6", "occurrence": 2,
                "plan_path": "insert.json",
            })
            self.assertEqual("insert-optional-parameter", inserted["operation"])
            api.dispatch("apply_change", {
                "plan_path": "insert.json", "destination": "inserted.in", "confirm": True,
            })
            inserted_text = (root / "inserted.in").read_text(encoding="latin-1")
            self.assertIn("relative_tolerance=1e-6\nend solver", inserted_text)

            removed = api.dispatch("preview_parameter_removal", {
                "source": "inserted.in", "block": "SOLVER", "construct": "block.solver",
                "parameter": "relative_tolerance", "occurrence": 2,
                "plan_path": "remove.json",
            })
            self.assertEqual("remove-optional-parameter", removed["operation"])
            result = api.dispatch("apply_change", {
                "plan_path": "remove.json", "destination": "removed.in", "confirm": True,
            })
            self.assertNotIn(
                "relative_tolerance", (root / "removed.in").read_text(encoding="latin-1")
            )
            self.assertEqual(0, result["validation"]["summary"]["errors"])


if __name__ == "__main__":
    unittest.main()
