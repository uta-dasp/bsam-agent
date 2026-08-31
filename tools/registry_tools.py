"""Validate the BSAM capability registry and generate its Markdown reference.

This tool intentionally uses only the Python standard library. It never reads or
copies BSAM source; evidence locators in the curated registry are metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "specs" / "bsam-2.4" / "capabilities.json"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "bsam" / "reference" / "BSAM_2_4_INPUT_API.md"
VALID_COVERAGE = {
    "identified",
    "partially-documented",
    "documented",
    "runtime-verified",
}


class RegistryError(ValueError):
    """Raised when curated registry invariants are violated."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_registry(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream, object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(data, dict):
        raise RegistryError("registry root must be an object")
    return data


def _require_keys(value: dict[str, Any], keys: set[str], context: str) -> None:
    missing = sorted(keys - set(value))
    if missing:
        raise RegistryError(f"{context} missing keys: {', '.join(missing)}")


def _unique(values: list[str], context: str) -> None:
    duplicates = sorted(item for item, count in Counter(values).items() if count > 1)
    if duplicates:
        raise RegistryError(f"duplicate {context}: {', '.join(duplicates)}")


def validate_registry(data: dict[str, Any]) -> dict[str, int]:
    _require_keys(
        data,
        {
            "schema_version",
            "registry_version",
            "target",
            "policy",
            "evidence",
            "top_level_blocks",
            "cluster_commands",
            "nested_constructs",
            "execution_contract",
        },
        "registry",
    )
    if data["schema_version"] != "1.1.0":
        raise RegistryError("unsupported schema_version")

    target = data["target"]
    _require_keys(
        target,
        {
            "product",
            "product_version",
            "source_commit",
            "executable_sha256",
            "platform",
            "execution_mode",
        },
        "target",
    )
    if len(target["source_commit"]) != 40:
        raise RegistryError("target.source_commit must contain 40 hexadecimal characters")
    if len(target["executable_sha256"]) != 64:
        raise RegistryError("target.executable_sha256 must contain 64 hexadecimal characters")
    for field in ("source_commit", "executable_sha256"):
        try:
            int(target[field], 16)
        except ValueError as exc:
            raise RegistryError(f"target.{field} is not hexadecimal") from exc

    evidence = data["evidence"]
    evidence_ids = [item["id"] for item in evidence]
    _unique(evidence_ids, "evidence id")
    evidence_by_id = {item["id"]: item for item in evidence}
    for item in evidence:
        _require_keys(item, {"id", "kind", "locator", "claim"}, item["id"])
        locator = item["locator"]
        if item["kind"] == "source":
            if not locator.startswith("source/"):
                raise RegistryError(f"{item['id']} source locator must start with source/")
            if ".." in Path(locator).parts or Path(locator).is_absolute():
                raise RegistryError(f"{item['id']} source locator must be relative and contained")
        if "line_end" in item and "line_start" not in item:
            raise RegistryError(f"{item['id']} has line_end without line_start")
        if item.get("line_end", item.get("line_start", 1)) < item.get("line_start", 1):
            raise RegistryError(f"{item['id']} has an inverted line range")

    blocks = data["top_level_blocks"]
    block_ids = [item["id"] for item in blocks]
    _unique(block_ids, "block id")
    _unique([item["canonical"].upper() for item in blocks], "canonical block token")

    commands = data["cluster_commands"]
    command_ids = [item["id"] for item in commands]
    _unique(command_ids, "command id")
    _unique([item["canonical"].upper() for item in commands], "canonical command token")
    _unique([item["dispatch_prefix"].upper() for item in commands], "command dispatch prefix")

    constructs = data["nested_constructs"]
    construct_ids = [item["id"] for item in constructs]
    _unique(construct_ids, "nested construct id")
    _unique(
        [f"{item['parent_block_id']}:{item['match_prefix'].lower()}" for item in constructs],
        "nested construct match prefix",
    )

    records = [("block", item) for item in blocks] + [
        ("command", item) for item in commands
    ] + [("construct", item) for item in constructs]
    for kind, item in records:
        _require_keys(
            item,
            {
                "id",
                "canonical",
                "summary",
                "coverage",
                "parameters",
                "evidence_ids",
                "remaining_work",
            },
            item["id"],
        )
        if kind == "block":
            _require_keys(
                item,
                {"lookup_token", "match_rule", "required", "parser", "termination"},
                item["id"],
            )
        elif kind == "command":
            _require_keys(item, {"parent_block_id", "dispatch_prefix"}, item["id"])
        else:
            _require_keys(
                item,
                {"parent_block_id", "match_prefix", "kind"},
                item["id"],
            )
        if item["coverage"] not in VALID_COVERAGE:
            raise RegistryError(f"{item['id']} has invalid coverage {item['coverage']}")
        if not item["summary"].strip():
            raise RegistryError(f"{item['id']} has an empty summary")
        missing_evidence = sorted(set(item["evidence_ids"]) - set(evidence_by_id))
        if missing_evidence:
            raise RegistryError(
                f"{item['id']} references missing evidence: {', '.join(missing_evidence)}"
            )
        parameter_names = [parameter["name"].lower() for parameter in item["parameters"]]
        _unique(parameter_names, f"parameter in {item['id']}")
        for parameter in item["parameters"]:
            _require_keys(
                parameter,
                {"name", "value_type", "required", "summary"},
                f"parameter in {item['id']}",
            )
        if kind in {"command", "construct"} and item["parent_block_id"] not in block_ids:
            raise RegistryError(f"{item['id']} references missing parent block")
        body = item.get("body")
        if body:
            _require_keys(
                body,
                {"style", "termination", "variants", "dependencies"},
                f"body in {item['id']}",
            )
            variant_names = [variant["name"].lower() for variant in body["variants"]]
            _unique(variant_names, f"body variant in {item['id']}")
            for variant in body["variants"]:
                _require_keys(
                    variant,
                    {"name", "when", "rows", "constraints"},
                    f"body variant in {item['id']}",
                )
                row_names = [row["name"].lower() for row in variant["rows"]]
                _unique(row_names, f"body row in {item['id']}/{variant['name']}")
                for row in variant["rows"]:
                    _require_keys(
                        row,
                        {"name", "repetition", "fields"},
                        f"body row in {item['id']}/{variant['name']}",
                    )
                    field_names = [field["name"].lower() for field in row["fields"]]
                    _unique(field_names, f"body field in {item['id']}/{variant['name']}/{row['name']}")
                    for field in row["fields"]:
                        _require_keys(
                            field,
                            {"name", "value_type", "required", "summary"},
                            f"body field in {item['id']}/{variant['name']}/{row['name']}",
                        )

    execution = data["execution_contract"]
    _require_keys(
        execution,
        {
            "invocation",
            "input_extension",
            "success_policy",
            "control_files",
            "evidence_ids",
        },
        "execution_contract",
    )
    missing_execution_evidence = sorted(set(execution["evidence_ids"]) - set(evidence_by_id))
    if missing_execution_evidence:
        raise RegistryError(
            "execution_contract references missing evidence: "
            + ", ".join(missing_execution_evidence)
        )

    return {
        "evidence": len(evidence),
        "blocks": len(blocks),
        "commands": len(commands),
        "constructs": len(constructs),
        "documented_records": sum(
            item["coverage"] in {"documented", "runtime-verified"}
            for _, item in records
        ),
    }


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _evidence_links(data: dict[str, Any]) -> dict[str, str]:
    return {item["id"]: f"[{item['id']}](#{item['id'].replace('.', '')})" for item in data["evidence"]}


def _render_body(lines: list[str], title: str, body: dict[str, Any]) -> None:
    lines.extend([
        f"### `{title}` body",
        "",
        f"Termination: {body['termination']}. Dependencies: "
        + ("; ".join(body["dependencies"]) or "none"),
        "",
    ])
    for variant in body["variants"]:
        lines.append(f"- **{variant['name']}** ({variant['when']}):")
        for row in variant["rows"]:
            fields = ", ".join(
                f"`{field['name']}`:{field['value_type']}" for field in row["fields"]
            )
            lines.append(f"  - `{row['name']}` [{row['repetition']}]: {fields}")
        lines.extend(f"  - Constraint: {item}" for item in variant["constraints"])
    lines.append("")


def render_reference(data: dict[str, Any], registry_path: Path) -> str:
    counts = validate_registry(data)
    target = data["target"]
    evidence_links = _evidence_links(data)
    registry_digest = hashlib.sha256(registry_path.read_bytes()).hexdigest().upper()
    lines: list[str] = [
        "# BSAM 2.4 current input API",
        "",
        "> Generated by `python tools/registry_tools.py generate`. Do not edit this file directly.",
        "",
        "## Baseline",
        "",
        f"- Product: {target['product']} {target['product_version']}",
        f"- Source commit: `{target['source_commit']}`",
        f"- Executable SHA-256: `{target['executable_sha256']}`",
        f"- Platform/mode: {target['platform']} {target['execution_mode']}",
        f"- Registry version: `{data['registry_version']}`",
        f"- Registry SHA-256: `{registry_digest}`",
        f"- Current inventory: {counts['blocks']} top-level blocks, {counts['commands']} cluster commands, and {counts['constructs']} nested constructs",
        "",
        "Coverage labels describe specification work, not parser availability. `identified` means an active dispatch path is known but its full data grammar is not yet documented.",
        "",
        "## Top-level blocks",
        "",
        "| Token | Required | Match rule | Parser | Coverage | Purpose |",
        "|---|---:|---|---|---|---|",
    ]
    for block in data["top_level_blocks"]:
        lines.append(
            "| `{}` | {} | {} | `{}` | {} | {} |".format(
                _escape_cell(block["canonical"]),
                "yes" if block["required"] else "no",
                _escape_cell(block["match_rule"]),
                _escape_cell(block["parser"]),
                _escape_cell(block["coverage"]),
                _escape_cell(block["summary"]),
            )
        )

    lines.extend(["", "## Block details", ""])
    for block in data["top_level_blocks"]:
        evidence = ", ".join(evidence_links[item] for item in block["evidence_ids"])
        tokens = ", ".join(f"`{token}`" for token in block["termination"]["tokens"])
        lines.extend(
            [
                f"### `{block['canonical']}`",
                "",
                block["summary"],
                "",
                f"- Registry ID: `{block['id']}`",
                f"- Lookup token/matcher: `{block['lookup_token']}` / {block['match_rule']}",
                f"- Required: {'yes' if block['required'] else 'no'}",
                f"- Termination: {tokens} ({block['termination']['certainty']})",
                f"- Coverage: {block['coverage']}",
                f"- Evidence: {evidence}",
            ]
        )
        if block["parameters"]:
            lines.extend(["", "Known parameters:", ""])
            for parameter in block["parameters"]:
                required = "required" if parameter["required"] else "optional"
                lines.append(
                    f"- `{parameter['name']}` ({parameter['value_type']}, {required}): {parameter['summary']}"
                )
        if block["remaining_work"]:
            lines.extend(["", "Remaining specification work:", ""])
            lines.extend(f"- {item}" for item in block["remaining_work"])
        lines.append("")

    lines.extend(
        [
            "## Finite-element cluster commands",
            "",
            "The parser dispatches on the first five characters (the leading `*` plus four letters). Canonical spellings below are generation targets; parameter completeness varies with the coverage label.",
            "",
            "| Command | Dispatch | Coverage | Known line parameters | Purpose |",
            "|---|---|---|---|---|",
        ]
    )
    for command in data["cluster_commands"]:
        parameters = ", ".join(f"`{item['name']}`" for item in command["parameters"]) or "—"
        lines.append(
            "| `{}` | `{}` | {} | {} | {} |".format(
                _escape_cell(command["canonical"]),
                _escape_cell(command["dispatch_prefix"]),
                _escape_cell(command["coverage"]),
                parameters,
                _escape_cell(command["summary"]),
            )
        )

    lines.extend(["", "## Documented command bodies", ""])
    for command in data["cluster_commands"]:
        body = command.get("body")
        if not body:
            continue
        _render_body(lines, command["canonical"], body)

    lines.extend([
        "## Nested block constructs",
        "",
        "| Parent | Construct | Match prefix | Kind | Coverage | Purpose |",
        "|---|---|---|---|---|---|",
    ])
    for construct in data["nested_constructs"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} |".format(
                _escape_cell(construct["parent_block_id"]),
                _escape_cell(construct["canonical"]),
                _escape_cell(construct["match_prefix"]),
                _escape_cell(construct["kind"]),
                _escape_cell(construct["coverage"]),
                _escape_cell(construct["summary"]),
            )
        )

    lines.extend(["", "## Nested construct details", ""])
    for construct in data["nested_constructs"]:
        evidence = ", ".join(evidence_links[item] for item in construct["evidence_ids"])
        lines.extend([
            f"### `{construct['canonical']}`",
            "",
            construct["summary"],
            "",
            f"- Registry ID: `{construct['id']}`",
            f"- Match prefix: `{construct['match_prefix']}`",
            f"- Coverage: {construct['coverage']}",
            f"- Evidence: {evidence}",
        ])
        if construct["parameters"]:
            lines.extend(["", "Known parameters:", ""])
            for parameter in construct["parameters"]:
                required = "required" if parameter["required"] else "optional"
                lines.append(
                    f"- `{parameter['name']}` ({parameter['value_type']}, {required}): {parameter['summary']}"
                )
        if construct["remaining_work"]:
            lines.extend(["", "Remaining specification work:", ""])
            lines.extend(f"- {item}" for item in construct["remaining_work"])
        lines.append("")
        if construct.get("body"):
            _render_body(lines, construct["canonical"], construct["body"])

    lines.extend(["", "## Execution contract", ""])
    execution = data["execution_contract"]
    lines.extend(
        [
            f"- Invocation: `{execution['invocation']}`",
            f"- Input extension: `{execution['input_extension']}`",
            f"- Success policy: {execution['success_policy']}",
            "- Known run/control artifacts:",
        ]
    )
    lines.extend(
        f"  - `{item['suffix']}`: {item['role']}" for item in execution["control_files"]
    )

    lines.extend(["", "## Evidence index", ""])
    for item in data["evidence"]:
        anchor = item["id"].replace(".", "")
        line_info = ""
        if "line_start" in item:
            line_info = f":{item['line_start']}"
            if item.get("line_end") != item["line_start"]:
                line_info += f"-{item.get('line_end', item['line_start'])}"
        lines.extend(
            [
                f"<a id=\"{anchor}\"></a>",
                f"- `{item['id']}` — {item['kind']}: `{item['locator']}{line_info}` — {item['claim']}",
            ]
        )

    lines.extend(
        [
            "",
            "## Coverage warning",
            "",
            "This is an initial active-dispatch inventory. It is not yet the complete parameter/type reference required by G1, and it must not be used to claim full generation support.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate", "generate", "check"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        data = load_registry(args.registry)
        counts = validate_registry(data)
        rendered = render_reference(data, args.registry)
    except (OSError, json.JSONDecodeError, RegistryError) as exc:
        print(f"registry error: {exc}", file=sys.stderr)
        return 1

    if args.action == "validate":
        print(
            "valid registry: "
            f"{counts['blocks']} blocks, {counts['commands']} cluster commands, "
            f"{counts['constructs']} nested constructs, "
            f"{counts['evidence']} evidence records"
        )
        return 0
    if args.action == "generate":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"generated {args.output.relative_to(REPO_ROOT)}")
        return 0

    try:
        existing = args.output.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"generated reference missing: {exc}", file=sys.stderr)
        return 1
    if existing != rendered:
        print("generated reference is stale; run the generate action", file=sys.stderr)
        return 1
    print("generated reference is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
