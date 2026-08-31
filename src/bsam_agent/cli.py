"""Command-line entry point for the deterministic BSAM Agent core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from . import __version__
from .document import SourceDocument
from .registry import load_registry


def _document(path_text: str) -> SourceDocument:
    path = Path(path_text)
    if not path.is_file():
        raise FileNotFoundError(f"input deck not found: {path}")
    return SourceDocument.read(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bsam-agent", description="Local deterministic BSAM input tooling")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="inspect a deck without changing it")
    inspect_parser.add_argument("deck")
    inspect_parser.add_argument("--compact", action="store_true", help="emit compact JSON")

    validate_parser = subparsers.add_parser("validate", help="run conservative current-syntax validation")
    validate_parser.add_argument("deck")
    validate_parser.add_argument("--compact", action="store_true", help="emit compact JSON")

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

        document = _document(args.deck)
        inspection = document.inspection()
        if args.command == "inspect":
            _print_json(inspection, args.compact)
            return 0
        if args.command == "validate":
            result = {
                "source": inspection["source"],
                "sha256": inspection["sha256"],
                "diagnostics": inspection["diagnostics"],
                "summary": inspection["summary"],
            }
            _print_json(result, args.compact)
            return 2 if inspection["summary"]["errors"] else 0
    except (OSError, ValueError) as exc:
        _print_json({"error": str(exc)})
        return 2
    return 2
