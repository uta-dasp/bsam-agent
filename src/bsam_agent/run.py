"""Synchronous, isolated Windows BSAM run supervision."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .document import SourceDocument
from .registry import load_registry


SUCCESS_SENTINEL = "----- END OF PROGRAM ------"
FATAL_MARKERS = (
    "===ERROR:",
    "ERROR:",
    " input block required",
    "doesn't exist in the input directory",
)


class RunError(ValueError):
    """Raised when run preflight or supervision cannot proceed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def classify_run(exit_code: int | None, text: str, stop_requested: bool = False) -> dict[str, Any]:
    sentinel = SUCCESS_SENTINEL in text
    fatal = sorted(marker for marker in FATAL_MARKERS if marker.lower() in text.lower())
    if stop_requested:
        classification = "stopped"
    elif sentinel and not fatal and exit_code == 0:
        classification = "succeeded"
    elif fatal or (exit_code is not None and exit_code != 0):
        classification = "failed"
    else:
        classification = "unknown"
    return {
        "classification": classification,
        "success_sentinel_seen": sentinel,
        "fatal_markers": fatal,
    }


def _write_manifest(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_bsam(
    deck: Path,
    output_directory: Path,
    executable: Path,
    timeout_seconds: float = 3600.0,
    stop_grace_seconds: float = 30.0,
) -> dict[str, Any]:
    registry = load_registry()
    deck = deck.resolve()
    executable = executable.resolve()
    output_directory = output_directory.resolve()
    if not deck.is_file() or deck.suffix.lower() != ".in":
        raise RunError(f"BSAM input deck not found or not .in: {deck}")
    if not executable.is_file():
        raise RunError(f"BSAM executable not found: {executable}")
    actual_executable_hash = _sha256(executable)
    expected_executable_hash = registry["target"]["executable_sha256"].upper()
    if actual_executable_hash != expected_executable_hash:
        raise RunError(
            "executable fingerprint mismatch: "
            f"expected {expected_executable_hash}, found {actual_executable_hash}"
        )
    if output_directory.exists():
        raise RunError(f"output directory already exists: {output_directory}")

    document = SourceDocument.read(deck)
    errors = [item for item in document.diagnostics() if item.severity == "error"]
    if errors:
        raise RunError("deck failed preflight: " + "; ".join(item.message for item in errors))

    output_directory.mkdir(parents=False)
    manifest_path = output_directory / "run-manifest.json"
    stdout_path = output_directory / "process.stdout.log"
    stderr_path = output_directory / "process.stderr.log"
    command = [
        str(executable),
        "-I",
        str(deck.parent),
        "-O",
        str(output_directory),
        deck.stem,
    ]
    started = datetime.now(timezone.utc)
    manifest: dict[str, Any] = {
        "state": "starting",
        "classification": "pending",
        "deck": str(deck),
        "deck_sha256": document.sha256,
        "executable": str(executable),
        "executable_sha256": actual_executable_hash,
        "output_directory": str(output_directory),
        "command": command,
        "started_at": started.isoformat(),
        "timeout_seconds": timeout_seconds,
    }
    _write_manifest(manifest_path, manifest)

    timed_out = False
    exit_code: int | None = None
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=output_directory,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
            )
            manifest["state"] = "running"
            manifest["process_id"] = process.pid
            _write_manifest(manifest_path, manifest)
            try:
                exit_code = process.wait(timeout=None if timeout_seconds <= 0 else timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                (output_directory / f"{deck.stem}.exit").write_text("2\n", encoding="ascii")
                try:
                    exit_code = process.wait(timeout=stop_grace_seconds)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        exit_code = process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        exit_code = process.wait()
    except OSError as exc:
        manifest.update({
            "state": "terminal",
            "classification": "failed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        })
        _write_manifest(manifest_path, manifest)
        raise RunError(f"failed to start or supervise BSAM: {exc}") from exc

    listing_path = output_directory / f"{deck.stem}.lst"
    combined_parts = []
    for path in (listing_path, stdout_path, stderr_path):
        if path.is_file():
            combined_parts.append(path.read_text(encoding="latin-1", errors="replace"))
    classification = classify_run(exit_code, "\n".join(combined_parts), stop_requested=timed_out)
    finished = datetime.now(timezone.utc)
    artifacts = sorted(
        str(path.relative_to(output_directory))
        for path in output_directory.iterdir()
        if path.is_file()
    )
    manifest.update({
        "state": "terminal",
        **classification,
        "process_exit_code": exit_code,
        "timed_out": timed_out,
        "finished_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "artifacts": artifacts,
    })
    _write_manifest(manifest_path, manifest)
    return manifest
