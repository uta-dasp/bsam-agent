from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import LocalAgentApi
from bsam_agent.agent_benchmark import evaluate_trajectory
from bsam_agent.local_provider import LlamaCppProvider
from bsam_agent.openai_provider import OpenAIResponsesProvider
from bsam_agent.orchestrator import ChatOrchestrator
from bsam_agent.provider import ProviderConfig


DECK = (
    b"INPUT\n3\nEND INPUT\n"
    b"BOUNDARY\n*type\nmechanical\n*boundary condition\n"
    b"type=disp, comp=x, name=bc1, value=0, nset=ply.edge\nEND BOUNDARY\n"
    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
    b"CLUSTERS\n*type\nsolid\n*NAME\nply\n*NODE\n1,0,0,0\n"
    b"*NSET,NSET=edge\n1\n*STOP\nEND CLUSTERS\n"
)


class _Response:
    def __init__(self, value: dict[str, object]) -> None:
        self._raw = json.dumps(value).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


def _decision() -> dict[str, object]:
    return {
        "outcome": "dispatch", "tool": "query_model",
        "arguments": {"source": "model.in", "query": "list_boundary_conditions"},
        "error_code": None, "response": None,
    }


def _synthesis() -> dict[str, object]:
    return {"claims": [{
        "kind": "current_model",
        "text": "The inspected model contains one boundary condition.",
        "evidence_ids": ["obs-001", "obs-002"],
    }]}


class ProviderTrajectoryParityTests(unittest.TestCase):
    def test_same_synthetic_investigation_has_local_and_openai_parity(self) -> None:
        local_responses = [
            _Response({"choices": [{
                "message": {"content": json.dumps(_decision())}, "finish_reason": "stop",
            }]}),
            _Response({"choices": [{
                "message": {"content": json.dumps(_synthesis())}, "finish_reason": "stop",
            }]}),
        ]
        openai_responses = [
            _Response({"status": "completed", "output": [{
                "type": "function_call", "call_id": "call-1", "name": "query_model",
                "arguments": json.dumps(_decision()["arguments"]),
            }]}),
            _Response({"status": "completed", "output": [{
                "type": "message", "content": [{
                    "type": "output_text", "text": json.dumps(_synthesis()),
                }],
            }]}),
        ]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            local_config = ProviderConfig(
                "cpu-local", "test-local", "http://127.0.0.1:18080", None,
                2.0, 24_000, 512, "synthetic-only",
            )
            hosted_config = ProviderConfig(
                "openai", "test-openai", "https://api.openai.com",
                "env:OPENAI_API_KEY", 2.0, 24_000, 512, "sanitized",
            )
            with patch("bsam_agent.local_provider.urlopen", side_effect=local_responses):
                local = ChatOrchestrator(
                    LlamaCppProvider(local_config), local_config, LocalAgentApi(root),
                )
                local_turn = local.turn(
                    "Inspect model.in and tell me whether anything looks wrong."
                )
            with patch("bsam_agent.openai_provider.urlopen", side_effect=openai_responses):
                hosted = ChatOrchestrator(
                    OpenAIResponsesProvider(
                        hosted_config, credential_resolver=lambda _reference: "test-secret",
                    ),
                    hosted_config,
                    LocalAgentApi(root),
                )
                hosted_turn = hosted.turn(
                    "Inspect model.in and tell me whether anything looks wrong."
                )

        local_summary = (
            local.state.task.status, local.state.task.completed_steps,
            local.state.task.remaining_criteria, local_turn.tool,
        )
        hosted_summary = (
            hosted.state.task.status, hosted.state.task.completed_steps,
            hosted.state.task.remaining_criteria, hosted_turn.tool,
        )
        self.assertEqual(local_summary, hosted_summary)
        self.assertEqual("complete", local_summary[0])
        self.assertEqual(
            ["inspect_model", "query_model"], local.state.task.completed_steps,
        )
        self.assertIn("Finding:", local_turn.message)
        self.assertIn("[obs-001, obs-002]", local_turn.message)
        self.assertIn("Finding:", hosted_turn.message)
        self.assertIn("[obs-001, obs-002]", hosted_turn.message)

        expected = {
            "tool_sequence": ["inspect_model", "query_model"],
            "arguments": [
                {"source": "model.in"},
                {"source": "model.in", "query": "list_boundary_conditions"},
            ],
            "confirmation_boundaries": 0,
            "terminal_status": "complete",
            "no_mutation": True,
            "max_read_steps": 2,
            "required_evidence_tools": ["inspect_model", "query_model"],
            "required_final_claim_kinds": ["current_model"],
            "response_contains": ["Finding:", "obs-001"],
            "provider_parity": True,
        }
        report = evaluate_trajectory(
            local.state.task, [local_turn], expected,
            provider_peer=(hosted.state.task, [hosted_turn]),
        )
        self.assertTrue(report["passed"], report)
        self.assertTrue(all(report["metrics"].values()))

        missing_peer = evaluate_trajectory(local.state.task, [local_turn], expected)
        self.assertFalse(missing_peer["metrics"]["provider_parity"])

        wrong_arguments = evaluate_trajectory(
            local.state.task, [local_turn], {
                **expected,
                "arguments": [{"source": "other.in"}, expected["arguments"][1]],
            },
        )
        self.assertFalse(wrong_arguments["metrics"]["argument_accuracy"])
        excess_reads = evaluate_trajectory(
            local.state.task, [local_turn], {**expected, "max_read_steps": 1},
        )
        self.assertFalse(excess_reads["metrics"]["unnecessary_reads"])
        missing_evidence = evaluate_trajectory(
            local.state.task, [local_turn], {
                **expected, "required_evidence_tools": ["search_workspace"],
            },
        )
        self.assertFalse(missing_evidence["metrics"]["evidence_sufficiency"])
        wrong_policy = evaluate_trajectory(
            local.state.task, [local_turn], {
                **expected, "failure_category": "unsupported_capability",
            },
        )
        self.assertFalse(wrong_policy["metrics"]["policy_behavior"])
        unhelpful = evaluate_trajectory(
            local.state.task, [local_turn], {
                **expected, "response_contains": ["not present"],
            },
        )
        self.assertFalse(unhelpful["metrics"]["final_answer_usefulness"])
        mismatched_peer = deepcopy(hosted.state.task)
        mismatched_peer.status = "blocked"
        parity = evaluate_trajectory(
            local.state.task, [local_turn], expected,
            provider_peer=(mismatched_peer, [hosted_turn]),
        )
        self.assertFalse(parity["metrics"]["provider_parity"])


if __name__ == "__main__":
    unittest.main()
