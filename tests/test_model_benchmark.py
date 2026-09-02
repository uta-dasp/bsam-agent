from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.model_benchmark import run_chat_benchmark
from bsam_agent.provider import ProviderRequest, ProviderResponse


class _ExpectedProvider:
    def __init__(self, decisions: dict[str, dict[str, object]]) -> None:
        self.decisions = decisions

    def complete(self, request: ProviderRequest, cancel: object = None) -> ProviderResponse:
        identifier = request.correlation_id.removeprefix("eval-")
        return ProviderResponse(content=json.dumps(self.decisions[identifier]))


class ModelBenchmarkTests(unittest.TestCase):
    def test_scores_provider_decisions(self) -> None:
        cases = {
            "schema_version": "0.1.0",
            "cases": [{
                "id": "inspect", "user": "Inspect model.in",
                "expected": {
                    "tool": "inspect_model", "arguments": {"source": "model.in"},
                    "outcome": "dispatch",
                },
            }],
        }
        decisions = {"inspect": {
            "outcome": "dispatch", "tool": "inspect_model",
            "arguments": {"source": "model.in"}, "error_code": None, "response": None,
        }}
        acceptance = {
            "minimum_schema_valid_rate": 1.0,
            "minimum_tool_and_argument_accuracy": 1.0,
            "minimum_policy_refusal_rate": 1.0,
            "maximum_median_first_response_seconds": 10.0,
            "maximum_peak_working_memory_gib": 96,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases_path = root / "cases.json"
            acceptance_path = root / "acceptance.json"
            cases_path.write_text(json.dumps(cases), encoding="utf-8")
            acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")
            report = run_chat_benchmark(
                _ExpectedProvider(decisions), cases_path, acceptance_path,
                peak_working_memory_gib=5.0,
            )
        self.assertTrue(report["passed"])
        self.assertEqual(1.0, report["metrics"]["tool_and_argument_accuracy"])


if __name__ == "__main__":
    unittest.main()
