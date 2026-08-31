"""Command-line entry point for the deterministic BSAM Agent core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from . import __version__
from .change import ChangeError, apply_plan, plan_parameter_change, review_plan, write_plan
from .registry import load_registry
from .run import RunError, request_run_stop, run_bsam, run_status
from .source_set import SourceSet


def _source_set(path_text: str, workspace_root: str | None = None) -> SourceSet:
    path = Path(path_text)
    boundary = Path(workspace_root) if workspace_root else None
    return SourceSet.read(path, boundary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bsam-agent", description="Local deterministic BSAM input tooling")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="inspect a deck without changing it")
    inspect_parser.add_argument("deck")
    inspect_parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    inspect_parser.add_argument("--workspace-root", help="contain the root deck and all include targets")

    validate_parser = subparsers.add_parser("validate", help="run conservative current-syntax validation")
    validate_parser.add_argument("deck")
    validate_parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    validate_parser.add_argument("--workspace-root", help="contain the root deck and all include targets")

    plan_parser = subparsers.add_parser("plan-change", help="plan a minimal edit to an existing key/value")
    plan_parser.add_argument("deck")
    plan_parser.add_argument("--block", required=True)
    plan_parser.add_argument("--construct", required=True)
    plan_parser.add_argument("--parameter", required=True)
    plan_parser.add_argument("--value", required=True)
    plan_parser.add_argument("--occurrence", type=int, default=1)
    plan_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    plan_parser.add_argument("--out", required=True, help="new JSON plan path")

    apply_parser = subparsers.add_parser("apply-change", help="apply a revision-bound plan to a new deck")
    apply_parser.add_argument("plan")
    apply_parser.add_argument("--out", required=True, help="new deck path; in-place writes are rejected")
    apply_parser.add_argument("--audit-out", help="new immutable audit JSON path; defaults beside output")

    diff_parser = subparsers.add_parser("diff", help="review a fresh change plan and its unified source diff")
    diff_parser.add_argument("plan")
    diff_parser.add_argument("--compact", action="store_true", help="emit compact JSON")

    run_parser = subparsers.add_parser("run", help="run a validated deck with the pinned BSAM executable")
    run_parser.add_argument("deck")
    run_parser.add_argument("--output-dir", required=True, help="new isolated output directory")
    run_parser.add_argument("--executable", default=str(Path(__file__).resolve().parents[3] / "projects" / "bsam20.exe"))
    run_parser.add_argument("--timeout", type=float, default=3600.0, help="seconds before requesting a controlled stop; <=0 disables")
    run_parser.add_argument("--stop-grace", type=float, default=30.0, help="seconds to wait after a controlled stop request")
    run_parser.add_argument("--workspace-root", help="contain the deck and all include targets")

    status_parser = subparsers.add_parser("status", help="read the durable status of one isolated run")
    status_parser.add_argument("output_dir")
    status_parser.add_argument("--compact", action="store_true", help="emit compact JSON")

    stop_parser = subparsers.add_parser("stop", help="request a controlled stop for one active run")
    stop_parser.add_argument("output_dir")

    subparsers.add_parser("baseline", help="print the pinned registry baseline")
    return parser


def _print_json(value: object, compact: bool = False) -> None:
    print(json.dumps(value, indent=None if compact else 2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "baseline":
            registry = load_registry()
            _print_json({"registry_version": registry["registry_version"], **registry["target"]})
            return 0

        if args.command == "plan-change":
            plan = plan_parameter_change(
                Path(args.deck),
                args.block,
                args.construct,
                args.parameter,
                args.value,
                args.occurrence,
                Path(args.workspace_root) if args.workspace_root else None,
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
            return 0
        if args.command == "apply-change":
            audit_path = Path(args.audit_out) if args.audit_out else None
            _print_json(apply_plan(Path(args.plan), Path(args.out), audit_path))
            return 0
        if args.command == "diff":
            _print_json(review_plan(Path(args.plan)), args.compact)
            return 0
        if args.command == "run":
            result = run_bsam(
                Path(args.deck),
                Path(args.output_dir),
                Path(args.executable),
                args.timeout,
                args.stop_grace,
                Path(args.workspace_root) if args.workspace_root else None,
            )
            _print_json(result)
            return 0 if result["classification"] == "succeeded" else 3
        if args.command == "status":
            _print_json(run_status(Path(args.output_dir)), args.compact)
            return 0
        if args.command == "stop":
            _print_json(request_run_stop(Path(args.output_dir)))
            return 0

        source_set = _source_set(args.deck, args.workspace_root)
        inspection = source_set.inspection()
        if args.command == "inspect":
            _print_json(inspection, args.compact)
            return 0
        if args.command == "validate":
            result = {
                "source": inspection["source"],
                "sha256": inspection["sha256"],
                "source_set_sha256": inspection["source_set_sha256"],
                "diagnostics": inspection["diagnostics"],
                "summary": inspection["summary"],
            }
            _print_json(result, args.compact)
            return 2 if inspection["summary"]["errors"] else 0
    except (OSError, ValueError, ChangeError, RunError) as exc:
        _print_json({"error": str(exc)})
        return 2
    return 2
