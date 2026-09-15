"""Contained per-task storage and promotion for engineering artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


TASK_WORKSPACE_SCHEMA_VERSION = "0.3.0"
TASK_WORKSPACE_DIRECTORY = Path(".bsam-agent") / "tasks"
ARTIFACT_CATEGORIES = frozenset({"plans", "variants", "runs", "observations", "retries"})
WORKSPACE_STATES = frozenset({"active", "selected", "promoting", "promoted", "discarded"})
ARTIFACT_STATES = frozenset({"staged", "selected", "promoted", "discarded"})


class TaskWorkspaceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TaskWorkspace:
    """A workspace-owned task area whose only exit is explicit safe promotion."""

    def __init__(self, workspace_root: Path, task_id: str) -> None:
        self.workspace_root = workspace_root.resolve()
        if not self.workspace_root.is_dir():
            raise TaskWorkspaceError("workspace_not_found", "workspace root is not a directory")
        _validate_task_id(task_id)
        self.task_id = task_id
        _reject_symlink_components(self.workspace_root, TASK_WORKSPACE_DIRECTORY)
        tasks_root = (self.workspace_root / TASK_WORKSPACE_DIRECTORY).resolve()
        if not tasks_root.is_relative_to(self.workspace_root):
            raise TaskWorkspaceError("path_not_allowed", "task storage escapes the workspace")
        self.tasks_root = tasks_root
        self.root = tasks_root / task_id
        self.manifest_path = self.root / "task-workspace.json"

    @classmethod
    def create(
        cls,
        workspace_root: Path,
        task_id: str,
        *,
        objective_sha256: str,
        source_scope: list[str] | None = None,
    ) -> TaskWorkspace:
        workspace = cls(workspace_root, task_id)
        _validate_sha256(objective_sha256, "objective_sha256")
        normalized_scope = [
            workspace.workspace_relative_path(item, role="source scope")
            for item in (source_scope or [])
        ]
        if len(normalized_scope) != len(set(normalized_scope)) or len(normalized_scope) > 16:
            raise TaskWorkspaceError("invalid_manifest", "source scope is duplicated or too large")
        workspace.tasks_root.mkdir(parents=True, exist_ok=True)
        if workspace.tasks_root.is_symlink():
            raise TaskWorkspaceError("path_not_allowed", "task storage may not be a symlink")
        try:
            workspace.root.mkdir()
        except FileExistsError as exc:
            raise TaskWorkspaceError("task_workspace_exists", "task workspace already exists") from exc
        try:
            for category in sorted(ARTIFACT_CATEGORIES):
                (workspace.root / category).mkdir()
            timestamp = _timestamp()
            workspace._write_manifest({
                "schema_version": TASK_WORKSPACE_SCHEMA_VERSION,
                "task_id": task_id,
                "state": "active",
                "objective_sha256": objective_sha256,
                "source_scope": normalized_scope,
                "created_at": timestamp,
                "updated_at": timestamp,
                "selected_artifact_id": None,
                "artifacts": [],
                "promotions": [],
            })
        except Exception:
            # Creation owns this new empty tree. Remove only files/directories below its exact root.
            _remove_new_task_tree(workspace.root, workspace.tasks_root)
            raise
        return workspace

    @classmethod
    def open(cls, workspace_root: Path, task_id: str) -> TaskWorkspace:
        workspace = cls(workspace_root, task_id)
        workspace.manifest()
        return workspace

    def manifest(self) -> dict[str, Any]:
        if self.manifest_path.is_symlink():
            raise TaskWorkspaceError("path_not_allowed", "task manifest may not be a symlink")
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TaskWorkspaceError("task_workspace_not_found", "task manifest does not exist") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise TaskWorkspaceError("invalid_manifest", "task manifest is unreadable") from exc
        value = _migrate_manifest(value)
        _validate_manifest(value, expected_task_id=self.task_id)
        return deepcopy(value)

    def resolve(self, relative_path: str, *, must_exist: bool = False) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise TaskWorkspaceError("invalid_path", "task path must be a non-empty relative path")
        supplied = Path(relative_path)
        if supplied.is_absolute() or ".." in supplied.parts:
            raise TaskWorkspaceError("path_not_allowed", "task path must stay inside the task workspace")
        _reject_symlink_components(self.root, supplied)
        resolved = (self.root / supplied).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise TaskWorkspaceError("path_not_allowed", "task path escapes the task workspace")
        if must_exist and not resolved.exists():
            raise TaskWorkspaceError("artifact_not_found", "task artifact does not exist")
        return resolved

    def workspace_relative_path(self, value: str, *, role: str = "path") -> str:
        if not isinstance(value, str) or not value.strip():
            raise TaskWorkspaceError("invalid_path", f"{role} must be a non-empty path")
        supplied = Path(value)
        if supplied.is_absolute():
            lexical = Path(os.path.abspath(supplied))
            if not lexical.is_relative_to(self.workspace_root):
                raise TaskWorkspaceError("path_not_allowed", f"{role} escapes the workspace")
            relative = lexical.relative_to(self.workspace_root)
        else:
            if ".." in supplied.parts:
                raise TaskWorkspaceError("path_not_allowed", f"{role} escapes the workspace")
            relative = supplied
        _reject_symlink_components(self.workspace_root, relative)
        resolved = (self.workspace_root / relative).resolve()
        if not resolved.is_relative_to(self.workspace_root):
            raise TaskWorkspaceError("path_not_allowed", f"{role} escapes the workspace")
        return str(resolved.relative_to(self.workspace_root)).replace("\\", "/")

    def write_artifact(
        self,
        category: str,
        name: str,
        data: bytes,
        *,
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        if category not in ARTIFACT_CATEGORIES:
            raise TaskWorkspaceError("invalid_category", "task artifact category is invalid")
        if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
            raise TaskWorkspaceError("invalid_path", "artifact name must be one file name")
        if not isinstance(data, bytes):
            raise TaskWorkspaceError("invalid_artifact", "artifact data must be bytes")
        if not isinstance(media_type, str) or not media_type:
            raise TaskWorkspaceError("invalid_artifact", "artifact media type is invalid")
        manifest = self.manifest()
        if manifest["state"] not in {"active", "promoted"}:
            raise TaskWorkspaceError("invalid_state", "task workspace no longer accepts artifacts")
        path = self.resolve(f"{category}/{name}")
        try:
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as exc:
            raise TaskWorkspaceError("output_exists", "task artifact already exists") from exc
        try:
            return self.register_artifact(category, name, media_type=media_type)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def register_artifact(
        self,
        category: str,
        name: str,
        *,
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Register one regular file written by a deterministic task-local tool."""
        return self.register_artifact_set(
            category, name, [name], media_type=media_type,
        )

    def register_artifact_set(
        self,
        category: str,
        root_name: str,
        member_names: list[str],
        *,
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Register a root artifact and every file required to promote it intact."""
        if category not in ARTIFACT_CATEGORIES:
            raise TaskWorkspaceError("invalid_category", "task artifact category is invalid")
        if not isinstance(root_name, str) or Path(root_name).name != root_name or root_name in {".", ".."}:
            raise TaskWorkspaceError("invalid_path", "artifact root name must be one file name")
        if (
            not isinstance(member_names, list)
            or root_name not in member_names
            or len(member_names) != len(set(member_names))
            or not member_names
            or len(member_names) > 256
        ):
            raise TaskWorkspaceError("invalid_artifact", "artifact member list is invalid")
        if not isinstance(media_type, str) or not media_type:
            raise TaskWorkspaceError("invalid_artifact", "artifact media type is invalid")
        manifest = self.manifest()
        if manifest["state"] not in {"active", "promoted"}:
            raise TaskWorkspaceError("invalid_state", "task workspace no longer accepts artifacts")
        root_relative = f"{category}/{root_name}"
        members: list[dict[str, Any]] = []
        for member_name in member_names:
            member = Path(member_name)
            if member.is_absolute() or ".." in member.parts or not member_name.strip():
                raise TaskWorkspaceError("path_not_allowed", "artifact member escapes its category")
            path = self.resolve(f"{category}/{member_name}", must_exist=True)
            if not path.is_file() or path.is_symlink():
                raise TaskWorkspaceError("invalid_artifact", "task artifact member is not a regular file")
            data = path.read_bytes()
            members.append({
                "path": str(path.relative_to(self.root)).replace("\\", "/"),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        members.sort(key=lambda item: item["path"])
        if any(
            member["path"] in {
                existing_member["path"]
                for existing in manifest["artifacts"]
                for existing_member in existing["members"]
            }
            for member in members
        ):
            raise TaskWorkspaceError("artifact_exists", "task artifact is already registered")
        artifact = {
            "artifact_id": f"artifact-{len(manifest['artifacts']) + 1:04d}",
            "category": category,
            "path": root_relative,
            "media_type": media_type,
            "size": sum(item["size"] for item in members),
            "sha256": _artifact_set_digest(members),
            "members": members,
            "state": "staged",
            "created_at": _timestamp(),
        }
        manifest["artifacts"].append(artifact)
        manifest["updated_at"] = _timestamp()
        self._write_manifest(manifest)
        return deepcopy(artifact)

    def select_artifact(self, artifact_id: str) -> dict[str, Any]:
        manifest = self.manifest()
        if (
            manifest["state"] not in {"active", "promoted"}
            or manifest["selected_artifact_id"] is not None
        ):
            raise TaskWorkspaceError("invalid_state", "task workspace already has a selection")
        artifact = _artifact(manifest, artifact_id)
        if artifact["state"] != "staged":
            raise TaskWorkspaceError("invalid_state", "only a staged artifact can be selected")
        self._verify_artifact(artifact)
        artifact["state"] = "selected"
        manifest["selected_artifact_id"] = artifact_id
        manifest["state"] = "selected"
        manifest["updated_at"] = _timestamp()
        self._write_manifest(manifest)
        return deepcopy(artifact)

    def discard_artifact(self, artifact_id: str) -> dict[str, Any]:
        manifest = self.manifest()
        if manifest["state"] not in {"active", "selected", "promoted"}:
            raise TaskWorkspaceError("invalid_state", "task workspace cannot discard artifacts now")
        artifact = _artifact(manifest, artifact_id)
        if artifact["state"] not in {"staged", "selected"}:
            raise TaskWorkspaceError("invalid_state", "artifact cannot be discarded")
        paths = self._verify_artifact(artifact)
        for path in reversed(paths):
            path.unlink()
        artifact["state"] = "discarded"
        if manifest["selected_artifact_id"] == artifact_id:
            manifest["selected_artifact_id"] = None
            manifest["state"] = (
                "promoted" if any(
                    item["state"] == "completed" for item in manifest["promotions"]
                ) else "active"
            )
        manifest["updated_at"] = _timestamp()
        self._write_manifest(manifest)
        return deepcopy(artifact)

    def discard_workspace(self) -> dict[str, Any]:
        manifest = self.manifest()
        if manifest["state"] not in {"active", "selected"}:
            raise TaskWorkspaceError("invalid_state", "task workspace cannot be discarded now")
        discardable = [
            (artifact, self._verify_artifact(artifact))
            for artifact in manifest["artifacts"]
            if artifact["state"] in {"staged", "selected"}
        ]
        for artifact, paths in discardable:
            for path in reversed(paths):
                path.unlink()
            if artifact["state"] in {"staged", "selected"}:
                artifact["state"] = "discarded"
        manifest["selected_artifact_id"] = None
        manifest["state"] = "discarded"
        manifest["updated_at"] = _timestamp()
        self._write_manifest(manifest)
        return deepcopy(manifest)

    def promote_selected(self, destination: str, *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise TaskWorkspaceError("confirmation_required", "promotion requires confirmation")
        manifest = self.manifest()
        artifact_id = manifest["selected_artifact_id"]
        if manifest["state"] != "selected" or not isinstance(artifact_id, str):
            raise TaskWorkspaceError("invalid_state", "task workspace has no selected artifact")
        artifact = _artifact(manifest, artifact_id)
        sources = self._verify_artifact(artifact)
        source_root = self.resolve(artifact["path"], must_exist=True)
        destination_relative = self.workspace_relative_path(destination, role="promotion destination")
        target = (self.workspace_root / destination_relative).resolve()
        if target.is_relative_to(self.tasks_root):
            raise TaskWorkspaceError(
                "path_not_allowed", "final artifacts must be promoted outside task storage",
            )
        if not target.parent.is_dir():
            raise TaskWorkspaceError("destination_not_found", "promotion parent does not exist")
        _reject_symlink_components(self.workspace_root, target.relative_to(self.workspace_root))
        targets: list[tuple[Path, Path]] = []
        for source in sources:
            relative = source.relative_to(source_root.parent)
            if source == source_root:
                member_target = target
            elif source.name.startswith(source_root.name + "."):
                member_target = target.with_name(target.name + source.name[len(source_root.name):])
            else:
                member_target = (target.parent / relative).resolve()
            if not member_target.is_relative_to(self.workspace_root):
                raise TaskWorkspaceError("path_not_allowed", "promoted member escapes the workspace")
            targets.append((source, member_target))
        if len({target_path for _, target_path in targets}) != len(targets):
            raise TaskWorkspaceError("invalid_artifact", "artifact members map to duplicate outputs")
        reused_outputs: list[str] = []
        pending_targets: list[tuple[Path, Path]] = []
        conflicts: list[Path] = []
        for source, target_path in targets:
            if not target_path.exists():
                pending_targets.append((source, target_path))
                continue
            if (
                source != source_root
                and not source.name.startswith(source_root.name + ".")
                and target_path.is_file()
                and not target_path.is_symlink()
                and hashlib.sha256(target_path.read_bytes()).hexdigest()
                == hashlib.sha256(source.read_bytes()).hexdigest()
            ):
                reused_outputs.append(
                    str(target_path.relative_to(self.workspace_root)).replace("\\", "/")
                )
            else:
                conflicts.append(target_path)
        if conflicts:
            raise TaskWorkspaceError("output_exists", "promotion destination already exists")

        promotion = {
            "promotion_id": f"promotion-{len(manifest['promotions']) + 1:04d}",
            "artifact_id": artifact_id,
            "destination": destination_relative,
            "sha256": artifact["sha256"],
            "state": "pending",
            "outputs": [
                str(target_path.relative_to(self.workspace_root)).replace("\\", "/")
                for _, target_path in targets
            ],
            "reused_outputs": reused_outputs,
            "created_at": _timestamp(),
            "completed_at": None,
            "error": None,
        }
        manifest["promotions"].append(promotion)
        manifest["state"] = "promoting"
        manifest["updated_at"] = _timestamp()
        self._write_manifest(manifest)

        temporaries: list[Path] = []
        created_targets: list[Path] = []
        created_directories: list[Path] = []
        try:
            for source, target_path in pending_targets:
                missing_parents: list[Path] = []
                parent = target_path.parent
                while not parent.exists() and parent.is_relative_to(self.workspace_root):
                    missing_parents.append(parent)
                    parent = parent.parent
                _reject_symlink_components(
                    self.workspace_root, parent.relative_to(self.workspace_root),
                )
                for new_directory in reversed(missing_parents):
                    new_directory.mkdir()
                    created_directories.append(new_directory)
                temporary = target_path.with_name(
                    f".{target_path.name}.promote-{uuid4().hex}.tmp"
                )
                temporaries.append(temporary)
                with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
                    while chunk := input_stream.read(1024 * 1024):
                        output_stream.write(chunk)
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
                os.link(temporary, target_path)
                created_targets.append(target_path)
                temporary.unlink()
        except Exception as exc:
            for temporary in temporaries:
                temporary.unlink(missing_ok=True)
            for created_target in reversed(created_targets):
                created_target.unlink(missing_ok=True)
            for created_directory in reversed(created_directories):
                try:
                    created_directory.rmdir()
                except OSError:
                    pass
            promotion["state"] = "failed"
            promotion["error"] = "output_exists" if isinstance(exc, FileExistsError) else "promotion_failed"
            manifest["state"] = "selected"
            manifest["updated_at"] = _timestamp()
            self._write_manifest(manifest)
            if isinstance(exc, FileExistsError):
                raise TaskWorkspaceError("output_exists", "promotion destination already exists") from exc
            raise TaskWorkspaceError("promotion_failed", str(exc)) from exc

        promotion["state"] = "completed"
        promotion["completed_at"] = _timestamp()
        artifact["state"] = "promoted"
        manifest["selected_artifact_id"] = None
        manifest["state"] = "promoted"
        manifest["updated_at"] = promotion["completed_at"]
        self._write_manifest(manifest)
        return deepcopy(promotion)

    def _verify_artifact(self, artifact: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        actual_members: list[dict[str, Any]] = []
        for member in artifact["members"]:
            path = self.resolve(member["path"], must_exist=True)
            if not path.is_file() or path.is_symlink():
                raise TaskWorkspaceError("invalid_artifact", "task artifact is not a regular file")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if len(data) != member["size"] or digest != member["sha256"]:
                raise TaskWorkspaceError("stale_artifact", "task artifact digest no longer matches")
            paths.append(path)
            actual_members.append({"path": member["path"], "size": len(data), "sha256": digest})
        if (
            sum(item["size"] for item in actual_members) != artifact["size"]
            or _artifact_set_digest(actual_members) != artifact["sha256"]
        ):
            raise TaskWorkspaceError("stale_artifact", "task artifact set digest no longer matches")
        return paths

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        _validate_manifest(manifest, expected_task_id=self.task_id)
        payload = json.dumps(
            manifest, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False,
        ).encode("utf-8") + b"\n"
        temporary = self.root / f".task-workspace-{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.manifest_path)
        finally:
            temporary.unlink(missing_ok=True)


def _artifact(manifest: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in manifest["artifacts"] if item["artifact_id"] == artifact_id]
    if len(matches) != 1:
        raise TaskWorkspaceError("artifact_not_found", "task artifact ID was not found")
    return matches[0]


def _validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", task_id) is None:
        raise TaskWorkspaceError("invalid_task_id", "task ID is invalid")


def _validate_sha256(value: Any, role: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise TaskWorkspaceError("invalid_manifest", f"{role} is not a lowercase SHA-256")


def _validate_manifest(value: Any, *, expected_task_id: str) -> None:
    fields = {
        "schema_version", "task_id", "state", "objective_sha256", "source_scope",
        "created_at", "updated_at", "selected_artifact_id", "artifacts", "promotions",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise TaskWorkspaceError("invalid_manifest", "task manifest fields are invalid")
    if value["schema_version"] != TASK_WORKSPACE_SCHEMA_VERSION or value["task_id"] != expected_task_id:
        raise TaskWorkspaceError("invalid_manifest", "task manifest identity is invalid")
    if value["state"] not in WORKSPACE_STATES:
        raise TaskWorkspaceError("invalid_manifest", "task workspace state is invalid")
    _validate_sha256(value["objective_sha256"], "objective_sha256")
    if (
        not isinstance(value["source_scope"], list)
        or not all(isinstance(item, str) and item for item in value["source_scope"])
        or len(value["source_scope"]) != len(set(value["source_scope"]))
        or len(value["source_scope"]) > 16
    ):
        raise TaskWorkspaceError("invalid_manifest", "task source scope is invalid")
    for name in ("created_at", "updated_at"):
        if not isinstance(value[name], str) or not value[name]:
            raise TaskWorkspaceError("invalid_manifest", f"task {name} is invalid")
    if value["selected_artifact_id"] is not None and not isinstance(value["selected_artifact_id"], str):
        raise TaskWorkspaceError("invalid_manifest", "selected artifact ID is invalid")
    if not isinstance(value["artifacts"], list) or not isinstance(value["promotions"], list):
        raise TaskWorkspaceError("invalid_manifest", "task artifact lists are invalid")
    artifact_ids: set[str] = set()
    selected_ids: list[str] = []
    for artifact in value["artifacts"]:
        required = {
            "artifact_id", "category", "path", "media_type", "size", "sha256",
            "members", "state", "created_at",
        }
        if not isinstance(artifact, dict) or set(artifact) != required:
            raise TaskWorkspaceError("invalid_manifest", "artifact fields are invalid")
        artifact_id = artifact["artifact_id"]
        if not isinstance(artifact_id, str) or artifact_id in artifact_ids:
            raise TaskWorkspaceError("invalid_manifest", "artifact ID is invalid")
        artifact_ids.add(artifact_id)
        if artifact["category"] not in ARTIFACT_CATEGORIES or artifact["state"] not in ARTIFACT_STATES:
            raise TaskWorkspaceError("invalid_manifest", "artifact category or state is invalid")
        if artifact["state"] == "selected":
            selected_ids.append(artifact_id)
        if (
            not isinstance(artifact["path"], str)
            or not artifact["path"].startswith(f"{artifact['category']}/")
            or Path(artifact["path"]).is_absolute()
            or ".." in Path(artifact["path"]).parts
            or not isinstance(artifact["media_type"], str)
            or not isinstance(artifact["size"], int)
            or isinstance(artifact["size"], bool)
            or artifact["size"] < 0
            or not isinstance(artifact["created_at"], str)
        ):
            raise TaskWorkspaceError("invalid_manifest", "artifact metadata is invalid")
        _validate_sha256(artifact["sha256"], "artifact sha256")
        members = artifact["members"]
        if not isinstance(members, list) or not members or len(members) > 256:
            raise TaskWorkspaceError("invalid_manifest", "artifact members are invalid")
        member_paths: set[str] = set()
        for member in members:
            if not isinstance(member, dict) or set(member) != {"path", "size", "sha256"}:
                raise TaskWorkspaceError("invalid_manifest", "artifact member fields are invalid")
            member_path = member["path"]
            if (
                not isinstance(member_path, str)
                or not member_path.startswith(f"{artifact['category']}/")
                or Path(member_path).is_absolute()
                or ".." in Path(member_path).parts
                or member_path in member_paths
                or not isinstance(member["size"], int)
                or isinstance(member["size"], bool)
                or member["size"] < 0
            ):
                raise TaskWorkspaceError("invalid_manifest", "artifact member metadata is invalid")
            member_paths.add(member_path)
            _validate_sha256(member["sha256"], "artifact member sha256")
        if artifact["path"] not in member_paths or (
            artifact["size"] != sum(item["size"] for item in members)
            or artifact["sha256"] != _artifact_set_digest(members)
        ):
            raise TaskWorkspaceError("invalid_manifest", "artifact set digest is inconsistent")
    if selected_ids != ([value["selected_artifact_id"]] if value["selected_artifact_id"] else []):
        raise TaskWorkspaceError("invalid_manifest", "selected artifact state is inconsistent")
    selection_expected = value["state"] in {"selected", "promoting"}
    if selection_expected != (value["selected_artifact_id"] is not None):
        raise TaskWorkspaceError("invalid_manifest", "task selection lifecycle is inconsistent")
    promotion_ids: set[str] = set()
    for promotion in value["promotions"]:
        required = {
            "promotion_id", "artifact_id", "destination", "sha256", "state",
            "outputs", "reused_outputs", "created_at", "completed_at", "error",
        }
        if not isinstance(promotion, dict) or set(promotion) != required:
            raise TaskWorkspaceError("invalid_manifest", "promotion fields are invalid")
        promotion_id = promotion["promotion_id"]
        if not isinstance(promotion_id, str) or promotion_id in promotion_ids:
            raise TaskWorkspaceError("invalid_manifest", "promotion ID is invalid")
        promotion_ids.add(promotion_id)
        if promotion["artifact_id"] not in artifact_ids or promotion["state"] not in {"pending", "completed", "failed"}:
            raise TaskWorkspaceError("invalid_manifest", "promotion reference or state is invalid")
        if (
            not isinstance(promotion["destination"], str)
            or not promotion["destination"]
            or Path(promotion["destination"]).is_absolute()
            or ".." in Path(promotion["destination"]).parts
        ):
            raise TaskWorkspaceError("invalid_manifest", "promotion destination is invalid")
        if (
            not isinstance(promotion["outputs"], list)
            or not promotion["outputs"]
            or len(promotion["outputs"]) != len(set(promotion["outputs"]))
            or not all(
                isinstance(item, str)
                and item
                and not Path(item).is_absolute()
                and ".." not in Path(item).parts
                for item in promotion["outputs"]
            )
        ):
            raise TaskWorkspaceError("invalid_manifest", "promotion outputs are invalid")
        if (
            not isinstance(promotion["reused_outputs"], list)
            or len(promotion["reused_outputs"]) != len(set(promotion["reused_outputs"]))
            or not set(promotion["reused_outputs"]).issubset(set(promotion["outputs"]))
        ):
            raise TaskWorkspaceError("invalid_manifest", "reused promotion outputs are invalid")
        _validate_sha256(promotion["sha256"], "promotion sha256")
        if (
            not isinstance(promotion["created_at"], str)
            or not promotion["created_at"]
            or promotion["completed_at"] is not None
            and not isinstance(promotion["completed_at"], str)
            or promotion["error"] is not None
            and not isinstance(promotion["error"], str)
        ):
            raise TaskWorkspaceError("invalid_manifest", "promotion metadata is invalid")
        if (
            promotion["state"] == "pending"
            and (promotion["completed_at"] is not None or promotion["error"] is not None)
            or promotion["state"] == "completed"
            and (promotion["completed_at"] is None or promotion["error"] is not None)
            or promotion["state"] == "failed"
            and (promotion["completed_at"] is not None or not promotion["error"])
        ):
            raise TaskWorkspaceError("invalid_manifest", "promotion lifecycle is inconsistent")
        linked_artifact = next(
            item for item in value["artifacts"]
            if item["artifact_id"] == promotion["artifact_id"]
        )
        if promotion["sha256"] != linked_artifact["sha256"]:
            raise TaskWorkspaceError("invalid_manifest", "promotion digest is inconsistent")
    if value["state"] == "promoting" and not any(
        item["state"] == "pending" for item in value["promotions"]
    ):
        raise TaskWorkspaceError("invalid_manifest", "promoting workspace lacks a pending promotion")
    if value["state"] == "promoted" and (
        sum(item["state"] == "promoted" for item in value["artifacts"]) != 1
        or sum(item["state"] == "completed" for item in value["promotions"]) != 1
    ):
        raise TaskWorkspaceError("invalid_manifest", "promoted workspace lifecycle is inconsistent")
    if value["state"] == "discarded" and any(
        item["state"] != "discarded" for item in value["artifacts"]
    ):
        raise TaskWorkspaceError("invalid_manifest", "discarded workspace retains live artifacts")


def _migrate_manifest(value: Any) -> Any:
    if not isinstance(value, dict) or value.get("schema_version") not in {"0.1.0", "0.2.0"}:
        return value
    migrated = deepcopy(value)
    migrated["schema_version"] = TASK_WORKSPACE_SCHEMA_VERSION
    if value.get("schema_version") == "0.1.0":
        for artifact in migrated.get("artifacts", []):
            if isinstance(artifact, dict):
                artifact["members"] = [{
                    "path": artifact.get("path"),
                    "size": artifact.get("size"),
                    "sha256": artifact.get("sha256"),
                }]
    for promotion in migrated.get("promotions", []):
        if isinstance(promotion, dict):
            if value.get("schema_version") == "0.1.0":
                promotion["outputs"] = [promotion.get("destination")]
            promotion["reused_outputs"] = []
    return migrated


def _artifact_set_digest(members: list[dict[str, Any]]) -> str:
    ordered = sorted(
        ({key: item[key] for key in ("path", "size", "sha256")} for item in members),
        key=lambda item: item["path"],
    )
    if len(ordered) == 1:
        return str(ordered[0]["sha256"])
    payload = json.dumps(ordered, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _reject_symlink_components(root: Path, relative: Path) -> None:
    current = root
    if current.is_symlink():
        raise TaskWorkspaceError("path_not_allowed", "workspace boundary may not be a symlink")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise TaskWorkspaceError("path_not_allowed", "symlinks are not allowed in task paths")


def _remove_new_task_tree(root: Path, tasks_root: Path) -> None:
    resolved_root = root.resolve()
    if not resolved_root.is_relative_to(tasks_root.resolve()) or resolved_root == tasks_root.resolve():
        return
    if not root.exists() or root.is_symlink():
        return
    for child in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if child.is_symlink() or child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    root.rmdir()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
