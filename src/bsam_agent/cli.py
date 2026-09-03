"""Command-line entry point for the deterministic BSAM Agent core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from . import __version__
from .api import serve
from .chat import run_terminal_chat
from .change import (
    ChangeError,
    apply_plan,
    plan_add_set_members,
    plan_add_element,
    plan_add_node,
    plan_delete_node,
    plan_create_set,
    plan_expand_notch_plies,
    plan_import_mesh,
    plan_migrate_legacy_solver,
    plan_parameter_change,
    plan_rename_boundary_condition,
    review_plan,
    write_plan,
)
from .registry import load_registry
from .mesh import MeshImportError, import_ele
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

    node_parser = subparsers.add_parser("plan-add-node", help="plan a typed node insertion")
    node_parser.add_argument("deck")
    node_parser.add_argument("--cluster", required=True)
    node_parser.add_argument("--label", required=True, type=int)
    node_parser.add_argument("--x", required=True)
    node_parser.add_argument("--y", required=True)
    node_parser.add_argument("--z", required=True)
    node_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    node_parser.add_argument("--out", required=True, help="new JSON plan path")

    element_parser = subparsers.add_parser("plan-add-element", help="plan a typed element insertion")
    element_parser.add_argument("deck")
    element_parser.add_argument("--cluster", required=True)
    element_parser.add_argument("--label", required=True, type=int)
    element_parser.add_argument("--type", required=True, dest="element_type")
    element_parser.add_argument("--nodes", required=True, nargs="+", type=int)
    element_parser.add_argument("--elset")
    element_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    element_parser.add_argument("--out", required=True, help="new JSON plan path")

    delete_node_parser = subparsers.add_parser(
        "plan-delete-node", help="plan deletion of an unreferenced node"
    )
    delete_node_parser.add_argument("deck")
    delete_node_parser.add_argument("--cluster", required=True)
    delete_node_parser.add_argument("--label", required=True, type=int)
    delete_node_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    delete_node_parser.add_argument("--out", required=True, help="new JSON plan path")

    create_set_parser = subparsers.add_parser("plan-create-set", help="plan a typed FE set")
    create_set_parser.add_argument("deck")
    create_set_parser.add_argument("--cluster", required=True)
    create_set_parser.add_argument("--kind", required=True, choices=("node", "element"))
    create_set_parser.add_argument("--name", required=True)
    create_set_parser.add_argument("--members", required=True, nargs="+", type=int)
    create_set_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    create_set_parser.add_argument("--out", required=True, help="new JSON plan path")

    add_members_parser = subparsers.add_parser(
        "plan-add-set-members", help="plan typed additions to an existing FE set"
    )
    add_members_parser.add_argument("deck")
    add_members_parser.add_argument("--cluster", required=True)
    add_members_parser.add_argument("--kind", required=True, choices=("node", "element"))
    add_members_parser.add_argument("--name", required=True)
    add_members_parser.add_argument("--members", required=True, nargs="+", type=int)
    add_members_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    add_members_parser.add_argument("--out", required=True, help="new JSON plan path")

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

    serve_parser = subparsers.add_parser("serve", help="serve the loopback-only local tool API")
    serve_parser.add_argument("--workspace-root", required=True)
    serve_parser.add_argument("--port", type=int, default=8765)

    chat_parser = subparsers.add_parser("chat", help="start a local model-assisted terminal chat")
    chat_parser.add_argument("--workspace-root", required=True, help="contain all project files")
    chat_parser.add_argument(
        "--config", default="config/provider.local.json", help="local provider configuration"
    )
    chat_parser.add_argument(
        "--no-audit", action="store_true", help="disable privacy-safe digest audit metadata"
    )
    chat_parser.add_argument(
        "--session",
        help="relative local transcript path to save and resume; contains raw chat text",
    )

    import_parser = subparsers.add_parser(
        "import-mesh", help="import a manually prepared Abaqus-style .ele mesh"
    )
    import_parser.add_argument("mesh")
    import_parser.add_argument("--compact", action="store_true", help="emit compact JSON")

    import_plan_parser = subparsers.add_parser(
        "plan-import-mesh", help="plan import of a .ele mesh into an empty template cluster"
    )
    import_plan_parser.add_argument("template")
    import_plan_parser.add_argument("mesh")
    import_plan_parser.add_argument("--cluster", required=True)
    import_plan_parser.add_argument("--workspace-root", help="contain the template and mesh")
    import_plan_parser.add_argument("--out", required=True, help="new JSON plan path")

    notch_parser = subparsers.add_parser(
        "plan-expand-notch-plies",
        help="plan the approved notch_v1 two-to-eight-ply transformation",
    )
    notch_parser.add_argument("deck")
    notch_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    notch_parser.add_argument("--out", required=True, help="new JSON plan path")

    solver_parser = subparsers.add_parser(
        "plan-migrate-legacy-solver",
        help="plan legacy type-9 to current PARDISO solver syntax migration",
    )
    solver_parser.add_argument("deck")
    solver_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    solver_parser.add_argument("--out", required=True, help="new JSON plan path")

    rename_bc_parser = subparsers.add_parser(
        "plan-rename-boundary-condition",
        help="plan a boundary-condition rename and dependent loading updates",
    )
    rename_bc_parser.add_argument("deck")
    rename_bc_parser.add_argument("--old", required=True, dest="old_name")
    rename_bc_parser.add_argument("--new", required=True, dest="new_name")
    rename_bc_parser.add_argument("--workspace-root", help="contain the deck and all include targets")
    rename_bc_parser.add_argument("--out", required=True, help="new JSON plan path")
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
        if args.command == "serve":
            serve(Path(args.workspace_root), args.port)
            return 0
        if args.command == "chat":
            root = Path(args.workspace_root).resolve()
            session_path = None
            if args.session:
                supplied = Path(args.session)
                if supplied.is_absolute():
                    raise ValueError("chat session path must be relative to the workspace")
                session_path = (root / supplied).resolve()
                if not session_path.is_relative_to(root):
                    raise ValueError("chat session path escapes the workspace")
            return run_terminal_chat(
                Path(args.config), root, audit_enabled=not args.no_audit,
                session_path=session_path,
            )
        if args.command == "import-mesh":
            _print_json(import_ele(Path(args.mesh)).as_dict(), args.compact)
            return 0
        if args.command == "plan-import-mesh":
            plan = plan_import_mesh(
                Path(args.template), Path(args.mesh), args.cluster,
                Path(args.workspace_root) if args.workspace_root else None,
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
            return 0
        if args.command == "plan-expand-notch-plies":
            plan = plan_expand_notch_plies(
                Path(args.deck), Path(args.workspace_root) if args.workspace_root else None
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
            return 0
        if args.command == "plan-migrate-legacy-solver":
            plan = plan_migrate_legacy_solver(
                Path(args.deck), Path(args.workspace_root) if args.workspace_root else None
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
            return 0
        if args.command == "plan-rename-boundary-condition":
            plan = plan_rename_boundary_condition(
                Path(args.deck), args.old_name, args.new_name,
                Path(args.workspace_root) if args.workspace_root else None,
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
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
        if args.command == "plan-add-node":
            plan = plan_add_node(
                Path(args.deck), args.cluster, args.label, args.x, args.y, args.z,
                Path(args.workspace_root) if args.workspace_root else None,
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
            return 0
        if args.command == "plan-add-element":
            plan = plan_add_element(
                Path(args.deck), args.cluster, args.label, args.element_type,
                args.nodes, args.elset,
                Path(args.workspace_root) if args.workspace_root else None,
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
            return 0
        if args.command == "plan-delete-node":
            plan = plan_delete_node(
                Path(args.deck), args.cluster, args.label,
                Path(args.workspace_root) if args.workspace_root else None,
            )
            write_plan(plan, Path(args.out))
            _print_json(plan)
            return 0
        if args.command in {"plan-create-set", "plan-add-set-members"}:
            planner = plan_create_set if args.command == "plan-create-set" else plan_add_set_members
            plan = planner(
                Path(args.deck), args.cluster, args.kind, args.name, args.members,
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
    except (OSError, ValueError, ChangeError, MeshImportError, RunError) as exc:
        _print_json({"error": str(exc)})
        return 2
    return 2
