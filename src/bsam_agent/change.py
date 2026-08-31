"""Revision-bound minimal patches for existing BSAM key/value parameters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .document import SourceDocument, SourceLine
from .registry import load_registry


PLAN_SCHEMA_VERSION = "1.0.0"


class ChangeError(ValueError):
    """Raised when a requested change cannot be planned or safely applied."""


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _plan_digest(plan_without_digest: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(plan_without_digest)).hexdigest().upper()


def _construct_record(block_name: str, construct_name: str) -> dict[str, Any]:
    registry = load_registry()
    block_by_name = {item["canonical"].upper(): item["id"] for item in registry["top_level_blocks"]}
    block_id = block_by_name.get(block_name.upper())
    if block_id is None:
        raise ChangeError(f"unknown registered block: {block_name}")
    requested = construct_name.upper()
    if not requested.startswith("*"):
        requested = "*" + requested
    matches = [
        item for item in registry["nested_constructs"]
        if item["parent_block_id"] == block_id and item["canonical"].upper() == requested
    ]
    if not matches:
        raise ChangeError(f"unknown registered construct {construct_name} in {block_name}")
    return matches[0]


def _validate_replacement(construct: dict[str, Any], parameter: str, value: str) -> None:
    parameters = {item["name"].lower(): item for item in construct["parameters"]}
    definition = parameters.get(parameter.lower())
    if definition is None:
        raise ChangeError(
            f"parameter {parameter} is not registered for {construct['canonical']}; untyped edits are blocked"
        )
    value_type = definition["value_type"].lower()
    try:
        if "integer" in value_type:
            parsed: int | float = int(value)
        elif "real" in value_type:
            parsed = float(value)
        else:
            parsed = 0
    except ValueError as exc:
        raise ChangeError(f"value {value!r} is not a valid {definition['value_type']}") from exc
    if value_type.startswith("positive-") and parsed <= 0:
        raise ChangeError(f"value for {parameter} must be positive")
    allowed = definition.get("allowed_values")
    if allowed is not None and value.lower() not in {str(item).lower() for item in allowed}:
        raise ChangeError(f"value for {parameter} must be one of: {', '.join(map(str, allowed))}")


def _find_construct_lines(
    document: SourceDocument,
    block_name: str,
    construct: dict[str, Any],
    occurrence: int,
) -> tuple[int, int]:
    if occurrence < 1:
        raise ChangeError("occurrence must be at least 1")
    blocks = [item for item in document.blocks() if item["name"].upper() == block_name.upper()]
    if not blocks:
        raise ChangeError(f"block {block_name} was not found")
    prefix = construct["match_prefix"].lower()
    matches: list[tuple[int, int]] = []
    for block in blocks:
        final = block["end_line"] or len(document.lines)
        line_number = block["start_line"] + 1
        while line_number <= final:
            stripped = document.lines[line_number - 1].stripped
            if stripped.lower().startswith(prefix):
                end = line_number + 1
                while end <= final:
                    candidate = document.lines[end - 1].stripped
                    if candidate.startswith("*") and not candidate.startswith("**"):
                        break
                    if candidate.upper().startswith("END "):
                        break
                    end += 1
                matches.append((line_number, end - 1))
            line_number += 1
    if occurrence > len(matches):
        raise ChangeError(
            f"construct {construct['canonical']} occurrence {occurrence} was not found; found {len(matches)}"
        )
    return matches[occurrence - 1]


def _value_spans(line: SourceLine, parameter: str) -> list[tuple[int, int]]:
    text = line.text
    searchable = text.split("#", 1)[0]
    lower = searchable.lower()
    needle = parameter.lower()
    cursor = 0
    spans: list[tuple[int, int]] = []
    while True:
        found = lower.find(needle, cursor)
        if found < 0:
            return spans
        before_ok = found == 0 or not (lower[found - 1].isalnum() or lower[found - 1] == "_")
        after_name = found + len(needle)
        after_ok = after_name == len(lower) or not (lower[after_name].isalnum() or lower[after_name] == "_")
        equals = after_name
        while equals < len(searchable) and searchable[equals].isspace():
            equals += 1
        if before_ok and after_ok and equals < len(searchable) and searchable[equals] == "=":
            value_start = equals + 1
            while value_start < len(searchable) and searchable[value_start].isspace():
                value_start += 1
            value_end = value_start
            while value_end < len(searchable) and searchable[value_end] != ",":
                value_end += 1
            while value_end > value_start and searchable[value_end - 1].isspace():
                value_end -= 1
            if value_end == value_start:
                raise ChangeError(f"parameter {parameter} has an empty value on line {line.number}")
            spans.append((line.start + value_start, line.start + value_end))
            cursor = value_end
            continue
        cursor = found + 1


def plan_parameter_change(
    source: Path,
    block: str,
    construct_name: str,
    parameter: str,
    value: str,
    occurrence: int = 1,
) -> dict[str, Any]:
    if any(character in value for character in "\r\n\x00,"):
        raise ChangeError("replacement value must be a single non-comma record value")
    if not value.strip():
        raise ChangeError("replacement value must not be empty")
    document = SourceDocument.read(source)
    construct = _construct_record(block, construct_name)
    _validate_replacement(construct, parameter, value)
    start_line, end_line = _find_construct_lines(document, block, construct, occurrence)
    candidates: list[tuple[SourceLine, int, int]] = []
    for line in document.lines[start_line:end_line]:
        candidates.extend((line, *span) for span in _value_spans(line, parameter))
    if not candidates:
        raise ChangeError(
            f"parameter {parameter} was not found in {construct['canonical']} occurrence {occurrence}"
        )
    if len(candidates) > 1:
        lines = ", ".join(str(item[0].number) for item in candidates)
        raise ChangeError(f"parameter {parameter} is ambiguous in the selected construct (lines {lines})")
    line, start, end = candidates[0]
    old_bytes = document.raw[start:end]
    new_bytes = value.encode("latin-1")
    if old_bytes == new_bytes:
        raise ChangeError("requested value is identical to the existing value")
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source.resolve()),
        "base_sha256": document.sha256,
        "operation": "set-existing-parameter",
        "selector": {
            "block": block.upper(),
            "construct": construct["canonical"],
            "construct_occurrence": occurrence,
            "parameter": parameter,
        },
        "patch": {
            "start": start,
            "end": end,
            "line": line.number,
            "old": old_bytes.decode("latin-1"),
            "new": value,
        },
        "preview": f"line {line.number}: {parameter} = {old_bytes.decode('latin-1')} -> {value}",
    }
    digest = _plan_digest(plan)
    plan["plan_digest"] = digest
    plan["plan_id"] = digest[:16]
    return plan


def write_plan(plan: dict[str, Any], destination: Path) -> None:
    if destination.exists():
        raise ChangeError(f"plan destination already exists: {destination}")
    destination.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_plan(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        plan = json.load(stream)
    if not isinstance(plan, dict):
        raise ChangeError("change plan must be a JSON object")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ChangeError("unsupported change-plan schema version")
    digest = plan.get("plan_digest")
    content = {key: value for key, value in plan.items() if key not in {"plan_digest", "plan_id"}}
    expected = _plan_digest(content)
    if digest != expected or plan.get("plan_id") != expected[:16]:
        raise ChangeError("change-plan digest is invalid")
    return plan


def apply_plan(plan_path: Path, destination: Path) -> dict[str, Any]:
    plan = load_plan(plan_path)
    source = Path(plan["source"])
    if source.resolve() == destination.resolve():
        raise ChangeError("in-place replacement is not allowed; choose a separate destination")
    if destination.exists():
        raise ChangeError(f"destination already exists: {destination}")
    document = SourceDocument.read(source)
    if document.sha256 != plan["base_sha256"]:
        raise ChangeError("source changed after planning; create a new change plan")
    patch = plan["patch"]
    start, end = int(patch["start"]), int(patch["end"])
    expected = patch["old"].encode("latin-1")
    if document.raw[start:end] != expected:
        raise ChangeError("planned source span no longer contains the expected value")
    updated = document.raw[:start] + patch["new"].encode("latin-1") + document.raw[end:]
    updated_document = SourceDocument.from_bytes(updated, str(destination.resolve()))
    errors = [item for item in updated_document.diagnostics() if item.severity == "error"]
    if errors:
        raise ChangeError("updated deck failed structural validation: " + "; ".join(item.message for item in errors))
    destination.write_bytes(updated)
    return {
        "plan_id": plan["plan_id"],
        "source": str(source.resolve()),
        "destination": str(destination.resolve()),
        "base_sha256": document.sha256,
        "output_sha256": updated_document.sha256,
        "changed_line": patch["line"],
        "preview": plan["preview"],
    }
