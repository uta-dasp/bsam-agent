from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.evals import load_chat_cases, load_trajectory_cases


ROOT = Path(__file__).resolve().parents[1]


class ChatEvaluationTests(unittest.TestCase):
    def test_chat_cases_are_strict_and_tool_contract_valid(self) -> None:
        value = load_chat_cases(ROOT / "evals" / "chat_cases.json")
        self.assertGreaterEqual(len(value["cases"]), 8)
        outcomes = {item["expected"]["outcome"] for item in value["cases"]}
        self.assertEqual({"answer", "dispatch", "refuse"}, outcomes)
        identifiers = {item["id"] for item in value["cases"]}
        self.assertTrue({
            "prompt-injection-in-deck", "stale-plan-review", "render-needs-reviewed-plan",
            "run-status", "stop-needs-confirmation", "validation-final-answer",
        } <= identifiers)

    def test_acceptance_thresholds_are_bounded(self) -> None:
        value = json.loads((ROOT / "evals" / "acceptance.json").read_text(encoding="utf-8"))
        for key in (
            "minimum_schema_valid_rate", "minimum_tool_and_argument_accuracy",
            "minimum_policy_refusal_rate",
        ):
            self.assertGreaterEqual(value[key], 0)
            self.assertLessEqual(value[key], 1)

    def test_trajectory_cases_cover_bounded_workflow_failures(self) -> None:
        value = load_trajectory_cases(ROOT / "evals" / "trajectory_cases.json")
        self.assertEqual(19, len(value["cases"]))
        identifiers = {item["id"] for item in value["cases"]}
        self.assertEqual({
            "inspect-modify-validate", "ambiguous-parameter", "dependent-boundary-rename",
            "unsupported-create", "stale-revision", "failed-execution",
            "solver-control-change", "generic-node-create", "stale-plan-refresh",
            "composite-reviewed-plan",
            "table-reference-inspection",
            "user-function-reference-inspection",
            "statistical-reference-inspection",
            "structured-material-reference-attribution",
            "optional-parameter-removal",
            "autonomous-boundary-investigation",
            "compare-original-with-last-output",
            "diagnose-last-failed-run",
            "syntax-only-repair-unavailable",
        }, identifiers)
        self.assertIn("repeated_action_loops", value["metrics"])
        self.assertIn("guarded_action_compliance", value["metrics"])
        self.assertIn("unnecessary_reads", value["metrics"])
        self.assertIn("evidence_sufficiency", value["metrics"])
        self.assertIn("policy_behavior", value["metrics"])
        self.assertIn("provider_parity", value["metrics"])
        autonomous = next(
            item for item in value["cases"]
            if item["id"] == "autonomous-boundary-investigation"
        )
        self.assertEqual(4, autonomous["expected"]["max_read_steps"])
        self.assertIn("inference", autonomous["expected"]["required_final_claim_kinds"])


if __name__ == "__main__":
    unittest.main()
