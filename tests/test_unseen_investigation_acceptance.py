from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.agent_benchmark import evaluate_trajectory
from bsam_agent.api import LocalAgentApi
from bsam_agent.orchestrator import ChatOrchestrator
from bsam_agent.provider import ProviderConfig, ProviderResponse


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "tests/fixtures/autonomous_named_data.in"
EVIDENCE = ROOT / "evals" / "results" / "unseen_named_data_investigation_2026-09-14.json"


def _config() -> ProviderConfig:
    return ProviderConfig(
        "cpu-local", "synthetic-acceptance", "http://127.0.0.1:1", None,
        1.0, 24_000, 512, "synthetic-only",
    )


def _decision(tool: str, arguments: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(content=json.dumps({
        "outcome": "dispatch", "tool": tool, "arguments": arguments,
        "error_code": None, "response": None,
    }))


class _UnseenInvestigationProvider:
    """Select steps from observations; it has no access to deterministic execution."""

    def __init__(self) -> None:
        self.requests = []

    def complete(self, request, cancel=None):
        self.requests.append(request)
        context = request.messages[-1].content
        if "Completed task evidence:" in context:
            return ProviderResponse(content=json.dumps({"claims": [
                {
                    "kind": "current_model",
                    "text": "All three outbound named-data references resolve.",
                    "evidence_ids": ["obs-003"],
                },
                {
                    "kind": "inference",
                    "text": "No unresolved structured-material dependency is present in the inspected model.",
                    "evidence_ids": ["obs-001", "obs-002", "obs-003"],
                },
            ]}))
        if '"tool":"query_model"' not in context:
            return _decision("query_model", {
                "source": SOURCE, "query": "list_entities",
                "entity_kind": "structured-material",
            })
        return _decision("find_references", {
            "source": SOURCE, "direction": "outbound",
            "entity_kind": "structured-material", "entity_name": "type-999-line-36",
        })


class UnseenInvestigationAcceptanceTests(unittest.TestCase):
    def test_model_composes_unseen_named_data_dependency_investigation(self) -> None:
        provider = _UnseenInvestigationProvider()
        agent = ChatOrchestrator(provider, _config(), LocalAgentApi(ROOT))
        result = agent.turn(
            f"Investigate {SOURCE}. Something may be wrong with the dependencies of its "
            "structured material; trace every outbound reference and explain whether each resolves."
        )

        expected = {
            "tool_sequence": ["query_model", "inspect_model", "find_references"],
            "arguments": [
                {"source": SOURCE, "query": "list_entities", "entity_kind": "structured-material"},
                {"source": SOURCE},
                {
                    "source": SOURCE, "direction": "outbound",
                    "entity_kind": "structured-material", "entity_name": "type-999-line-36",
                },
            ],
            "confirmation_boundaries": 0,
            "terminal_status": "complete",
            "no_mutation": True,
            "max_read_steps": 3,
            "required_evidence_tools": ["inspect_model", "query_model", "find_references"],
            "required_final_claim_kinds": ["current_model", "inference"],
            "response_contains": ["Finding:", "Inference:", "obs-003"],
        }
        report = evaluate_trajectory(agent.state.task, [result], expected)

        self.assertTrue(report["passed"], report)
        self.assertEqual(2, len(provider.requests))
        self.assertEqual(1, agent.state.task.model_step_count)
        self.assertIn("Task context", provider.requests[0].messages[-1].content)
        self.assertIn(
            "find_references",
            provider.requests[0].response_schema["properties"]["tool"]["enum"],
        )
        self.assertEqual("find_references", result.tool)
        self.assertEqual(3, result.tool_result["summary"]["matches"])
        self.assertFalse(result.tool_result["summary"]["ambiguous"])
        self.assertEqual(
            {"uses-table", "uses-user-function", "uses-statistical-distribution"},
            {item["kind"] for item in result.tool_result["matches"]},
        )
        self.assertTrue(all(
            item["status"] == "resolved" for item in result.tool_result["matches"]
        ))
        retained = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual("synthetic-only", retained["data_classification"])
        self.assertEqual(agent.state.task.completed_steps, retained["trajectory"]["tool_sequence"])
        self.assertEqual(
            agent.state.task.active_source_digest, retained["fixture"]["source_set_sha256"],
        )
        self.assertTrue(retained["evaluation"]["model_composed"])
        self.assertFalse(retained["evaluation"]["request_specific_workflow_added"])


if __name__ == "__main__":
    unittest.main()
