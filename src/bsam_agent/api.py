"""Loopback-only JSON tool API for the deterministic BSAM Agent core."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .change import (
    apply_plan,
    plan_add_element,
    plan_add_node,
    plan_add_set_members,
    plan_create_set,
    plan_delete_node,
    plan_import_mesh,
    plan_parameter_change,
    review_plan,
    write_plan,
)
from .mesh import import_ele
from .registry import load_registry
from .run import request_run_stop, run_bsam, run_status
from .source_set import SourceSet
from .tool_contracts import (
    TOOL_CONTRACTS,
    contract_manifest,
    validate_arguments,
    validate_response,
)


API_VERSION = "0.1.0"
MAX_REQUEST_BYTES = 1_048_576


class ApiError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _RunJob:
    output_directory: Path
    source_set_sha256: str
    state: str = "accepted"
    classification: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class LocalAgentApi:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        if not self.workspace_root.is_dir():
            raise ValueError("API workspace root is not a directory")
        self._jobs: dict[Path, _RunJob] = {}
        self._jobs_lock = threading.Lock()

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(TOOL_CONTRACTS)

    def _path(self, value: Any, role: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ApiError("invalid_arguments", f"{role} must be a non-empty relative path")
        supplied = Path(value)
        if supplied.is_absolute():
            raise ApiError("path_not_allowed", f"{role} must be relative to the API workspace")
        resolved = (self.workspace_root / supplied).resolve()
        if not resolved.is_relative_to(self.workspace_root):
            raise ApiError("path_not_allowed", f"{role} escapes the API workspace")
        return resolved

    @staticmethod
    def _args(
        value: Any,
        required: set[str] = frozenset(),
        optional: set[str] = frozenset(),
    ) -> dict[str, Any]:
        # Canonical validation is performed by tool_contracts before dispatch.
        # These parameters remain only to keep each handler self-documenting.
        if not isinstance(value, dict):
            raise ApiError("invalid_arguments", "tool arguments must be a JSON object")
        return value

    def dispatch(self, tool: str, arguments: Any) -> dict[str, Any]:
        if tool not in self.tools:
            raise ApiError("unknown_tool", f"unknown tool: {tool}")
        try:
            checked = validate_arguments(tool, arguments)
            result = self._dispatch(tool, checked)
            return validate_response(tool, result)
        except ApiError:
            raise
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_arguments", str(exc)) from exc

    def _dispatch(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool == "get_capabilities":
            self._args(arguments)
            registry = load_registry()
            return {
                "api_version": API_VERSION,
                "registry_version": registry["registry_version"],
                "bsam": registry["target"],
                "capabilities": {
                    "top_level_blocks": [
                        {key: item[key] for key in ("id", "canonical", "coverage")}
                        for item in registry["top_level_blocks"]
                    ],
                    "cluster_commands": [
                        {key: item[key] for key in ("id", "canonical", "coverage")}
                        for item in registry["cluster_commands"]
                    ],
                    "nested_constructs": [
                        {key: item[key] for key in ("id", "canonical", "coverage")}
                        for item in registry["nested_constructs"]
                    ],
                },
                "tools": list(self.tools),
                "tool_contracts": contract_manifest(),
            }
        if tool in {"inspect_model", "validate_model"}:
            args = self._args(arguments, {"source"})
            inspection = SourceSet.read(
                self._path(args["source"], "source"), self.workspace_root
            ).inspection()
            if tool == "inspect_model":
                return inspection
            return {
                "source_set_sha256": inspection["source_set_sha256"],
                "diagnostics": inspection["diagnostics"],
                "summary": inspection["summary"],
            }
        if tool == "import_mesh":
            args = self._args(arguments, {"source"})
            return import_ele(self._path(args["source"], "source")).as_dict()
        if tool == "preview_parameter_change":
            args = self._args(
                arguments,
                {"source", "block", "construct", "parameter", "value", "plan_path"},
                {"occurrence"},
            )
            plan = plan_parameter_change(
                self._path(args["source"], "source"), str(args["block"]),
                str(args["construct"]), str(args["parameter"]), str(args["value"]),
                int(args.get("occurrence", 1)), self.workspace_root,
            )
            write_plan(plan, self._path(args["plan_path"], "plan_path"))
            return plan
        if tool == "preview_add_node":
            args = self._args(
                arguments, {"source", "cluster", "label", "x", "y", "z", "plan_path"}
            )
            plan = plan_add_node(
                self._path(args["source"], "source"), str(args["cluster"]), int(args["label"]),
                str(args["x"]), str(args["y"]), str(args["z"]), self.workspace_root,
            )
            write_plan(plan, self._path(args["plan_path"], "plan_path"))
            return plan
        if tool == "preview_add_element":
            args = self._args(
                arguments,
                {"source", "cluster", "label", "element_type", "node_labels", "plan_path"},
                {"elset"},
            )
            if not isinstance(args["node_labels"], list):
                raise ApiError("invalid_arguments", "node_labels must be an array")
            plan = plan_add_element(
                self._path(args["source"], "source"), str(args["cluster"]), int(args["label"]),
                str(args["element_type"]), [int(item) for item in args["node_labels"]],
                str(args["elset"]) if args.get("elset") is not None else None,
                self.workspace_root,
            )
            write_plan(plan, self._path(args["plan_path"], "plan_path"))
            return plan
        if tool == "preview_delete_node":
            args = self._args(arguments, {"source", "cluster", "label", "plan_path"})
            plan = plan_delete_node(
                self._path(args["source"], "source"), str(args["cluster"]),
                int(args["label"]), self.workspace_root,
            )
            write_plan(plan, self._path(args["plan_path"], "plan_path"))
            return plan
        if tool in {"preview_create_set", "preview_add_set_members"}:
            args = self._args(
                arguments, {"source", "cluster", "member_kind", "name", "members", "plan_path"}
            )
            if not isinstance(args["members"], list):
                raise ApiError("invalid_arguments", "members must be an array")
            planner = plan_create_set if tool == "preview_create_set" else plan_add_set_members
            plan = planner(
                self._path(args["source"], "source"), str(args["cluster"]),
                str(args["member_kind"]), str(args["name"]),
                [int(item) for item in args["members"]], self.workspace_root,
            )
            write_plan(plan, self._path(args["plan_path"], "plan_path"))
            return plan
        if tool == "preview_import_mesh":
            args = self._args(
                arguments, {"template", "mesh", "cluster", "plan_path"}
            )
            plan = plan_import_mesh(
                self._path(args["template"], "template"), self._path(args["mesh"], "mesh"),
                str(args["cluster"]), self.workspace_root,
            )
            write_plan(plan, self._path(args["plan_path"], "plan_path"))
            return plan
        if tool == "review_change":
            args = self._args(arguments, {"plan_path"})
            return review_plan(self._path(args["plan_path"], "plan_path"))
        if tool == "apply_change":
            args = self._args(arguments, {"plan_path", "destination", "confirm"}, {"audit_path"})
            if args["confirm"] is not True:
                raise ApiError("confirmation_required", "apply_change requires confirm=true")
            audit = self._path(args["audit_path"], "audit_path") if "audit_path" in args else None
            return apply_plan(
                self._path(args["plan_path"], "plan_path"),
                self._path(args["destination"], "destination"), audit,
            )
        if tool == "run_bsam":
            args = self._args(
                arguments, {"source", "output_dir", "executable", "confirm"},
                {"timeout", "stop_grace"},
            )
            if args["confirm"] is not True:
                raise ApiError("confirmation_required", "run_bsam requires confirm=true")
            return self._start_run(
                self._path(args["source"], "source"), self._path(args["output_dir"], "output_dir"),
                self._path(args["executable"], "executable"), float(args.get("timeout", 3600.0)),
                float(args.get("stop_grace", 30.0)),
            )
        if tool == "get_run_status":
            args = self._args(arguments, {"output_dir"})
            return self._run_status(self._path(args["output_dir"], "output_dir"))
        args = self._args(arguments, {"output_dir", "confirm"})
        if args["confirm"] is not True:
            raise ApiError("confirmation_required", "stop_run requires confirm=true")
        return self._stop_run(self._path(args["output_dir"], "output_dir"))

    def _start_run(
        self,
        source: Path,
        output_directory: Path,
        executable: Path,
        timeout: float,
        stop_grace: float,
    ) -> dict[str, Any]:
        source_set = SourceSet.read(source, self.workspace_root)
        if source_set.diagnostics() and any(
            item.severity == "error" for item in source_set.diagnostics()
        ):
            raise ApiError("preflight_failed", "source set has validation errors")
        with self._jobs_lock:
            if output_directory in self._jobs or output_directory.exists():
                raise ApiError("run_conflict", "run output directory is already reserved")
            job = _RunJob(output_directory, source_set.sha256)
            self._jobs[output_directory] = job

        def worker() -> None:
            job.state = "running"
            try:
                result = run_bsam(
                    source, output_directory, executable, timeout, stop_grace, self.workspace_root
                )
                job.result = result
                job.state = str(result.get("state", "terminal"))
                job.classification = str(result.get("classification", "unknown"))
            except (OSError, ValueError) as exc:
                job.error = str(exc)
                job.state = "terminal"
                job.classification = "failed"

        job.thread = threading.Thread(target=worker, name=f"bsam-run-{output_directory.name}", daemon=True)
        job.thread.start()
        return {
            "state": "accepted",
            "classification": "pending",
            "output_directory": str(output_directory),
            "source_set_sha256": source_set.sha256,
        }

    def _run_status(self, output_directory: Path) -> dict[str, Any]:
        manifest = output_directory / "run-manifest.json"
        if manifest.is_file():
            return run_status(output_directory)
        with self._jobs_lock:
            job = self._jobs.get(output_directory)
        if job is None:
            raise ApiError("run_not_found", "run is not known to this API process")
        if job.result is not None:
            return job.result
        result: dict[str, Any] = {
            "state": job.state,
            "classification": job.classification,
            "output_directory": str(output_directory),
            "source_set_sha256": job.source_set_sha256,
            "cancel_requested": job.cancel_requested.is_set(),
        }
        if job.error:
            result["error"] = job.error
        return result

    def _stop_run(self, output_directory: Path) -> dict[str, Any]:
        manifest = output_directory / "run-manifest.json"
        if manifest.is_file():
            return request_run_stop(output_directory)
        with self._jobs_lock:
            job = self._jobs.get(output_directory)
        if job is None:
            raise ApiError("run_not_found", "run is not known to this API process")
        job.cancel_requested.set()

        def deliver() -> None:
            while job.thread is not None and job.thread.is_alive():
                if (output_directory / "run-manifest.json").is_file():
                    try:
                        request_run_stop(output_directory)
                    except (OSError, ValueError):
                        pass
                    return
                time.sleep(0.02)

        threading.Thread(target=deliver, name=f"bsam-stop-{output_directory.name}", daemon=True).start()
        return {
            "state": "stop-requested",
            "classification": "pending",
            "output_directory": str(output_directory),
            "source_set_sha256": job.source_set_sha256,
        }


def build_server(api: LocalAgentApi, port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "BSAMAgent/0.1"

        def _send(self, status: int, value: dict[str, Any]) -> None:
            raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/v1/health":
                self._send(200, {"status": "ok", "api_version": API_VERSION})
            elif self.path == "/api/v1/capabilities":
                self._send(200, api.dispatch("get_capabilities", {}))
            else:
                self._send(404, {"error": {"code": "not_found", "message": "route not found"}})

        def do_POST(self) -> None:  # noqa: N802
            prefix = "/api/v1/tools/"
            if not self.path.startswith(prefix) or "/" in self.path[len(prefix):]:
                self._send(404, {"error": {"code": "not_found", "message": "route not found"}})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise ApiError("invalid_request", "request body size is invalid")
                if self.headers.get_content_type() != "application/json":
                    raise ApiError("invalid_request", "Content-Type must be application/json")
                arguments = json.loads(self.rfile.read(length))
                self._send(200, api.dispatch(self.path[len(prefix):], arguments))
            except ApiError as exc:
                self._send(400, {"error": {"code": exc.code, "message": str(exc)}})
            except (OSError, ValueError) as exc:
                self._send(400, {"error": {"code": "tool_error", "message": str(exc)}})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(workspace_root: Path, port: int = 8765) -> None:
    server = build_server(LocalAgentApi(workspace_root), port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
