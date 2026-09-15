"""Validation for model-independent chat evaluation fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .tool_contracts import TOOL_CONTRACTS, validate_arguments


def load_chat_cases(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "0.1.0":
        raise ValueError("unsupported chat-case schema")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("chat cases must be a non-empty array")
    identifiers: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "user", "expected"}:
            raise ValueError("chat case must contain only id, user, and expected")
        identifier = case["id"]
        if not isinstance(identifier, str) or identifier in identifiers:
            raise ValueError("chat case identifiers must be unique strings")
        identifiers.add(identifier)
        expected = case["expected"]
        if not isinstance(expected, dict):
            raise ValueError(f"case {identifier} expected result must be an object")
        allowed = {"tool", "arguments", "outcome", "error_code", "response_contains"}
        if set(expected) - allowed or not {"tool", "arguments", "outcome"} <= set(expected):
            raise ValueError(f"case {identifier} expected result fields are invalid")
        if expected["outcome"] not in {"dispatch", "refuse", "answer"}:
            raise ValueError(f"case {identifier} outcome is invalid")
        tool = expected["tool"]
        if tool is not None:
            if tool not in TOOL_CONTRACTS:
                raise ValueError(f"case {identifier} names an unknown tool")
            validate_arguments(tool, expected["arguments"])
        elif expected["arguments"] != {}:
            raise ValueError(f"case {identifier} without a tool must have empty arguments")
        if expected["outcome"] == "refuse" and "error_code" not in expected:
            raise ValueError(f"case {identifier} refusal requires an error code")
        if expected["outcome"] == "answer":
            phrases = expected.get("response_contains")
            if tool is not None or expected["arguments"] != {}:
                raise ValueError(f"case {identifier} final answer must not dispatch a tool")
            if not isinstance(phrases, list) or not phrases or any(
                not isinstance(item, str) or not item for item in phrases
            ):
                raise ValueError(f"case {identifier} final answer requires response_contains")
        elif "response_contains" in expected:
            raise ValueError(f"case {identifier} response_contains is only valid for final answers")
    return value


def load_trajectory_cases(path: Path) -> dict[str, Any]:
    """Validate deterministic multi-turn task-trajectory fixtures."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") not in {"0.1.0", "0.2.0"}:
        raise ValueError("unsupported trajectory-case schema")
    if set(value) != {"schema_version", "metrics", "cases"}:
        raise ValueError("trajectory fixture fields are invalid")
    metrics = value["metrics"]
    if not isinstance(metrics, list) or not metrics or any(
        not isinstance(item, str) or not item for item in metrics
    ):
        raise ValueError("trajectory metrics must be non-empty strings")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("trajectory cases must be a non-empty array")
    identifiers: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "user", "expected"}:
            raise ValueError("trajectory case fields are invalid")
        identifier = case["id"]
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("trajectory case identifiers must be unique strings")
        identifiers.add(identifier)
        if not isinstance(case["user"], str) or not case["user"]:
            raise ValueError(f"trajectory case {identifier} user text is invalid")
        expected = case["expected"]
        allowed = {
            "tool_sequence", "confirmation_boundaries", "terminal_status",
            "failure_category", "no_mutation", "arguments", "max_read_steps",
            "required_evidence_tools", "required_final_claim_kinds", "response_contains",
            "provider_parity",
        }
        if not isinstance(expected, dict) or set(expected) - allowed or not {
            "tool_sequence", "confirmation_boundaries", "terminal_status", "no_mutation",
        } <= set(expected):
            raise ValueError(f"trajectory case {identifier} expected fields are invalid")
        sequence = expected["tool_sequence"]
        if not isinstance(sequence, list) or any(tool not in TOOL_CONTRACTS for tool in sequence):
            raise ValueError(f"trajectory case {identifier} has an invalid tool sequence")
        boundaries = expected["confirmation_boundaries"]
        if not isinstance(boundaries, int) or isinstance(boundaries, bool) or boundaries < 0:
            raise ValueError(f"trajectory case {identifier} confirmation count is invalid")
        if expected["terminal_status"] not in {
            "complete", "clarification", "refused", "failed", "blocked",
        }:
            raise ValueError(f"trajectory case {identifier} terminal status is invalid")
        if not isinstance(expected["no_mutation"], bool):
            raise ValueError(f"trajectory case {identifier} no_mutation is invalid")
        if "failure_category" in expected and not isinstance(expected["failure_category"], str):
            raise ValueError(f"trajectory case {identifier} failure category is invalid")
        arguments = expected.get("arguments")
        if arguments is not None and (
            not isinstance(arguments, list)
            or len(arguments) != len(sequence)
            or any(not isinstance(item, dict) for item in arguments)
        ):
            raise ValueError(f"trajectory case {identifier} arguments are invalid")
        max_reads = expected.get("max_read_steps")
        if max_reads is not None and (
            not isinstance(max_reads, int) or isinstance(max_reads, bool) or max_reads < 0
        ):
            raise ValueError(f"trajectory case {identifier} read bound is invalid")
        evidence_tools = expected.get("required_evidence_tools", [])
        if not isinstance(evidence_tools, list) or any(
            tool not in TOOL_CONTRACTS for tool in evidence_tools
        ):
            raise ValueError(f"trajectory case {identifier} evidence tools are invalid")
        claim_kinds = expected.get("required_final_claim_kinds", [])
        if not isinstance(claim_kinds, list) or any(
            kind not in {"current_model", "documentation", "inference", "general"}
            for kind in claim_kinds
        ):
            raise ValueError(f"trajectory case {identifier} claim kinds are invalid")
        phrases = expected.get("response_contains", [])
        if not isinstance(phrases, list) or any(
            not isinstance(phrase, str) or not phrase for phrase in phrases
        ):
            raise ValueError(f"trajectory case {identifier} response phrases are invalid")
        if "provider_parity" in expected and not isinstance(expected["provider_parity"], bool):
            raise ValueError(f"trajectory case {identifier} provider parity is invalid")
    return value
