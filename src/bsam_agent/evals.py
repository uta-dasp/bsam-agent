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
