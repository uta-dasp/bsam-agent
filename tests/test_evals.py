from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.evals import load_chat_cases


ROOT = Path(__file__).resolve().parents[1]


class ChatEvaluationTests(unittest.TestCase):
    def test_chat_cases_are_strict_and_tool_contract_valid(self) -> None:
        value = load_chat_cases(ROOT / "evals" / "chat_cases.json")
        self.assertGreaterEqual(len(value["cases"]), 8)
        outcomes = {item["expected"]["outcome"] for item in value["cases"]}
        self.assertEqual({"dispatch", "refuse"}, outcomes)

    def test_acceptance_thresholds_are_bounded(self) -> None:
        value = json.loads((ROOT / "evals" / "acceptance.json").read_text(encoding="utf-8"))
        for key in (
            "minimum_schema_valid_rate", "minimum_tool_and_argument_accuracy",
            "minimum_policy_refusal_rate",
        ):
            self.assertGreaterEqual(value[key], 0)
            self.assertLessEqual(value[key], 1)


if __name__ == "__main__":
    unittest.main()
