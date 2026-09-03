"""Audit primary reachable BSAM input dispatches against the capability registry.

Only dispatch tokens, routine names, and relative source locations are emitted. The
BSAM source remains outside this repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "specs" / "bsam-2.4" / "capabilities.json"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "bsam" / "DISPATCH_AUDIT.md"
DEFAULT_SOURCE_ROOT = REPO_ROOT.parent / "bsam20"

INITIALIZERS = (
    ("INPUT", "INP_INI", "source/libbsam/inp_ini.f90"),
    ("SOLVER", "SOLVE_INI", "source/libbsam/solve_ini.f90"),
    ("UFUNCTIONS", "UFUNCTION_INI", "source/libbsam/ufunction_ini.f90"),
    ("MOISTURE", "MOI_INI", "source/libbsam/moisture.f90"),
    ("CLUSTERS", "IAP_INI", "source/libbsam/iap_ini.f90"),
    ("BOUNDARY", "IBN_INI", "source/libbsam/ibn_ini.f90"),
    ("CONSTITUTIVE", "CON_INI", "source/libbsam/con_ini.f90"),
    ("TABLES", "TABLE_INI", "source/libbsam/table_ini.f90"),
    ("STATISTICAL", "STAT_DIST_INI", "source/libbsam/stat_dist_ini.f90"),
    ("MATERIALS", "MAT_INI", "source/libbsam/mat_ini.f90"),
    ("FAILURE", "FAI_INI", "source/libbsam/fai_ini.f90"),
    ("USER", "USF_INI", "source/libbsam/usf_ini.f90"),
    ("CRACK", "CRK_INI", "source/libbsam/crk_ini.f90"),
)
MAIN_SOURCE = "source/bsam/mainf1.f90"
FE_SOURCE = "source/libbsam/mod_fe_input.f90"
BOUNDARY_SOURCE = "source/libbsam/ibn_ini.f90"
BOUNDARY_INTERNAL_CASES = {"*g-c"}


class AuditError(ValueError):
    pass


@dataclass(frozen=True)
class Dispatch:
    token: str
    locator: str


def _active_lines(path: Path) -> Iterable[tuple[int, str]]:
    for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("!"):
            continue
        yield number, raw.split("!", 1)[0]


def _source_file(source_root: Path, locator: str) -> Path:
    path = (source_root / locator).resolve()
    if not path.is_file() or not path.is_relative_to(source_root.resolve()):
        raise AuditError(f"missing or unsafe BSAM source locator: {locator}")
    return path


def _find_call(path: Path, routine: str, locator: str) -> Dispatch:
    pattern = re.compile(rf"\bcall\s+{re.escape(routine)}\s*\(", re.IGNORECASE)
    matches = [number for number, line in _active_lines(path) if pattern.search(line)]
    if len(matches) != 1:
        raise AuditError(f"expected one active {routine} call in {locator}; found {len(matches)}")
    return Dispatch(routine, f"{locator}:{matches[0]}")


def _find_block_lookup(path: Path, token: str, locator: str) -> Dispatch:
    pattern = re.compile(
        rf"\bcall\s+inp_block\s*\([^\r\n]*['\"]{re.escape(token)}['\"]",
        re.IGNORECASE,
    )
    matches = [number for number, line in _active_lines(path) if pattern.search(line)]
    if not matches:
        raise AuditError(f"no active INP_BLOCK lookup for {token} in {locator}")
    return Dispatch(token, f"{locator}:{matches[0]}")


def _star_cases(path: Path, locator: str) -> list[Dispatch]:
    pattern = re.compile(r"\bcase\s*\(\s*['\"](\*[A-Za-z0-9_-]+)['\"]", re.IGNORECASE)
    result = []
    for number, line in _active_lines(path):
        match = pattern.search(line)
        if match:
            result.append(Dispatch(match.group(1), f"{locator}:{number}"))
    return result


def _boundary_type_prelude(path: Path, locator: str) -> Dispatch:
    pattern = re.compile(r"\.eq\.\s*['\"](\*type)['\"]", re.IGNORECASE)
    matches = [
        Dispatch(match.group(1), f"{locator}:{number}")
        for number, line in _active_lines(path)
        if (match := pattern.search(line))
    ]
    if len(matches) != 1:
        raise AuditError(f"expected one active *TYPE boundary prelude; found {len(matches)}")
    return matches[0]


def _git_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


def _commented_initializer_calls(path: Path, locator: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r"^\s*!+\s*(?:[A-Za-z0-9]+\s+)?call\s+(\w+_INI)\s*\(", re.IGNORECASE,
    )
    result = []
    for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        match = pattern.search(raw)
        if match:
            result.append({
                "routine": match.group(1),
                "classification": "unreachable commented-out initializer",
                "locator": f"{locator}:{number}",
            })
    return result


def _deprecated_block_lookups(source_root: Path) -> list[dict[str, str]]:
    root = source_root / "source" / "libbsam" / "deprecated"
    pattern = re.compile(
        r"\bcall\s+inp_block\s*\([^\r\n]*['\"]([A-Za-z0-9 _-]+)['\"]",
        re.IGNORECASE,
    )
    result = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        locator = path.relative_to(source_root).as_posix()
        for number, line in _active_lines(path):
            match = pattern.search(line)
            if match:
                result.append({
                    "token": match.group(1),
                    "classification": "inactive deprecated source; not called by main input sequence",
                    "locator": f"{locator}:{number}",
                })
    return result


def audit(source_root: Path, registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    source_root = source_root.resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    commit = _git_commit(source_root)
    expected_commit = registry["target"]["source_commit"]
    if commit != expected_commit:
        raise AuditError(f"BSAM source commit {commit} does not match registry {expected_commit}")

    main = _source_file(source_root, MAIN_SOURCE)
    top_level = []
    for token, routine, locator in INITIALIZERS:
        call = _find_call(main, routine, MAIN_SOURCE)
        lookup = None
        if token != "INPUT":
            lookup = _find_block_lookup(_source_file(source_root, locator), token, locator)
        top_level.append({
            "token": token,
            "initializer": routine,
            "call": call.locator,
            "lookup": lookup.locator if lookup else "handled by INPUT initializer",
        })

    fe_cases = _star_cases(_source_file(source_root, FE_SOURCE), FE_SOURCE)
    boundary_cases = _star_cases(_source_file(source_root, BOUNDARY_SOURCE), BOUNDARY_SOURCE)
    boundary_internal = [
        item for item in boundary_cases if item.token.casefold() in BOUNDARY_INTERNAL_CASES
    ]
    boundary_dispatches = [
        _boundary_type_prelude(_source_file(source_root, BOUNDARY_SOURCE), BOUNDARY_SOURCE),
        *(item for item in boundary_cases if item.token.casefold() not in BOUNDARY_INTERNAL_CASES),
    ]

    registered_blocks = {item["canonical"].casefold() for item in registry["top_level_blocks"]}
    registered_fe = {item["dispatch_prefix"].casefold() for item in registry["cluster_commands"]}
    registered_boundary = {
        item["match_prefix"].casefold()
        for item in registry["nested_constructs"]
        if item["parent_block_id"] == "block.boundary"
    }
    found_blocks = {item["token"].casefold() for item in top_level}
    found_fe = {item.token.casefold() for item in fe_cases}
    found_boundary = {item.token.casefold() for item in boundary_dispatches}
    gaps = {
        "top_level_missing_from_registry": sorted(found_blocks - registered_blocks),
        "top_level_missing_from_source": sorted(registered_blocks - found_blocks),
        "cluster_missing_from_registry": sorted(found_fe - registered_fe),
        "cluster_missing_from_source": sorted(registered_fe - found_fe),
        "boundary_missing_from_registry": sorted(found_boundary - registered_boundary),
        "boundary_missing_from_source": sorted(registered_boundary - found_boundary),
    }
    return {
        "source_commit": commit,
        "top_level": top_level,
        "cluster_dispatches": [item.__dict__ for item in fe_cases],
        "boundary_dispatches": [item.__dict__ for item in boundary_dispatches],
        "classified_internal_cases": [
            {**item.__dict__, "classification": "internal G-CONTROL option token"}
            for item in boundary_internal
        ],
        "commented_initializers": _commented_initializer_calls(main, MAIN_SOURCE),
        "deprecated_block_lookups": _deprecated_block_lookups(source_root),
        "gaps": gaps,
        "complete": not any(gaps.values()),
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "# BSAM primary dispatch audit",
        "",
        f"Pinned source commit: `{result['source_commit']}`.",
        "",
        "This generated audit compares the active initialization sequence and primary input dispatches with the capability registry. It records tokens and source locations only; BSAM source is not copied into this repository.",
        "",
        "## Top-level initialization path",
        "",
        "| Token | Initializer | Active call | Block lookup |",
        "|---|---|---|---|",
    ]
    for item in result["top_level"]:
        lines.append(
            f"| `{item['token']}` | `{item['initializer']}` | `{item['call']}` | `{item['lookup']}` |"
        )
    lines.extend([
        "",
        "## Finite-element cluster command dispatch",
        "",
        "| Prefix | Source |",
        "|---|---|",
    ])
    lines.extend(
        f"| `{item['token']}` | `{item['locator']}` |" for item in result["cluster_dispatches"]
    )
    lines.extend([
        "",
        "## BOUNDARY construct dispatch",
        "",
        "| Prefix | Source |",
        "|---|---|",
    ])
    lines.extend(
        f"| `{item['token']}` | `{item['locator']}` |" for item in result["boundary_dispatches"]
    )
    lines.extend([
        "",
        "## Classified internal cases",
        "",
        "| Token | Classification | Source |",
        "|---|---|---|",
    ])
    lines.extend(
        f"| `{item['token']}` | {item['classification']} | `{item['locator']}` |"
        for item in result["classified_internal_cases"]
    )
    lines.extend([
        "",
        "## Reconciliation",
        "",
        f"Primary dispatch coverage is **{'complete' if result['complete'] else 'incomplete'}**.",
        "",
    ])
    for name, values in result["gaps"].items():
        lines.append(f"- `{name}`: {', '.join(values) if values else 'none'}")
    lines.extend([
        "",
        "## Excluded initialization paths",
        "",
        "These paths are present in the pinned tree but are not reachable from the active main input sequence.",
        "",
        "| Routine or token | Classification | Source |",
        "|---|---|---|",
    ])
    lines.extend(
        f"| `{item['routine']}` | {item['classification']} | `{item['locator']}` |"
        for item in result["commented_initializers"]
    )
    lines.extend(
        f"| `{item['token']}` | {item['classification']} | `{item['locator']}` |"
        for item in result["deprecated_block_lookups"]
    )
    lines.extend([
        "",
        "This closes primary token enumeration only. Record variants, subordinate value dispatches, grammar, and semantic dependencies remain tracked in M1.2 and M1.3.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("scan", "generate", "check"))
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        result = audit(args.source_root, args.registry)
        rendered = render(result)
        if args.command == "scan":
            print(json.dumps(result, indent=2))
        elif args.command == "generate":
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {args.output}")
        elif not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise AuditError(f"dispatch audit is stale; run generate: {args.output}")
        if not result["complete"]:
            raise AuditError("primary dispatch audit has registry/source gaps")
    except (AuditError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"dispatch audit failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
