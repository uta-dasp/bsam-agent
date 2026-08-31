"""Isolated Windows BSAM run supervision with concurrent status/stop controls."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import load_registry
from .source_set import SourceSet


SUCCESS_SENTINEL = "----- END OF PROGRAM ------"
RUN_MANIFEST_SCHEMA_VERSION = "1.0.0"
STOP_REQUEST_SCHEMA_VERSION = "1.0.0"
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
    if sentinel and not fatal and exit_code == 0:
        classification = "succeeded"
    elif stop_requested:
        classification = "stopped"
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
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _load_json_object(path: Path, description: str) -> dict[str, Any]:
    value: Any = None
    for attempt in range(10):
        try:
            with path.open("r", encoding="utf-8") as stream:
                value = json.load(stream)
            break
        except json.JSONDecodeError as exc:
            # An immutable stop request is created with exclusive write. A
            # concurrent reader can observe that directory entry just before
            # its small JSON body is complete, so retry only this transient.
            if attempt == 9:
                raise RunError(f"cannot read {description}: {path}: {exc}") from exc
            time.sleep(0.02)
        except OSError as exc:
            raise RunError(f"cannot read {description}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunError(f"{description} must be a JSON object: {path}")
    return value


def _load_run_manifest(output_directory: Path) -> tuple[Path, Path, dict[str, Any]]:
    output_directory = output_directory.resolve()
    if not output_directory.is_dir():
        raise RunError(f"run output directory not found: {output_directory}")
    manifest_path = output_directory / "run-manifest.json"
    if not manifest_path.is_file():
        raise RunError(f"run manifest not found: {manifest_path}")
    manifest = _load_json_object(manifest_path, "run manifest")
    recorded_directory = manifest.get("output_directory")
    if not isinstance(recorded_directory, str):
        raise RunError("run manifest has no valid output_directory")
    if Path(recorded_directory).resolve() != output_directory:
        raise RunError("run manifest output_directory does not match its containing directory")
    if manifest.get("state") not in {"starting", "running", "terminal"}:
        raise RunError("run manifest has an invalid state")
    deck = manifest.get("deck")
    if not isinstance(deck, str) or Path(deck).suffix.lower() != ".in":
        raise RunError("run manifest has no valid BSAM deck path")
    return output_directory, manifest_path, manifest


def _process_is_running(process_id: int) -> bool | None:
    """Return process liveness, or None when the OS will not disclose it."""
    if process_id <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, process_id)
        if not handle:
            return None if ctypes.get_last_error() == 5 else False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    return True


def _stop_request_path(output_directory: Path) -> Path:
    return output_directory / "stop-request.json"


def _validate_stop_request(
    request: dict[str, Any],
    output_directory: Path,
    manifest: dict[str, Any] | None = None,
) -> None:
    if request.get("schema_version") != STOP_REQUEST_SCHEMA_VERSION:
        raise RunError("stop request has an unsupported schema version")
    recorded_directory = request.get("output_directory")
    if not isinstance(recorded_directory, str) or Path(recorded_directory).resolve() != output_directory:
        raise RunError("stop request output_directory does not match its containing directory")
    if request.get("reason") not in {"user", "timeout"}:
        raise RunError("stop request has an invalid reason")
    if not isinstance(request.get("requested_at"), str):
        raise RunError("stop request has no requested_at timestamp")
    deck = request.get("deck")
    if not isinstance(deck, str) or Path(deck).suffix.lower() != ".in":
        raise RunError("stop request has no valid BSAM deck path")
    if manifest is not None:
        if Path(deck).resolve() != Path(manifest["deck"]).resolve():
            raise RunError("stop request deck does not match the run manifest")
        if request.get("deck_sha256") != manifest.get("deck_sha256"):
            raise RunError("stop request deck digest does not match the run manifest")


def _read_stop_request(
    output_directory: Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    path = _stop_request_path(output_directory)
    if not path.is_file():
        return None
    request = _load_json_object(path, "stop request")
    _validate_stop_request(request, output_directory, manifest)
    return request


def _create_stop_request(
    output_directory: Path,
    manifest: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    if reason not in {"user", "timeout"}:
        raise RunError(f"unsupported stop reason: {reason}")
    path = _stop_request_path(output_directory)
    request: dict[str, Any] = {
        "schema_version": STOP_REQUEST_SCHEMA_VERSION,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "output_directory": str(output_directory),
        "deck": manifest["deck"],
        "deck_sha256": manifest.get("deck_sha256"),
        "process_id": manifest.get("process_id"),
    }
    already_requested = False
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(request, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        request = _load_json_object(path, "stop request")
        _validate_stop_request(request, output_directory, manifest)
        already_requested = True

    exit_path = _ensure_exit_stop(output_directory, manifest)
    return {
        **request,
        "stop_request": str(path),
        "exit_file": str(exit_path),
        "already_requested": already_requested,
    }


def _ensure_exit_stop(output_directory: Path, manifest: dict[str, Any]) -> Path:
    exit_path = output_directory / f"{Path(manifest['deck']).stem}.exit"
    # BSAM creates this control file with its help text and a current value of
    # zero. Requesting a stop intentionally replaces that one known run-local
    # control record with value 2; the separate JSON request remains immutable.
    if not exit_path.is_file() or exit_path.read_bytes() != b"2\n":
        with exit_path.open("w", encoding="ascii", newline="\n") as stream:
            stream.write("2\n")
    return exit_path


def run_status(output_directory: Path) -> dict[str, Any]:
    """Read one run's durable manifest and derive current local status."""
    output_directory, manifest_path, manifest = _load_run_manifest(output_directory)
    process_id = manifest.get("process_id")
    process_running: bool | None = None
    if manifest["state"] in {"starting", "running"} and isinstance(process_id, int):
        process_running = _process_is_running(process_id)
    artifacts = sorted(
        str(path.relative_to(output_directory))
        for path in output_directory.iterdir()
        if path.is_file()
    )
    return {
        **manifest,
        "manifest": str(manifest_path),
        "process_running": process_running,
        "stop_request": _read_stop_request(output_directory, manifest),
        "artifacts": artifacts,
    }


def request_run_stop(output_directory: Path) -> dict[str, Any]:
    """Request BSAM's controlled file-based stop for one known active run."""
    output_directory, _, manifest = _load_run_manifest(output_directory)
    existing = _read_stop_request(output_directory, manifest)
    if existing is not None:
        if manifest["state"] == "terminal":
            return {
                **existing,
                "stop_request": str(_stop_request_path(output_directory)),
                "exit_file": str(output_directory / f"{Path(manifest['deck']).stem}.exit"),
                "already_requested": True,
                "state": "terminal",
            }
        result = _create_stop_request(output_directory, manifest, "user")
        result["state"] = manifest["state"]
        return result
    if manifest["state"] == "terminal":
        raise RunError("run is already terminal and has no stop request")
    result = _create_stop_request(output_directory, manifest, "user")
    result["state"] = manifest["state"]
    return result


def run_bsam(
    deck: Path,
    output_directory: Path,
    executable: Path,
    timeout_seconds: float = 3600.0,
    stop_grace_seconds: float = 30.0,
    workspace_root: Path | None = None,
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

    source_set = SourceSet.read(deck, workspace_root)
    document = source_set.documents[deck]
    errors = [item for item in source_set.diagnostics() if item.severity == "error"]
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
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "state": "starting",
        "classification": "pending",
        "deck": str(deck),
        "deck_sha256": document.sha256,
        "source_set_sha256": source_set.sha256,
        "source_files": [
            {"path": str(path), "sha256": source.sha256}
            for path, source in source_set.documents.items()
        ],
        "executable": str(executable),
        "executable_sha256": actual_executable_hash,
        "output_directory": str(output_directory),
        "command": command,
        "started_at": started.isoformat(),
        "timeout_seconds": timeout_seconds,
    }
    _write_manifest(manifest_path, manifest)

    timed_out = False
    stop_escalated = False
    exit_code: int | None = None
    process: subprocess.Popen[Any] | None = None
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
            timeout_deadline = (
                None if timeout_seconds <= 0 else time.monotonic() + timeout_seconds
            )
            stop_deadline: float | None = None
            while exit_code is None:
                exit_code = process.poll()
                if exit_code is not None:
                    break
                now = time.monotonic()
                stop_request = _read_stop_request(output_directory, manifest)
                if stop_request is None and timeout_deadline is not None and now >= timeout_deadline:
                    timed_out = True
                    stop_request = _create_stop_request(output_directory, manifest, "timeout")
                if stop_request is not None:
                    _ensure_exit_stop(output_directory, manifest)
                    if stop_deadline is None:
                        stop_deadline = now + max(0.0, stop_grace_seconds)
                    if now >= stop_deadline:
                        stop_escalated = True
                        process.terminate()
                        try:
                            exit_code = process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            exit_code = process.wait()
                        break
                try:
                    exit_code = process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    pass
    except (OSError, RunError) as exc:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait()
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
    stop_request = _read_stop_request(output_directory, manifest)
    classification = classify_run(
        exit_code,
        "\n".join(combined_parts),
        stop_requested=stop_request is not None,
    )
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
        "stop_escalated": stop_escalated,
        "stop_requested": stop_request is not None,
        "stop_reason": stop_request.get("reason") if stop_request else None,
        "stop_requested_at": stop_request.get("requested_at") if stop_request else None,
        "finished_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "artifacts": artifacts,
    })
    _write_manifest(manifest_path, manifest)
    return manifest
