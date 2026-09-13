"""Aggregate repository checks for generated BSAM specification contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from . import dispatch_audit, registry_tools
except ImportError:  # Direct script execution places tools/ on sys.path.
    import dispatch_audit  # type: ignore[no-redef]
    import registry_tools  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = REPO_ROOT / "schemas" / "capability-registry.schema.json"
DEFAULT_DISPATCH_AUDIT = REPO_ROOT / "docs" / "bsam" / "DISPATCH_AUDIT.md"


class RepositoryCheckError(ValueError):
    """Raised when a checked-in contract or generated artifact has drifted."""


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}\n"
    if marker not in text:
        raise RepositoryCheckError(f"dispatch audit is missing section: {heading}")
    body = text.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def _first_column_tokens(section: str) -> set[str]:
    return {
        match.group(1)
        for line in section.splitlines()
        if (match := re.match(r"^\| `([^`]+)` \|", line))
    }


def validate_committed_dispatch(registry: dict[str, Any], text: str) -> None:
    commit_match = re.search(r"Pinned source commit: `([0-9a-fA-F]{40})`", text)
    if not commit_match or commit_match.group(1) != registry["target"]["source_commit"]:
        raise RepositoryCheckError("dispatch audit source commit does not match the registry")
    expected = {
        "Top-level initialization path": {
            item["canonical"] for item in registry["top_level_blocks"]
        },
        "Finite-element cluster command dispatch": {
            item["dispatch_prefix"] for item in registry["cluster_commands"]
        },
        "BOUNDARY construct dispatch": {
            item["match_prefix"] for item in registry["nested_constructs"]
            if item["parent_block_id"] == "block.boundary"
        },
    }
    for heading, tokens in expected.items():
        actual = _first_column_tokens(_section(text, heading))
        if actual != tokens:
            raise RepositoryCheckError(
                f"dispatch audit {heading} tokens differ from the registry"
            )
    reconciliation = _section(text, "Reconciliation")
    if "Primary dispatch coverage is **complete**." not in reconciliation:
        raise RepositoryCheckError("dispatch audit does not certify complete coverage")
    gap_lines = re.findall(r"^- `[^`]+`: (.+)$", reconciliation, re.MULTILINE)
    if len(gap_lines) != 6 or any(value != "none" for value in gap_lines):
        raise RepositoryCheckError("dispatch audit contains missing or malformed gap results")


def validate_schema_binding(registry: dict[str, Any], schema: dict[str, Any]) -> None:
    if schema.get("properties", {}).get("schema_version", {}).get("const") != registry.get(
        "schema_version"
    ):
        raise RepositoryCheckError("registry and JSON Schema versions differ")
    properties = set(schema.get("properties", {}))
    required = set(schema.get("required", ()))
    registry_keys = set(registry)
    if registry_keys - properties or required - registry_keys:
        raise RepositoryCheckError("registry root keys and JSON Schema binding differ")


def validate_ci_binding(registry: dict[str, Any]) -> None:
    contract = registry["repository_check_contract"]
    workflow = (REPO_ROOT / contract["ci_workflow"]).resolve()
    if not workflow.is_relative_to(REPO_ROOT) or not workflow.is_file():
        raise RepositoryCheckError("registered CI workflow is missing or outside the repository")
    text = workflow.read_text(encoding="utf-8")
    for command in (contract["repository_command"], contract["test_command"]):
        if f"run: {command}" not in text:
            raise RepositoryCheckError(f"CI workflow does not run registered command: {command}")


def check_repository(
    registry_path: Path = registry_tools.DEFAULT_REGISTRY,
    schema_path: Path = DEFAULT_SCHEMA,
    dispatch_path: Path = DEFAULT_DISPATCH_AUDIT,
    source_root: Path | None = None,
) -> dict[str, Any]:
    registry = registry_tools.load_registry(registry_path)
    counts = registry_tools.validate_registry(registry)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate_schema_binding(registry, schema)
    expected_reference = registry_tools.render_reference(registry, registry_path)
    actual_reference = registry_tools.DEFAULT_OUTPUT.read_text(encoding="utf-8")
    if actual_reference != expected_reference:
        raise RepositoryCheckError("generated registry reference is stale")
    dispatch_text = dispatch_path.read_text(encoding="utf-8")
    validate_committed_dispatch(registry, dispatch_text)
    validate_ci_binding(registry)

    live_source_checked = False
    if source_root is not None and source_root.is_dir():
        result = dispatch_audit.audit(source_root, registry_path)
        if not result["complete"] or dispatch_audit.render(result) != dispatch_text:
            raise RepositoryCheckError("live source dispatch audit differs from the committed audit")
        live_source_checked = True
    return {
        "registry_version": registry["registry_version"],
        "required_checks": registry["repository_check_contract"]["required_checks"],
        "generated_artifacts": counts["generated_artifacts"],
        "live_source_dispatch": "passed" if live_source_checked else "skipped-source-unavailable",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=registry_tools.DEFAULT_REGISTRY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--dispatch-audit", type=Path, default=DEFAULT_DISPATCH_AUDIT)
    parser.add_argument("--source-root", type=Path, default=dispatch_audit.DEFAULT_SOURCE_ROOT)
    args = parser.parse_args(argv)
    source_root = args.source_root if args.source_root.is_dir() else None
    try:
        result = check_repository(
            args.registry, args.schema, args.dispatch_audit, source_root,
        )
    except (
        OSError, json.JSONDecodeError, registry_tools.RegistryError,
        dispatch_audit.AuditError, RepositoryCheckError,
    ) as exc:
        print(f"repository checks failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
