"""Revision-bound minimal patches for existing BSAM key/value parameters."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .document import SourceDocument, SourceLine, diagnostic_summary
from .mesh import MeshModel, import_ele, render_bsam_commands
from .registry import load_registry
from .source_set import SourceSet


PLAN_SCHEMA_VERSION = "1.10.0"
SUPPORTED_PLAN_SCHEMA_VERSIONS = {
    "1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", "1.6.0",
    "1.7.0", "1.8.0", "1.9.0", PLAN_SCHEMA_VERSION,
}
AUDIT_SCHEMA_VERSION = "1.1.0"


class ChangeError(ValueError):
    """Raised when a requested change cannot be planned or safely applied."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _plan_digest(plan_without_digest: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(plan_without_digest)).hexdigest().upper()


def _patched_bytes(document: SourceDocument, patch: dict[str, Any]) -> bytes:
    start, end = int(patch["start"]), int(patch["end"])
    expected = patch["old"].encode("latin-1")
    if start < 0 or end < start or end > len(document.raw):
        raise ChangeError("planned source span is outside the source document")
    if document.raw[start:end] != expected:
        raise ChangeError("planned source span no longer contains the expected value")
    return document.raw[:start] + patch["new"].encode("latin-1") + document.raw[end:]


def _patched_bytes_many(document: SourceDocument, patches: list[dict[str, Any]]) -> bytes:
    """Apply non-overlapping revision-bound patches without offset drift."""
    if not patches:
        raise ChangeError("change plan must contain at least one patch")
    ordered = sorted(patches, key=lambda item: (int(item["start"]), int(item["end"])))
    prior_end = -1
    for patch in ordered:
        start, end = int(patch["start"]), int(patch["end"])
        if start < prior_end:
            raise ChangeError("planned source patches overlap")
        if start < 0 or end < start or end > len(document.raw):
            raise ChangeError("planned source span is outside the source document")
        if document.raw[start:end] != patch["old"].encode("latin-1"):
            raise ChangeError("planned source span no longer contains the expected value")
        prior_end = end
    updated = document.raw
    for patch in reversed(ordered):
        start, end = int(patch["start"]), int(patch["end"])
        updated = updated[:start] + patch["new"].encode("latin-1") + updated[end:]
    return updated


def _patched_source_files(
    source_set: SourceSet, patches: list[dict[str, Any]],
) -> dict[Path, bytes]:
    grouped: dict[Path, list[dict[str, Any]]] = {}
    for patch in patches:
        source = Path(str(patch.get("source", source_set.root))).resolve()
        if source not in source_set.documents:
            raise ChangeError("planned patch source is not in the bound source set")
        grouped.setdefault(source, []).append(patch)
    return {
        source: _patched_bytes_many(source_set.documents[source], items)
        for source, items in grouped.items()
    }


def _source_diff(source: Path, before: bytes, after: bytes) -> str:
    before_lines = before.decode("latin-1").splitlines()
    after_lines = after.decode("latin-1").splitlines()
    return "\n".join(unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{source.name}",
        tofile=f"b/{source.name}",
        lineterm="",
    )) + "\n"


def _validation_result(source_set: SourceSet, replacements: dict[Path, bytes]) -> dict[str, Any]:
    semantic = source_set.semantic_index(replacements)
    diagnostics = source_set.diagnostics(semantic, replacements)
    return {
        "diagnostics": [item.as_dict() for item in diagnostics],
        "semantic_summary": semantic.as_dict()["summary"],
        "summary": diagnostic_summary(diagnostics),
    }


def _validate_raw_value(value: str) -> None:
    if any(character in value for character in "\r\n\x00,"):
        raise ChangeError(
            "replacement value must be a single non-comma record value",
            "invalid_parameter_value",
        )
    if not value.strip():
        raise ChangeError(
            "replacement value must not be empty", "invalid_parameter_value",
        )


def _semantic_source_path(source_set: SourceSet, source: str) -> Path:
    return (
        source_set.root
        if source == "<root>"
        else (source_set.input_directory / source).resolve()
    )


def _cluster_source_boundary(
    source_set: SourceSet, cluster: str,
) -> tuple[Path, SourceDocument, SourceLine]:
    if not cluster.strip():
        raise ChangeError("cluster name must not be empty")
    key = f"cluster:{cluster.casefold()}"
    matches = [
        item for item in source_set.semantic_index().entities
        if item.kind == "cluster" and item.key == key
    ]
    if not matches:
        raise ChangeError(f"cluster {cluster} was not found in the source set")
    if len(matches) > 1:
        raise ChangeError(f"cluster name {cluster} is ambiguous in the source set")
    entity = matches[0]
    source_path = _semantic_source_path(source_set, entity.location.source)
    document = source_set.documents.get(source_path)
    if document is None:
        raise ChangeError("cluster source location is not in the bound source set")
    boundary = next(
        (
            item for item in document.lines[entity.location.line:]
            if item.text.lstrip().upper()[:5] in {"*NAME", "*TYPE", "*STOP"}
        ),
        None,
    )
    if boundary is not None and boundary.text.lstrip().upper()[:5] == "*NAME":
        raise ChangeError(f"cluster {cluster} has no boundary before the next *NAME")
    if boundary is None:
        if source_path == source_set.root:
            raise ChangeError(f"cluster {cluster} has no following *TYPE or *STOP boundary")
        boundary = SourceLine(
            number=len(document.lines) + 1,
            start=len(document.raw),
            end=len(document.raw),
            content=b"",
            newline=b"",
        )
    return source_path, document, boundary


def _record_prefix(document: SourceDocument, boundary: SourceLine, newline: bytes) -> bytes:
    if boundary.start == 0 or document.raw[:boundary.start].endswith((b"\r", b"\n")):
        return b""
    return newline


def _node_patch(
    source_set: SourceSet,
    cluster: str,
    label: int,
    coordinates: tuple[str, str, str],
) -> dict[str, Any]:
    if label <= 0:
        raise ChangeError("node label must be positive")
    for value in coordinates:
        _validate_raw_value(value)
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ChangeError(f"node coordinate {value!r} is not a real number") from exc
        if not math.isfinite(parsed):
            raise ChangeError(f"node coordinate {value!r} must be finite")

    key = f"cluster:{cluster.casefold()}/node:{label}"
    if any(item.key == key for item in source_set.semantic_index().entities):
        raise ChangeError(f"node {label} already exists in cluster {cluster}")

    source_path, document, boundary = _cluster_source_boundary(source_set, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    record = (
        _record_prefix(document, boundary, newline) + b"*NODE" + newline
        + f"{label},{coordinates[0]},{coordinates[1]},{coordinates[2]}".encode("latin-1")
        + newline
    )
    return {
        "source": str(source_path),
        "start": boundary.start,
        "end": boundary.start,
        "line": boundary.number,
        "old": "",
        "new": record.decode("latin-1"),
    }


def plan_add_node(
    source: Path,
    cluster: str,
    label: int,
    x: str,
    y: str,
    z: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source = source.resolve()
    source_set = SourceSet.read(source, workspace_root)
    document = source_set.documents[source]
    coordinates = (x, y, z)
    patch = _node_patch(source_set, cluster, label, coordinates)
    model_path = f"CLUSTERS[{cluster.casefold()}].nodes[{label}]"
    preview = f"line {patch['line']}: add node {label} to cluster {cluster} at ({x}, {y}, {z})"
    return _typed_plan(
        source_set, patch, "add-node",
        {"cluster": cluster, "label": label, "coordinates": list(coordinates)},
        model_path, preview, "create",
    )


def _typed_plan(
    source_set: SourceSet,
    patch: dict[str, Any],
    operation: str,
    selector: dict[str, Any],
    model_path: str,
    preview: str,
    change_operation: str,
    inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source = source_set.root
    root_document = source_set.documents[source]
    patch_source = Path(str(patch.get("source", source))).resolve()
    document = source_set.documents.get(patch_source)
    if document is None:
        raise ChangeError("planned patch source is not in the bound source set")
    updated = _patched_bytes(document, patch)
    replacements = {patch_source: updated}
    root_raw = replacements.get(source, root_document.raw)
    updated_document = SourceDocument.from_bytes(root_raw, str(source))
    validation = _validation_result(source_set, replacements)
    if validation["summary"]["errors"]:
        messages = "; ".join(
            item["message"] for item in validation["diagnostics"] if item["severity"] == "error"
        )
        raise ChangeError(f"planned source set failed dependency validation: {messages}")
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source),
        "workspace_root": str(source_set.workspace_root),
        "base_sha256": root_document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_sha256": updated_document.sha256,
        "proposed_source_set_sha256": source_set.digest_with(replacements),
        "operation": operation,
        "selector": selector,
        "patch": patch,
        "changed_model_paths": [model_path],
        "affected_files": [str(patch_source)],
        "changes": [{"operation": change_operation, "target": model_path, "summary": preview}],
        "source_diff": _source_diff(patch_source, document.raw, updated),
        "validation": validation,
        "preview": preview,
    }
    if inputs:
        plan["inputs"] = inputs
    digest = _plan_digest(plan)
    plan["plan_digest"] = digest
    plan["plan_id"] = digest[:16]
    return plan


def _element_patch(
    source_set: SourceSet,
    cluster: str,
    label: int,
    element_type: str,
    node_labels: tuple[int, ...],
    elset: str | None,
) -> dict[str, Any]:
    if label <= 0:
        raise ChangeError("element label must be positive")
    requested_type = element_type.upper()
    semantic = source_set.semantic_index()
    prefix = f"cluster:{cluster.casefold()}/"
    element_key = f"{prefix}element:{label}"
    if any(item.key == element_key for item in semantic.entities):
        raise ChangeError(f"element {label} already exists in cluster {cluster}")
    peers = [
        item for item in semantic.entities
        if item.kind == "element" and item.key.startswith(prefix)
        and str(item.attributes.get("element_type", "")).upper() == requested_type
    ]
    if not peers:
        raise ChangeError(
            f"element type {requested_type} is not established in cluster {cluster}; "
            "adding a new topology is blocked"
        )
    widths = {len(item.attributes.get("connectivity", [])) for item in peers}
    if len(widths) != 1 or len(node_labels) not in widths:
        expected = ", ".join(str(item) for item in sorted(widths))
        raise ChangeError(f"{requested_type} connectivity must contain {expected} node labels")
    if any(label_value <= 0 for label_value in node_labels):
        raise ChangeError("connectivity node labels must be positive")
    entity_keys = {item.key for item in semantic.entities}
    missing = [value for value in node_labels if f"{prefix}node:{value}" not in entity_keys]
    if missing:
        raise ChangeError(f"connectivity references missing nodes: {', '.join(map(str, missing))}")
    if elset is not None:
        _validate_raw_value(elset)

    source_path, document, boundary = _cluster_source_boundary(source_set, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    options = f"*ELEMENT,TYPE={requested_type}"
    if elset:
        options += f",ELSET={elset}"
    record = (
        _record_prefix(document, boundary, newline) + options.encode("latin-1") + newline
        + (str(label) + "," + ",".join(map(str, node_labels))).encode("ascii") + newline
    )
    return {
        "source": str(source_path),
        "start": boundary.start,
        "end": boundary.start,
        "line": boundary.number,
        "old": "",
        "new": record.decode("latin-1"),
    }


def plan_add_element(
    source: Path,
    cluster: str,
    label: int,
    element_type: str,
    node_labels: list[int],
    elset: str | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    nodes = tuple(node_labels)
    patch = _element_patch(source_set, cluster, label, element_type, nodes, elset)
    model_path = f"CLUSTERS[{cluster.casefold()}].elements[{label}]"
    preview = f"line {patch['line']}: add {element_type.upper()} element {label} to cluster {cluster}"
    return _typed_plan(
        source_set, patch, "add-element",
        {
            "cluster": cluster,
            "label": label,
            "element_type": element_type.upper(),
            "node_labels": list(nodes),
            "elset": elset,
        },
        model_path, preview, "create",
    )


def _delete_mesh_entity_patch(
    source_set: SourceSet, cluster: str, label: int, entity_kind: str,
) -> dict[str, Any]:
    if entity_kind not in {"node", "element"}:
        raise ChangeError("mesh entity deletion supports nodes or elements")
    key = f"cluster:{cluster.casefold()}/{entity_kind}:{label}"
    semantic = source_set.semantic_index()
    matches = [item for item in semantic.entities if item.key == key]
    if not matches:
        raise ChangeError(f"{entity_kind} {label} was not found in cluster {cluster}")
    if len(matches) > 1:
        raise ChangeError(f"{entity_kind} {label} is ambiguous in cluster {cluster}")
    entity = matches[0]
    if entity.attributes.get("generated_by"):
        raise ChangeError(
            f"generated {entity_kind} {label} cannot be deleted as one explicit record"
        )
    dependents = [
        item for item in semantic.references
        if item.target_key == key
        or (item.source_entity_id == entity.id and item.kind == "member-of")
    ]
    if dependents:
        kinds = ", ".join(sorted({item.kind for item in dependents}))
        raise ChangeError(
            f"{entity_kind} {label} has dependent references ({kinds}); deletion is blocked"
        )
    source_path = _semantic_source_path(source_set, entity.location.source)
    document = source_set.documents.get(source_path)
    if document is None:
        raise ChangeError(f"{entity_kind} source location is not in the bound source set")
    line = document.lines[entity.location.line - 1]
    return {
        "source": str(source_path),
        "start": line.start,
        "end": line.end,
        "line": line.number,
        "old": document.raw[line.start:line.end].decode("latin-1"),
        "new": "",
    }


def _delete_node_patch(source_set: SourceSet, cluster: str, label: int) -> dict[str, Any]:
    return _delete_mesh_entity_patch(source_set, cluster, label, "node")


def plan_delete_node(
    source: Path,
    cluster: str,
    label: int,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch = _delete_node_patch(source_set, cluster, label)
    model_path = f"CLUSTERS[{cluster.casefold()}].nodes[{label}]"
    preview = f"line {patch['line']}: delete unreferenced node {label} from cluster {cluster}"
    return _typed_plan(
        source_set, patch, "delete-node", {"cluster": cluster, "label": label},
        model_path, preview, "delete",
    )


def plan_delete_element(
    source: Path,
    cluster: str,
    label: int,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch = _delete_mesh_entity_patch(source_set, cluster, label, "element")
    model_path = f"CLUSTERS[{cluster.casefold()}].elements[{label}]"
    preview = f"line {patch['line']}: delete unreferenced element {label} from cluster {cluster}"
    return _typed_plan(
        source_set, patch, "delete-element", {"cluster": cluster, "label": label},
        model_path, preview, "delete",
    )


def _set_patch(
    source_set: SourceSet,
    cluster: str,
    member_kind: str,
    name: str,
    members: tuple[int, ...],
    require_new: bool,
) -> dict[str, Any]:
    if member_kind not in {"node", "element"}:
        raise ChangeError("set kind must be node or element")
    _validate_raw_value(name)
    if not members or any(item <= 0 for item in members):
        raise ChangeError("set members must be a non-empty list of positive labels")
    if len(set(members)) != len(members):
        raise ChangeError("set member list contains duplicates")
    semantic = source_set.semantic_index()
    prefix = f"cluster:{cluster.casefold()}/"
    set_kind = f"{member_kind}-set"
    set_key = f"{prefix}{set_kind}:{name.casefold()}"
    existing = [item for item in semantic.entities if item.key == set_key]
    if require_new and existing:
        raise ChangeError(f"{set_kind} {name} already exists in cluster {cluster}")
    if not require_new and not existing:
        raise ChangeError(f"{set_kind} {name} was not found in cluster {cluster}")
    entity_keys = {item.key for item in semantic.entities}
    missing = [item for item in members if f"{prefix}{member_kind}:{item}" not in entity_keys]
    if missing:
        raise ChangeError(f"set references missing {member_kind}s: {', '.join(map(str, missing))}")
    if not require_new:
        current = {
            int(reference.target_key.rsplit(":", 1)[1])
            for entity in existing
            for reference in semantic.references
            if reference.source_entity_id == entity.id and reference.kind == "contains"
        }
        duplicates = sorted(current.intersection(members))
        if duplicates:
            raise ChangeError(f"set already contains members: {', '.join(map(str, duplicates))}")

    source_path, document, boundary = _cluster_source_boundary(source_set, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    command = "*NSET,NSET=" if member_kind == "node" else "*ELSET,ELSET="
    record = (
        _record_prefix(document, boundary, newline) + (command + name).encode("latin-1") + newline
        + ",".join(map(str, members)).encode("ascii") + newline
    )
    return {
        "source": str(source_path),
        "start": boundary.start,
        "end": boundary.start,
        "line": boundary.number,
        "old": "",
        "new": record.decode("latin-1"),
    }


def plan_create_set(
    source: Path,
    cluster: str,
    member_kind: str,
    name: str,
    members: list[int],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    values = tuple(members)
    patch = _set_patch(source_set, cluster, member_kind, name, values, True)
    set_kind = f"{member_kind}-sets"
    model_path = f"CLUSTERS[{cluster.casefold()}].{set_kind}[{name.casefold()}]"
    preview = f"line {patch['line']}: create {member_kind} set {name} with {len(values)} members"
    return _typed_plan(
        source_set, patch, "create-set",
        {"cluster": cluster, "member_kind": member_kind, "name": name, "members": list(values)},
        model_path, preview, "create",
    )


def plan_add_set_members(
    source: Path,
    cluster: str,
    member_kind: str,
    name: str,
    members: list[int],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    values = tuple(members)
    patch = _set_patch(source_set, cluster, member_kind, name, values, False)
    set_kind = f"{member_kind}-sets"
    model_path = f"CLUSTERS[{cluster.casefold()}].{set_kind}[{name.casefold()}].members"
    preview = f"line {patch['line']}: add {len(values)} members to {member_kind} set {name}"
    return _typed_plan(
        source_set, patch, "add-set-members",
        {"cluster": cluster, "member_kind": member_kind, "name": name, "members": list(values)},
        model_path, preview, "modify",
    )


def _remove_set_member_patch(
    source_set: SourceSet,
    cluster: str,
    member_kind: str,
    name: str,
    member: int,
) -> dict[str, Any]:
    if member_kind not in {"node", "element"}:
        raise ChangeError("set kind must be node or element")
    if member <= 0:
        raise ChangeError("set member must be a positive label")
    semantic = source_set.semantic_index()
    prefix = f"cluster:{cluster.casefold()}/"
    set_kind = f"{member_kind}-set"
    set_key = f"{prefix}{set_kind}:{name.casefold()}"
    entities = [item for item in semantic.entities if item.key == set_key]
    if not entities:
        raise ChangeError(f"{set_kind} {name} was not found in cluster {cluster}")
    entity_ids = {item.id for item in entities}
    membership = [
        item for item in semantic.references
        if item.source_entity_id in entity_ids and item.kind == "contains"
    ]
    target = f"{prefix}{member_kind}:{member}"
    matches = [item for item in membership if item.target_key == target]
    if not matches:
        raise ChangeError(f"{set_kind} {name} does not contain member {member}")
    if len(matches) > 1:
        raise ChangeError(f"member {member} is ambiguous in {set_kind} {name}")
    if len({item.target_key for item in membership}) <= 1:
        raise ChangeError(f"removing member {member} would leave {set_kind} {name} empty")
    location = matches[0].location
    source_path = _semantic_source_path(source_set, location.source)
    document = source_set.documents.get(source_path)
    if document is None:
        raise ChangeError("set member source location is not in the bound source set")
    line = document.lines[location.line - 1]
    code = line.text.split("#", 1)[0]
    tokens = list(re.finditer(rf"(?<!\d){member}(?!\d)", code))
    if len(tokens) != 1:
        raise ChangeError(
            f"member {member} no longer resolves to one exact token on line {line.number}"
        )
    token = tokens[0]
    fields = [item.strip() for item in code.split(",") if item.strip()]
    if len(fields) == 1:
        start, end = line.start, line.end
    elif not code[:token.start()].strip():
        local_end = token.end()
        while local_end < len(code) and code[local_end].isspace():
            local_end += 1
        if local_end >= len(code) or code[local_end] != ",":
            raise ChangeError("first set member is not followed by a comma; removal is blocked")
        local_end += 1
        while local_end < len(code) and code[local_end].isspace():
            local_end += 1
        start, end = line.start + token.start(), line.start + local_end
    else:
        local_start = token.start()
        while local_start > 0 and code[local_start - 1].isspace():
            local_start -= 1
        if local_start <= 0 or code[local_start - 1] != ",":
            raise ChangeError("set member is not preceded by a comma; removal is blocked")
        start, end = line.start + local_start - 1, line.start + token.end()
    return {
        "source": str(source_path),
        "start": start,
        "end": end,
        "line": line.number,
        "old": document.raw[start:end].decode("latin-1"),
        "new": "",
    }


def plan_remove_set_member(
    source: Path,
    cluster: str,
    member_kind: str,
    name: str,
    member: int,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch = _remove_set_member_patch(
        source_set, cluster, member_kind, name, member,
    )
    set_kind = f"{member_kind}-sets"
    model_path = (
        f"CLUSTERS[{cluster.casefold()}].{set_kind}[{name.casefold()}].members[{member}]"
    )
    preview = f"line {patch['line']}: remove member {member} from {member_kind} set {name}"
    return _typed_plan(
        source_set, patch, "remove-set-member",
        {
            "cluster": cluster, "member_kind": member_kind,
            "name": name, "member": member,
        },
        model_path, preview, "delete",
    )


def _delete_set_patch(
    source_set: SourceSet, cluster: str, member_kind: str, name: str,
) -> dict[str, Any]:
    if member_kind not in {"node", "element"}:
        raise ChangeError("set kind must be node or element")
    semantic = source_set.semantic_index()
    set_kind = f"{member_kind}-set"
    key = f"cluster:{cluster.casefold()}/{set_kind}:{name.casefold()}"
    matches = [item for item in semantic.entities if item.key == key]
    if not matches:
        raise ChangeError(f"{set_kind} {name} was not found in cluster {cluster}")
    if len(matches) != 1:
        raise ChangeError(f"{set_kind} {name} has multiple definitions; deletion is blocked")
    entity = matches[0]
    if entity.attributes.get("mode") != "explicit":
        raise ChangeError(f"only one explicit {set_kind} definition can be deleted")
    dependents = [
        item for item in semantic.references
        if item.target_key == key and item.source_entity_id != entity.id
    ]
    if dependents:
        kinds = ", ".join(sorted({item.kind for item in dependents}))
        raise ChangeError(f"{set_kind} {name} has dependent references ({kinds}); deletion is blocked")

    source_path = _semantic_source_path(source_set, entity.location.source)
    document = source_set.documents.get(source_path)
    if document is None:
        raise ChangeError("set source location is not in the bound source set")
    command_index = entity.location.line - 1
    following = document.lines[command_index + 1:]
    next_command = next(
        (
            offset for offset, line in enumerate(following, start=command_index + 1)
            if line.stripped.startswith("*") and not line.stripped.startswith("**")
        ),
        len(document.lines),
    )
    span_lines = document.lines[command_index:next_command]
    if any(line.stripped.startswith("**") for line in span_lines):
        raise ChangeError("commented set definitions require manual review before deletion")
    active_lines = [line for line in span_lines if line.stripped]
    if len(active_lines) < 2:
        raise ChangeError("explicit set has no removable member records")
    start, end = active_lines[0].start, active_lines[-1].end
    return {
        "source": str(source_path),
        "start": start,
        "end": end,
        "line": active_lines[0].number,
        "old": document.raw[start:end].decode("latin-1"),
        "new": "",
    }


def plan_delete_set(
    source: Path,
    cluster: str,
    member_kind: str,
    name: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch = _delete_set_patch(source_set, cluster, member_kind, name)
    set_kind = f"{member_kind}-sets"
    model_path = f"CLUSTERS[{cluster.casefold()}].{set_kind}[{name.casefold()}]"
    preview = f"line {patch['line']}: delete unreferenced {member_kind} set {name}"
    return _typed_plan(
        source_set, patch, "delete-set",
        {"cluster": cluster, "member_kind": member_kind, "name": name},
        model_path, preview, "delete",
    )


def _nodal_record_target_patch(
    source_set: SourceSet,
    capability: str,
    cluster: str,
    current_target: str,
    new_target: str,
    occurrence: int | None,
) -> tuple[dict[str, Any], int, str]:
    _validate_raw_value(new_target)
    mapping = {
        "command.boundary": "nodal-boundary",
        "command.load": "nodal-load",
    }
    entity_kind = mapping.get(capability)
    if entity_kind is None:
        raise ChangeError(f"nodal target editing is unavailable for {capability}")
    semantic = source_set.semantic_index()
    candidates = [
        item for item in semantic.entities
        if item.kind == entity_kind
        and str(item.attributes.get("cluster", "")).casefold() == cluster.casefold()
        and str(item.attributes.get("target", "")).casefold() == current_target.casefold()
    ]
    if not candidates:
        raise ChangeError(
            f"target {current_target} was not found in {capability} for cluster {cluster}"
        )
    if occurrence is None:
        if len(candidates) != 1:
            raise ChangeError(
                f"target {current_target} is ambiguous in {capability} for cluster {cluster}; "
                "specify occurrence"
            )
        selected, selected_occurrence = candidates[0], 1
    else:
        if occurrence < 1 or occurrence > len(candidates):
            raise ChangeError(
                f"occurrence {occurrence} is outside the {len(candidates)} matching records"
            )
        selected, selected_occurrence = candidates[occurrence - 1], occurrence

    format_name = str(selected.attributes.get("format", "ABAQ"))
    node_only = capability == "command.boundary" and format_name == "LIST"
    set_only = capability == "command.boundary" and format_name == "POLY"
    prefix = f"cluster:{cluster.casefold()}/"
    node_key = f"{prefix}node:{new_target.casefold()}"
    set_key = f"{prefix}node-set:{new_target.casefold()}"
    keys = {item.key for item in semantic.entities}
    if set_only:
        if set_key not in keys:
            raise ChangeError("POLYNOMIAL boundary targets must be an existing node set")
    elif node_only:
        if not new_target.isdigit() or node_key not in keys:
            raise ChangeError("LIST boundary targets must be an existing numeric node")
    elif set_key not in keys and (not new_target.isdigit() or node_key not in keys):
        raise ChangeError("new target must be an existing node set or numeric node")

    source_path = _semantic_source_path(source_set, selected.location.source)
    document = source_set.documents.get(source_path)
    if document is None:
        raise ChangeError("nodal record source location is not in the bound source set")
    line = document.lines[selected.location.line - 1]
    match = re.match(r"\s*(?P<target>[^,\s]+)", line.text)
    if match is None or match.group("target").casefold() != current_target.casefold():
        raise ChangeError("nodal record target no longer resolves to one exact leading token")
    start = line.start + match.start("target")
    end = line.start + match.end("target")
    return ({
        "source": str(source_path),
        "start": start,
        "end": end,
        "line": line.number,
        "old": document.raw[start:end].decode("latin-1"),
        "new": new_target,
    }, selected_occurrence, entity_kind)


def plan_retarget_nodal_record(
    source: Path,
    capability: str,
    cluster: str,
    current_target: str,
    new_target: str,
    occurrence: int | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch, selected_occurrence, entity_kind = _nodal_record_target_patch(
        source_set, capability, cluster, current_target, new_target, occurrence,
    )
    model_path = (
        f"CLUSTERS[{cluster.casefold()}].{entity_kind}[{selected_occurrence}].target"
    )
    preview = (
        f"line {patch['line']}: retarget {capability} record from "
        f"{current_target} to {new_target}"
    )
    return _typed_plan(
        source_set, patch, "retarget-nodal-record",
        {
            "capability": capability, "cluster": cluster,
            "current_target": current_target, "new_target": new_target,
            "occurrence": selected_occurrence,
        },
        model_path, preview, "modify",
    )


def _section_target_patch(
    source_set: SourceSet,
    cluster: str,
    current_target: str,
    new_target: str,
    occurrence: int | None,
) -> tuple[dict[str, Any], int]:
    _validate_raw_value(new_target)
    semantic = source_set.semantic_index()
    candidates = [
        item for item in semantic.entities
        if item.kind == "section"
        and str(item.attributes.get("cluster", "")).casefold() == cluster.casefold()
        and item.name.casefold() == current_target.casefold()
    ]
    if not candidates:
        raise ChangeError(
            f"section target {current_target} was not found in cluster {cluster}"
        )
    if occurrence is None:
        if len(candidates) != 1:
            raise ChangeError(
                f"section target {current_target} is ambiguous in cluster {cluster}; "
                "specify occurrence"
            )
        selected, selected_occurrence = candidates[0], 1
    else:
        if occurrence < 1 or occurrence > len(candidates):
            raise ChangeError(
                f"occurrence {occurrence} is outside the {len(candidates)} matching sections"
            )
        selected, selected_occurrence = candidates[occurrence - 1], occurrence
    new_key = f"cluster:{cluster.casefold()}/element-set:{new_target.casefold()}"
    if not any(item.key == new_key for item in semantic.entities):
        raise ChangeError("new section target must be an existing element set")

    source_path = _semantic_source_path(source_set, selected.location.source)
    document = source_set.documents.get(source_path)
    if document is None:
        raise ChangeError("section source location is not in the bound source set")
    line = document.lines[selected.location.line - 1]
    spans = _value_spans(line, "ELSET")
    if len(spans) != 1:
        raise ChangeError("section ELSET no longer resolves to one exact command value")
    start, end = spans[0]
    old = document.raw[start:end].decode("latin-1")
    if old.casefold() != current_target.casefold():
        raise ChangeError(f"section ELSET does not reference {current_target}")
    return ({
        "source": str(source_path),
        "start": start,
        "end": end,
        "line": line.number,
        "old": old,
        "new": new_target,
    }, selected_occurrence)


def plan_retarget_section(
    source: Path,
    cluster: str,
    current_target: str,
    new_target: str,
    occurrence: int | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch, selected_occurrence = _section_target_patch(
        source_set, cluster, current_target, new_target, occurrence,
    )
    model_path = f"CLUSTERS[{cluster.casefold()}].sections[{selected_occurrence}].elset"
    preview = (
        f"line {patch['line']}: retarget section from {current_target} to {new_target}"
    )
    return _typed_plan(
        source_set, patch, "retarget-section",
        {
            "cluster": cluster, "current_target": current_target,
            "new_target": new_target, "occurrence": selected_occurrence,
        },
        model_path, preview, "modify",
    )


def _coordinate_operation_target_patch(
    source_set: SourceSet,
    capability: str,
    cluster: str,
    current_target: str,
    new_target: str,
    occurrence: int | None,
) -> tuple[dict[str, Any], int, str]:
    operation_name = {"command.shift": "shift", "command.scale": "scale"}.get(capability)
    if operation_name is None:
        raise ChangeError(f"coordinate target editing is unavailable for {capability}")
    _validate_raw_value(new_target)
    semantic = source_set.semantic_index()
    candidates = [
        item for item in semantic.entities
        if item.kind == "coordinate-operation"
        and str(item.attributes.get("cluster", "")).casefold() == cluster.casefold()
        and str(item.attributes.get("operation", "")).casefold() == operation_name
        and str(item.attributes.get("target", "")).casefold() == current_target.casefold()
    ]
    if not candidates:
        raise ChangeError(
            f"{operation_name} target {current_target} was not found in cluster {cluster}"
        )
    if occurrence is None:
        if len(candidates) != 1:
            raise ChangeError(
                f"{operation_name} target {current_target} is ambiguous in cluster {cluster}; "
                "specify occurrence"
            )
        selected, selected_occurrence = candidates[0], 1
    else:
        if occurrence < 1 or occurrence > len(candidates):
            raise ChangeError(
                f"occurrence {occurrence} is outside the {len(candidates)} matching operations"
            )
        selected, selected_occurrence = candidates[occurrence - 1], occurrence
    if current_target.casefold() == "all":
        raise ChangeError("ALL-target coordinate operations have no NSET value to retarget")
    new_key = f"cluster:{cluster.casefold()}/node-set:{new_target.casefold()}"
    if not any(item.key == new_key for item in semantic.entities):
        raise ChangeError("new coordinate-operation target must be an existing node set")
    source_path = _semantic_source_path(source_set, selected.location.source)
    document = source_set.documents.get(source_path)
    if document is None:
        raise ChangeError("coordinate-operation source is not in the bound source set")
    line = document.lines[selected.location.line - 1]
    spans = _value_spans(line, "NSET")
    if len(spans) != 1:
        raise ChangeError("coordinate-operation NSET no longer resolves to one exact value")
    start, end = spans[0]
    old = document.raw[start:end].decode("latin-1")
    if old.casefold() != current_target.casefold():
        raise ChangeError(f"coordinate-operation NSET does not reference {current_target}")
    return ({
        "source": str(source_path), "start": start, "end": end,
        "line": line.number, "old": old, "new": new_target,
    }, selected_occurrence, operation_name)


def plan_retarget_coordinate_operation(
    source: Path,
    capability: str,
    cluster: str,
    current_target: str,
    new_target: str,
    occurrence: int | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch, selected_occurrence, operation_name = _coordinate_operation_target_patch(
        source_set, capability, cluster, current_target, new_target, occurrence,
    )
    model_path = (
        f"CLUSTERS[{cluster.casefold()}].coordinate-operations"
        f"[{operation_name}:{selected_occurrence}].nset"
    )
    preview = (
        f"line {patch['line']}: retarget {operation_name} from "
        f"{current_target} to {new_target}"
    )
    return _typed_plan(
        source_set, patch, "retarget-coordinate-operation",
        {
            "capability": capability, "cluster": cluster,
            "current_target": current_target, "new_target": new_target,
            "occurrence": selected_occurrence,
        },
        model_path, preview, "modify",
    )


def _mesh_import_patch(
    source_set: SourceSet,
    cluster: str,
    mesh_path: Path,
    expected_sha256: str | None = None,
) -> tuple[dict[str, Any], MeshModel]:
    mesh_path = mesh_path.resolve()
    if not mesh_path.is_relative_to(source_set.workspace_root):
        raise ChangeError("mesh input is outside the configured workspace root")
    mesh = import_ele(mesh_path)
    if expected_sha256 is not None and mesh.sha256 != expected_sha256:
        raise ChangeError("mesh input changed after planning; create a new import plan")
    prefix = f"cluster:{cluster.casefold()}/"
    existing = [
        item for item in source_set.semantic_index().entities
        if item.key.startswith(prefix) and item.kind in {
            "node", "element", "node-set", "element-set", "section"
        }
    ]
    if existing:
        raise ChangeError(f"target cluster {cluster} is not empty")
    source_path, document, boundary = _cluster_source_boundary(source_set, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    rendered = _record_prefix(document, boundary, newline) + render_bsam_commands(mesh, newline)
    return ({
        "source": str(source_path),
        "start": boundary.start,
        "end": boundary.start,
        "line": boundary.number,
        "old": "",
        "new": rendered.decode("latin-1"),
    }, mesh)


def plan_import_mesh(
    template: Path,
    mesh_path: Path,
    cluster: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_set = SourceSet.read(template.resolve(), workspace_root)
    patch, mesh = _mesh_import_patch(source_set, cluster, mesh_path)
    model_path = f"CLUSTERS[{cluster.casefold()}].mesh"
    summary = mesh.as_dict()["summary"]
    preview = (
        f"line {patch['line']}: import {summary['nodes']} nodes and "
        f"{summary['elements']} elements into cluster {cluster}"
    )
    mesh_input = {
        "role": "mesh",
        "format": "abaqus-style-ele",
        "path": mesh.source,
        "sha256": mesh.sha256,
    }
    return _typed_plan(
        source_set, patch, "import-mesh",
        {"cluster": cluster, "mesh": mesh_input},
        model_path, preview, "create", [mesh_input],
    )


def _construct_record(block_name: str, construct_name: str) -> dict[str, Any]:
    registry = load_registry()
    block_records = {item["canonical"].upper(): item for item in registry["top_level_blocks"]}
    block_by_name = {name: item["id"] for name, item in block_records.items()}
    block_id = block_by_name.get(block_name.upper())
    if block_id is None:
        raise ChangeError(
            f"unknown registered block: {block_name}", "unknown_parameter_context",
        )
    requested = construct_name.upper()
    if not requested.startswith("*"):
        requested = "*" + requested
    if block_id == "block.solver" and construct_name.casefold() in {
        "solver", "block.solver",
    }:
        return {
            **block_records["SOLVER"],
            "canonical": "SOLVER",
            "match_prefix": "*type",
        }
    matches = [
        item for item in registry["nested_constructs"]
        if item["parent_block_id"] == block_id and (
            item["canonical"].upper() == requested
            or item["id"].casefold() == construct_name.casefold()
        )
    ]
    if not matches:
        raise ChangeError(
            f"unknown registered construct {construct_name} in {block_name}",
            "unknown_parameter_context",
        )
    return matches[0]


def _parameter_definition(
    construct: dict[str, Any], parameter: str,
) -> dict[str, Any]:
    parameters = {item["name"].lower(): item for item in construct["parameters"]}
    definition = parameters.get(parameter.lower())
    if definition is None:
        raise ChangeError(
            f"parameter {parameter} is not registered for {construct['canonical']}; untyped edits are blocked",
            "unknown_parameter",
        )
    return definition


def _validate_replacement(construct: dict[str, Any], parameter: str, value: str) -> None:
    definition = _parameter_definition(construct, parameter)
    value_type = definition["value_type"].lower()
    try:
        if value_type == "flag":
            if value.casefold() not in {"true", "false"}:
                raise ValueError
            parsed = 0
        elif "integer" in value_type:
            parsed: int | float = int(value)
        elif "real" in value_type:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError
        else:
            parsed = 0
    except ValueError as exc:
        raise ChangeError(
            f"value {value!r} is not a valid {definition['value_type']}",
            "invalid_parameter_value",
        ) from exc
    if value_type.startswith("positive-") and parsed <= 0:
        raise ChangeError(
            f"value for {parameter} must be positive", "invalid_parameter_value",
        )
    if value_type.startswith("nonnegative-") and parsed < 0:
        raise ChangeError(
            f"value for {parameter} must be nonnegative", "invalid_parameter_value",
        )
    allowed = definition.get("allowed_values")
    if allowed is not None and value.lower() not in {str(item).lower() for item in allowed}:
        raise ChangeError(
            f"value for {parameter} must be one of: {', '.join(map(str, allowed))}",
            "invalid_parameter_value",
        )


def _find_construct_lines(
    document: SourceDocument,
    block_name: str,
    construct: dict[str, Any],
    occurrence: int,
) -> tuple[int, int]:
    if occurrence < 1:
        raise ChangeError(
            "occurrence must be at least 1", "invalid_parameter_occurrence",
        )
    blocks = [item for item in document.blocks() if item["name"].upper() == block_name.upper()]
    if not blocks:
        raise ChangeError(
            f"block {block_name} was not found", "missing_parameter_context",
        )
    prefix = construct["match_prefix"].lower()
    matches: list[tuple[int, int]] = []
    for block in blocks:
        final = block["end_line"] or len(document.lines)
        line_number = block["start_line"] + 1
        while line_number <= final:
            stripped = document.lines[line_number - 1].stripped
            if stripped.lower().startswith(prefix):
                end = line_number + 1
                while end <= final:
                    candidate = document.lines[end - 1].stripped
                    if candidate.startswith("*") and not candidate.startswith("**"):
                        break
                    if candidate.upper().startswith("END "):
                        break
                    end += 1
                matches.append((line_number, end - 1))
            line_number += 1
    if occurrence > len(matches):
        raise ChangeError(
            f"construct {construct['canonical']} occurrence {occurrence} was not found; found {len(matches)}",
            "missing_parameter_context",
        )
    return matches[occurrence - 1]


def _value_spans(line: SourceLine, parameter: str) -> list[tuple[int, int]]:
    text = line.text
    searchable = text.split("#", 1)[0]
    lower = searchable.lower()
    needle = parameter.lower()
    cursor = 0
    spans: list[tuple[int, int]] = []
    while True:
        found = lower.find(needle, cursor)
        if found < 0:
            return spans
        before_ok = found == 0 or not (lower[found - 1].isalnum() or lower[found - 1] == "_")
        after_name = found + len(needle)
        after_ok = after_name == len(lower) or not (lower[after_name].isalnum() or lower[after_name] == "_")
        equals = after_name
        while equals < len(searchable) and searchable[equals].isspace():
            equals += 1
        if before_ok and after_ok and equals < len(searchable) and searchable[equals] == "=":
            value_start = equals + 1
            while value_start < len(searchable) and searchable[value_start].isspace():
                value_start += 1
            value_end = value_start
            while value_end < len(searchable) and searchable[value_end] != ",":
                value_end += 1
            while value_end > value_start and searchable[value_end - 1].isspace():
                value_end -= 1
            if value_end == value_start:
                raise ChangeError(
                    f"parameter {parameter} has an empty value on line {line.number}",
                    "invalid_parameter_value",
                )
            spans.append((line.start + value_start, line.start + value_end))
            cursor = value_end
            continue
        cursor = found + 1


def _select_parameter_candidate(
    candidates: list[tuple[SourceLine, int, int]],
    definition: dict[str, Any],
    parameter: str,
    parameter_occurrence: int | None,
) -> tuple[tuple[SourceLine, int, int], int]:
    """Select one registered repeated value without guessing among duplicates."""
    if parameter_occurrence is None:
        if len(candidates) > 1:
            lines = ", ".join(str(item[0].number) for item in candidates)
            raise ChangeError(
                f"parameter {parameter} is ambiguous in the selected construct "
                f"(lines {lines}); provide parameter_occurrence",
                "ambiguous_parameter",
            )
        return candidates[0], 1
    if parameter_occurrence < 1:
        raise ChangeError(
            "parameter_occurrence must be at least 1", "invalid_parameter_occurrence",
        )
    if definition.get("cardinality", "single") != "repeated-last-wins":
        raise ChangeError(
            f"parameter {parameter} is not registered as repeated",
            "parameter_edit_unsupported",
        )
    if parameter_occurrence > len(candidates):
        raise ChangeError(
            f"parameter {parameter} occurrence {parameter_occurrence} was not found; "
            f"found {len(candidates)}",
            "missing_parameter",
        )
    return candidates[parameter_occurrence - 1], parameter_occurrence


def _flag_spans(
    line: SourceLine, construct: dict[str, Any], parameter: str,
) -> list[tuple[int, int]]:
    searchable = line.text.split("#", 1)[0]
    result: list[tuple[int, int]] = []
    definition = _parameter_definition(construct, parameter)
    for match in re.finditer(r"[^\s,=]+", searchable):
        token = match.group(0).casefold()
        candidates = [
            item for item in construct.get("parameters", [])
            if str(item.get("name", "")).casefold() == token
            or (
                len(token) >= 4
                and str(item.get("name", "")).casefold()[:4] == token[:4]
            )
        ]
        if len(candidates) == 1 and candidates[0] is definition:
            result.append((line.start + match.start(), line.start + match.end()))
    return result


def _flag_parameter_plan(
    source_set: SourceSet,
    construct: dict[str, Any],
    block: str,
    parameter: str,
    value: str,
    occurrence: int,
    command_line_number: int,
) -> dict[str, Any]:
    source = source_set.root
    document = source_set.documents[source]
    definition = _parameter_definition(construct, parameter)
    line = document.lines[command_line_number - 1]
    spans = _flag_spans(line, construct, parameter)
    if len(spans) > 1:
        raise ChangeError(
            f"flag {parameter} is ambiguous on line {line.number}",
            "ambiguous_parameter",
        )
    enabled = value.casefold() == "true"
    if enabled == bool(spans):
        raise ChangeError("requested value is identical to the existing value")
    edit_operation = "insert" if enabled else "remove"
    if definition.get("edit_operations", {}).get(edit_operation) != "verified":
        raise ChangeError(
            f"{edit_operation} of flag parameter {parameter} is not verified",
            "parameter_edit_unsupported",
        )
    if enabled:
        code = line.text.split("#", 1)[0]
        local = len(code.rstrip())
        start = end = line.start + local
        old = ""
        new = f",{definition['name']}"
        operation = "insert-optional-flag"
        summary = f"line {line.number}: enable {definition['name']}"
        change_operation = "create"
    else:
        start, end = spans[0]
        local_start = start - line.start
        while local_start > 0 and line.text[local_start - 1].isspace():
            local_start -= 1
        if local_start > 0 and line.text[local_start - 1] == ",":
            local_start -= 1
        elif local_start == start - line.start:
            raise ChangeError(
                f"flag {parameter} is not separately delimited; removal is blocked",
                "parameter_edit_unsupported",
            )
        start = line.start + local_start
        old = document.raw[start:end].decode("latin-1")
        new = ""
        operation = "remove-optional-flag"
        summary = f"line {line.number}: disable {definition['name']}"
        change_operation = "delete"
    patch = {
        "source": str(source),
        "start": start,
        "end": end,
        "line": line.number,
        "old": old,
        "new": new,
    }
    model_path = f"{block.upper()}.{construct['canonical']}[{occurrence}].{parameter}"
    return _typed_plan(
        source_set,
        patch,
        operation,
        {
            "block": block.upper(),
            "construct": construct["canonical"],
            "construct_occurrence": occurrence,
            "parameter": parameter,
            "requested_value": value.casefold(),
        },
        model_path,
        summary,
        change_operation,
    )


def _boundary_condition_rename_patches(
    source_set: SourceSet, old_name: str, new_name: str
) -> list[dict[str, Any]]:
    _validate_raw_value(old_name)
    _validate_raw_value(new_name)
    if any(character.isspace() for character in old_name + new_name):
        raise ChangeError("boundary-condition names must not contain whitespace")
    if old_name.casefold() == new_name.casefold():
        raise ChangeError("new boundary-condition name must differ from the current name")
    semantic = source_set.semantic_index()
    old_key = _key_for_change("boundary-condition", old_name)
    new_key = _key_for_change("boundary-condition", new_name)
    definitions = [item for item in semantic.entities if item.key == old_key]
    if len(definitions) != 1:
        raise ChangeError(
            f"boundary condition {old_name} must resolve to one exact root definition"
        )
    if any(item.key == new_key for item in semantic.entities):
        raise ChangeError(f"boundary condition {new_name} already exists")
    document = source_set.documents[source_set.root]
    locations = [(definitions[0].location, "name")]
    locations.extend(
        (reference.location, "change")
        for reference in semantic.references
        if reference.target_key == old_key and reference.kind == "changes-boundary-condition"
    )
    patches: list[dict[str, Any]] = []
    for location, parameter in locations:
        if location.source != "<root>":
            raise ChangeError("boundary-condition rename currently supports root-deck records only")
        line = document.lines[location.line - 1]
        spans = _value_spans(line, parameter)
        if len(spans) != 1:
            raise ChangeError(
                f"{parameter} on line {line.number} no longer resolves to one exact value"
            )
        start, end = spans[0]
        old = document.raw[start:end].decode("latin-1")
        if old.casefold() != old_name.casefold():
            raise ChangeError(
                f"{parameter} on line {line.number} does not reference {old_name}"
            )
        patches.append({
            "start": start,
            "end": end,
            "line": line.number,
            "old": old,
            "new": new_name,
        })
    return patches


def _key_for_change(kind: str, name: str) -> str:
    return f"{kind}:{name.casefold()}"


def plan_rename_boundary_condition(
    source: Path,
    old_name: str,
    new_name: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Plan one boundary-condition rename and all loading-sequence dependents."""
    source = source.resolve()
    source_set = SourceSet.read(source, workspace_root)
    document = source_set.documents[source]
    patches = _boundary_condition_rename_patches(source_set, old_name, new_name)
    updated = _patched_bytes_many(document, patches)
    updated_document = SourceDocument.from_bytes(updated, str(source))
    validation = _validation_result(source_set, {source: updated})
    if validation["summary"]["errors"]:
        messages = "; ".join(
            item["message"] for item in validation["diagnostics"] if item["severity"] == "error"
        )
        raise ChangeError(f"planned boundary-condition rename failed validation: {messages}")
    model_paths = [
        f"BOUNDARY.boundary-conditions[{old_name}]",
        f"BOUNDARY.loading-sequence.change[{old_name}]",
    ]
    dependent_count = len(patches) - 1
    preview = (
        f"rename boundary condition {old_name} -> {new_name} and update "
        f"{dependent_count} loading-sequence reference(s)"
    )
    changes = [
        {"operation": "rename", "target": model_paths[0], "summary": f"{old_name} -> {new_name}"},
        {"operation": "retarget", "target": model_paths[1], "summary": f"updated {dependent_count} dependent reference(s)"},
    ]
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source),
        "workspace_root": str(source_set.workspace_root),
        "base_sha256": document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_sha256": updated_document.sha256,
        "proposed_source_set_sha256": source_set.digest_with({source: updated}),
        "operation": "rename-boundary-condition",
        "selector": {"old_name": old_name, "new_name": new_name},
        "patches": patches,
        "changed_model_paths": model_paths,
        "affected_files": [str(source)],
        "changes": changes,
        "source_diff": _source_diff(source, document.raw, updated),
        "validation": validation,
        "preview": preview,
    }
    digest = _plan_digest(plan)
    plan["plan_digest"] = digest
    plan["plan_id"] = digest[:16]
    return plan


def plan_rename_entity(
    source: Path,
    capability: str,
    entity_name: str,
    new_name: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Dispatch a generic rename only through an explicitly verified capability adapter."""
    registry = load_registry()
    matches = [
        item for item in [
            *registry["top_level_blocks"],
            *registry["cluster_commands"],
            *registry["nested_constructs"],
        ]
        if item["id"].casefold() == capability.casefold()
    ]
    if len(matches) != 1:
        raise ChangeError(f"capability identity does not resolve uniquely: {capability}")
    record = matches[0]
    if record.get("operations", {}).get("rename") != "verified":
        status = record.get("operations", {}).get("rename", "unassessed")
        raise ChangeError(
            f"rename is {status} for {record['id']}; no structural change was planned"
        )
    adapters = {
        "construct.boundary-conditions": plan_rename_boundary_condition,
    }
    adapter = adapters.get(record["id"])
    if adapter is None:
        raise ChangeError(f"verified rename adapter is missing for {record['id']}")
    return adapter(source, entity_name, new_name, workspace_root)


def _verified_operation_record(capability: str, operation: str) -> dict[str, Any]:
    registry = load_registry()
    matches = [
        item for item in [
            *registry["top_level_blocks"],
            *registry["cluster_commands"],
            *registry["nested_constructs"],
        ]
        if item["id"].casefold() == capability.casefold()
    ]
    if len(matches) != 1:
        raise ChangeError(f"capability identity does not resolve uniquely: {capability}")
    record = matches[0]
    if record.get("operations", {}).get(operation) != "verified":
        status = record.get("operations", {}).get(operation, "unassessed")
        raise ChangeError(
            f"{operation} is {status} for {record['id']}; no structural change was planned"
        )
    return record


def _structural_payload(
    value: Any, required: set[str], optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChangeError("structural operation payload must be an object")
    optional = optional or set()
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required - optional)
    if missing:
        raise ChangeError(f"structural operation payload is missing: {', '.join(missing)}")
    if extra:
        raise ChangeError(f"structural operation payload has unknown fields: {', '.join(extra)}")
    return value


def _integer_list(value: Any, field: str) -> list[int]:
    if not isinstance(value, list) or any(
        not isinstance(item, int) or isinstance(item, bool) for item in value
    ):
        raise ChangeError(f"{field} must be an array of integers")
    return value


def plan_create_entity(
    source: Path,
    capability: str,
    attributes: dict[str, Any],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Create an entity through an explicitly verified capability adapter."""
    record = _verified_operation_record(capability, "create")
    if record["id"] == "command.node":
        data = _structural_payload(attributes, {"cluster", "label", "x", "y", "z"})
        if not isinstance(data["label"], int) or isinstance(data["label"], bool):
            raise ChangeError("label must be an integer")
        return plan_add_node(
            source, str(data["cluster"]), data["label"], str(data["x"]),
            str(data["y"]), str(data["z"]), workspace_root,
        )
    if record["id"] == "command.element":
        data = _structural_payload(
            attributes, {"cluster", "label", "element_type", "node_labels"}, {"elset"}
        )
        if not isinstance(data["label"], int) or isinstance(data["label"], bool):
            raise ChangeError("label must be an integer")
        return plan_add_element(
            source, str(data["cluster"]), data["label"], str(data["element_type"]),
            _integer_list(data["node_labels"], "node_labels"),
            str(data["elset"]) if data.get("elset") is not None else None,
            workspace_root,
        )
    if record["id"] in {"command.nset", "command.elset"}:
        data = _structural_payload(attributes, {"cluster", "name", "members"})
        member_kind = "node" if record["id"] == "command.nset" else "element"
        return plan_create_set(
            source, str(data["cluster"]), member_kind, str(data["name"]),
            _integer_list(data["members"], "members"), workspace_root,
        )
    raise ChangeError(f"verified create adapter is missing for {record['id']}")


def plan_modify_entity(
    source: Path,
    capability: str,
    entity_name: str,
    changes: dict[str, Any],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Modify an entity through an explicitly verified capability adapter."""
    record = _verified_operation_record(capability, "modify")
    if record["id"] in {"command.nset", "command.elset"}:
        if not isinstance(changes, dict):
            raise ChangeError("structural operation payload must be an object")
        actions = {"add_members", "remove_member"}.intersection(changes)
        if len(actions) != 1:
            raise ChangeError(
                "set modification requires exactly one of add_members or remove_member"
            )
        action = next(iter(actions))
        data = _structural_payload(changes, {"cluster", action})
        member_kind = "node" if record["id"] == "command.nset" else "element"
        if action == "add_members":
            return plan_add_set_members(
                source, str(data["cluster"]), member_kind, entity_name,
                _integer_list(data["add_members"], "add_members"), workspace_root,
            )
        if not isinstance(data["remove_member"], int) or isinstance(
            data["remove_member"], bool
        ):
            raise ChangeError("remove_member must be an integer")
        return plan_remove_set_member(
            source, str(data["cluster"]), member_kind, entity_name,
            data["remove_member"], workspace_root,
        )
    if record["id"] in {"command.boundary", "command.load"}:
        data = _structural_payload(changes, {"cluster", "new_target"}, {"occurrence"})
        occurrence = data.get("occurrence")
        if occurrence is not None and (
            not isinstance(occurrence, int) or isinstance(occurrence, bool)
        ):
            raise ChangeError("occurrence must be an integer")
        return plan_retarget_nodal_record(
            source, record["id"], str(data["cluster"]), entity_name,
            str(data["new_target"]), occurrence, workspace_root,
        )
    if record["id"] == "command.section":
        data = _structural_payload(changes, {"cluster", "new_target"}, {"occurrence"})
        occurrence = data.get("occurrence")
        if occurrence is not None and (
            not isinstance(occurrence, int) or isinstance(occurrence, bool)
        ):
            raise ChangeError("occurrence must be an integer")
        return plan_retarget_section(
            source, str(data["cluster"]), entity_name,
            str(data["new_target"]), occurrence, workspace_root,
        )
    if record["id"] in {"command.shift", "command.scale"}:
        data = _structural_payload(changes, {"cluster", "new_target"}, {"occurrence"})
        occurrence = data.get("occurrence")
        if occurrence is not None and (
            not isinstance(occurrence, int) or isinstance(occurrence, bool)
        ):
            raise ChangeError("occurrence must be an integer")
        return plan_retarget_coordinate_operation(
            source, record["id"], str(data["cluster"]), entity_name,
            str(data["new_target"]), occurrence, workspace_root,
        )
    raise ChangeError(f"verified modify adapter is missing for {record['id']}")


def plan_delete_entity(
    source: Path,
    capability: str,
    entity_name: str,
    context: dict[str, Any],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Delete an entity through an explicitly verified capability adapter."""
    record = _verified_operation_record(capability, "delete")
    if record["id"] == "command.node":
        data = _structural_payload(context, {"cluster"})
        try:
            label = int(entity_name)
        except ValueError as exc:
            raise ChangeError("node entity_name must be an integer label") from exc
        return plan_delete_node(source, str(data["cluster"]), label, workspace_root)
    if record["id"] == "command.element":
        data = _structural_payload(context, {"cluster"})
        try:
            label = int(entity_name)
        except ValueError as exc:
            raise ChangeError("element entity_name must be an integer label") from exc
        return plan_delete_element(source, str(data["cluster"]), label, workspace_root)
    if record["id"] in {"command.nset", "command.elset"}:
        data = _structural_payload(context, {"cluster"})
        member_kind = "node" if record["id"] == "command.nset" else "element"
        return plan_delete_set(
            source, str(data["cluster"]), member_kind, entity_name, workspace_root,
        )
    raise ChangeError(f"verified delete adapter is missing for {record['id']}")


def _block_span(document: SourceDocument, name: str) -> tuple[int, int]:
    matches = [item for item in document.blocks() if item["name"] == name]
    if len(matches) != 1 or matches[0]["end_line"] is None:
        raise ChangeError(f"notch expansion requires one terminated {name} block")
    block = matches[0]
    return int(block["start_line"]), int(block["end_line"])


def _nested_body_patch(
    document: SourceDocument, block: str, command_prefix: str, replacement: str
) -> dict[str, Any]:
    block_start, block_end = _block_span(document, block)
    candidates = [
        line for line in document.lines[block_start:block_end - 1]
        if line.stripped.casefold().startswith(command_prefix.casefold())
    ]
    if len(candidates) != 1:
        raise ChangeError(f"notch expansion requires one {command_prefix} command in {block}")
    command = candidates[0]
    start = command.end
    end = next(
        (
            line.start for line in document.lines[command.number:block_end - 1]
            if line.stripped.startswith("*") and not line.stripped.startswith("**")
        ),
        document.lines[block_end - 1].start,
    )
    return {
        "start": start,
        "end": end,
        "line": command.number + 1,
        "old": document.raw[start:end].decode("latin-1"),
        "new": replacement,
    }


def _block_body_patch(document: SourceDocument, block: str, replacement: str) -> dict[str, Any]:
    start_line, end_line = _block_span(document, block)
    start = document.lines[start_line - 1].end
    end = document.lines[end_line - 1].start
    return {
        "start": start,
        "end": end,
        "line": start_line + 1,
        "old": document.raw[start:end].decode("latin-1"),
        "new": replacement,
    }


def _notch_newline(document: SourceDocument) -> str:
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    return newline.decode("latin-1")


def _notch_boundary_bodies(newline: str) -> tuple[str, str, str]:
    boundary = [
        "type=disp, comp=z, name=bc1-1, value=0.000, nset=PLY1.ZMIN",
    ]
    loads: list[str] = []
    for ply in range(1, 9):
        first = 2 + 3 * (ply - 1)
        boundary.extend([
            f"type=disp, comp=x, name=bc{first}-1, value=0., nset=PLY{ply}.XMAX",
            f"type=disp, comp=x, name=bc{first + 1}-1, value=0.0, nset=PLY{ply}.XMIN",
            f"type=disp, comp=y, name=bc{first + 2}-1, value=0.00, nset=PLY{ply}.XMIN",
        ])
        loads.append(f"change=bc{first}-1, type=disp, value=0.1")

    connections = ["type=-2, name=penalty, tolerance=1.e-5"]
    for lower in range(1, 8):
        connections.append(f"mset=PLY{lower}.ZMAX, Constitutive=3")
    connections.append("last=PLY8")
    boundary_body = newline.join(boundary) + newline * 2
    connection_body = newline.join(connections) + newline * 2
    loading_body = (
        "type=Static, name=n/a,nstep=200,incr=0.1" + newline * 2
        + newline.join(loads) + newline * 2
    )
    return boundary_body, connection_body, loading_body


def _notch_crack_body(document: SourceDocument) -> str:
    start_line, end_line = _block_span(document, "CRACK")
    body = document.raw[
        document.lines[start_line - 1].end:document.lines[end_line - 1].start
    ].decode("latin-1")
    matches = list(re.finditer(r"(?mi)^301\s+arbitrary self-cracks\s*$", body))
    if len(matches) != 2:
        raise ChangeError("notch expansion requires exactly two established crack templates")
    segments: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        segments.append(body[match.start():end])
    rendered: list[str] = [body[:matches[0].start()]]
    for ply in range(1, 9):
        template = segments[(ply - 1) % 2]
        updated, count = re.subn(
            r"(?mi)^(\s*)[12](\s+-approximation\s*)$",
            rf"\g<1>{ply}\g<2>",
            template,
            count=1,
        )
        if count != 1:
            raise ChangeError("notch crack template has no unique approximation selector")
        rendered.append(updated)
    return "".join(rendered)


def _notch_template_compatibility(source_set: SourceSet) -> None:
    semantic = source_set.semantic_index()
    for kind in ("node", "element"):
        first = {
            item.key.rsplit(":", 1)[-1]: item
            for item in semantic.entities
            if item.key.startswith(f"cluster:ply1/{kind}:")
        }
        second = {
            item.key.rsplit(":", 1)[-1]: item
            for item in semantic.entities
            if item.key.startswith(f"cluster:ply2/{kind}:")
        }
        expected_count = 5222 if kind == "node" else 2502
        if len(first) != expected_count or len(second) != expected_count:
            raise ChangeError(
                f"notch templates require {expected_count} {kind} records per ply"
            )
        if first.keys() != second.keys():
            raise ChangeError(f"PLY1 and PLY2 {kind} labels do not match")
        for label, left in first.items():
            right = second[label]
            if kind == "node":
                left_values = left.attributes.get("coordinates", [])
                right_values = right.attributes.get("coordinates", [])
                comparable = left_values[:2] == right_values[:2]
            else:
                comparable = (
                    left.attributes.get("element_type") == right.attributes.get("element_type")
                    and left.attributes.get("connectivity") == right.attributes.get("connectivity")
                )
            if not comparable:
                raise ChangeError(f"PLY1 and PLY2 {kind} {label} are not compatible templates")
    entity_keys = {item.key for item in semantic.entities}
    for ply in (1, 2):
        for set_name in ("xmin", "xmax", "zmin", "zmax"):
            key = f"cluster:ply{ply}/node-set:{set_name}"
            if key not in entity_keys:
                raise ChangeError(f"notch template is missing required set PLY{ply}.{set_name.upper()}")


def _transform_notch_cluster(segment: str, source_ply: int, target_ply: int) -> str:
    segment = re.sub(rf"(?i)\bply{source_ply}\b", f"ply{target_ply}", segment)
    lines = segment.splitlines(keepends=True)
    in_nodes = False
    found_nodes = 0
    result: list[str] = []
    source_base = float(source_ply - 1)
    target_base = 0.25 * (target_ply - 1)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("*") and not stripped.startswith("**"):
            in_nodes = stripped[:5].upper() == "*NODE"
            result.append(line)
            continue
        if not in_nodes or not stripped or stripped.startswith("**"):
            result.append(line)
            continue
        ending = ""
        content = line
        if line.endswith("\r\n"):
            content, ending = line[:-2], "\r\n"
        elif line.endswith(("\n", "\r")):
            content, ending = line[:-1], line[-1]
        fields = content.split(",")
        if len(fields) != 4:
            raise ChangeError("notch node template contains a non-four-field node record")
        try:
            source_z = float(fields[3].strip())
        except ValueError as exc:
            raise ChangeError("notch node template contains an invalid Z coordinate") from exc
        local_z = source_z - source_base
        if local_z < -1e-10 or local_z > 1.0 + 1e-10:
            raise ChangeError("notch template Z extent is not the established unit-thickness ply")
        leading = fields[3][:len(fields[3]) - len(fields[3].lstrip())]
        trailing = fields[3][len(fields[3].rstrip()):]
        fields[3] = leading + f"{target_base + 0.25 * local_z:.17e}" + trailing
        result.append(",".join(fields) + ending)
        found_nodes += 1
    if found_nodes != 5222:
        raise ChangeError(f"notch ply template contains {found_nodes} nodes; expected 5222")
    return "".join(result)


def _notch_cluster_body(document: SourceDocument) -> str:
    start_line, end_line = _block_span(document, "CLUSTERS")
    start = document.lines[start_line - 1].end
    end = document.lines[end_line - 1].start
    body = document.raw[start:end].decode("latin-1")
    starts = [match.start() for match in re.finditer(r"(?mi)^\s*\*TYPE\s*$", body)]
    if len(starts) != 2:
        raise ChangeError("notch expansion requires exactly two cluster templates")
    templates = [body[starts[0]:starts[1]], body[starts[1]:]]
    for index, template in enumerate(templates, start=1):
        match = re.search(r"(?mi)^\s*\*constitutive\s*\r?\n\s*(\d+)\s*$", template)
        if match is None or int(match.group(1)) != index:
            raise ChangeError(f"notch PLY{index} template must use constitutive {index}")
    prefix = body[:starts[0]]
    rendered = [prefix]
    for ply in range(1, 9):
        source_ply = 1 if ply % 2 else 2
        rendered.append(_transform_notch_cluster(templates[source_ply - 1], source_ply, ply))
    return "".join(rendered)


def _notch_expansion_patches(source_set: SourceSet) -> list[dict[str, Any]]:
    document = source_set.documents[source_set.root]
    _notch_template_compatibility(source_set)
    newline = _notch_newline(document)
    boundary, connections, loading = _notch_boundary_bodies(newline)
    return [
        _nested_body_patch(document, "BOUNDARY", "*boundary condition", boundary),
        _nested_body_patch(document, "BOUNDARY", "*connections", connections),
        _nested_body_patch(document, "BOUNDARY", "*loading sequence", loading),
        _block_body_patch(document, "CRACK", _notch_crack_body(document)),
        _block_body_patch(document, "CLUSTERS", _notch_cluster_body(document)),
    ]


def _legacy_solver_patch(source_set: SourceSet) -> tuple[dict[str, Any], dict[str, Any]]:
    """Translate the established serial type-9 SOLVER body to current syntax."""
    document = source_set.documents[source_set.root]
    blocks = [item for item in document.blocks() if item["name"] == "SOLVER"]
    if len(blocks) != 1:
        raise ChangeError("solver migration requires exactly one SOLVER block")
    block = blocks[0]
    if block["end_line"] is None:
        raise ChangeError("solver migration requires a terminated SOLVER block")

    body_lines = document.lines[block["start_line"]:block["end_line"] - 1]
    records = [
        line for line in body_lines
        if line.stripped and not line.stripped.startswith("**")
    ]
    if records and records[0].first_field.casefold().startswith("*type"):
        raise ChangeError("SOLVER block already uses current syntax")
    if len(records) not in {2, 3}:
        raise ChangeError("legacy solver migration requires two records and one optional matrix marker")
    try:
        solver_type = int(records[0].first_field)
        threads = int(records[1].first_field)
    except ValueError as exc:
        raise ChangeError("SOLVER block is not the supported legacy numeric format") from exc
    if solver_type != 9:
        raise ChangeError("solver migration currently supports legacy type 9 only")
    if threads <= 0:
        raise ChangeError("legacy solver thread count must be positive")

    matrix_type = "definite"
    if len(records) == 3:
        marker = records[2].first_field.casefold()
        if marker.startswith("*in"):
            matrix_type = "indefinite"
        elif marker.startswith("*un"):
            matrix_type = "unsymmetric"
        else:
            raise ChangeError("legacy solver matrix marker must be *indefinite or *unsymmetric")

    newline = next((line.newline for line in body_lines if line.newline), b"\n")
    rendered = ["*type=pardiso", f"n_threads={threads}"]
    if matrix_type != "definite":
        rendered.append(f"matrix_type={matrix_type}")
    rendered.append("end solver")
    new_body = newline.join(item.encode("latin-1") for item in rendered) + newline
    start = document.lines[block["start_line"] - 1].end
    end = document.lines[block["end_line"] - 1].start
    patch = {
        "start": start,
        "end": end,
        "line": block["start_line"] + 1,
        "old": document.raw[start:end].decode("latin-1"),
        "new": new_body.decode("latin-1"),
    }
    selector = {
        "source_format": "legacy-numeric",
        "source_type": solver_type,
        "target_type": "pardiso",
        "n_threads": threads,
        "matrix_type": matrix_type,
        "baseline": "BSAM 2.4 non-MPI",
    }
    return patch, selector


def plan_migrate_legacy_solver(
    source: Path, workspace_root: Path | None = None
) -> dict[str, Any]:
    """Plan type-9 legacy-to-current PARDISO syntax migration for the serial baseline."""
    source_set = SourceSet.read(source.resolve(), workspace_root)
    patch, selector = _legacy_solver_patch(source_set)
    preview = (
        "migrate legacy solver type 9 to current PARDISO syntax; preserve "
        f"n_threads={selector['n_threads']} and matrix_type={selector['matrix_type']}"
    )
    return _typed_plan(
        source_set,
        patch,
        "migrate-legacy-solver",
        selector,
        "SOLVER[1]",
        preview,
        "modify",
    )


def plan_expand_notch_plies(
    source: Path, workspace_root: Path | None = None
) -> dict[str, Any]:
    """Plan the approved notch_v1 two-to-eight-ply transformation."""
    source = source.resolve()
    source_set = SourceSet.read(source, workspace_root)
    document = source_set.documents[source]
    patches = _notch_expansion_patches(source_set)
    updated = _patched_bytes_many(document, patches)
    updated_document = SourceDocument.from_bytes(updated, str(source))
    validation = _validation_result(source_set, {source: updated})
    if validation["summary"]["errors"]:
        messages = "; ".join(
            item["message"] for item in validation["diagnostics"] if item["severity"] == "error"
        )
        raise ChangeError(f"planned notch expansion failed dependency validation: {messages}")
    model_paths = [
        "CLUSTERS.plies", "BOUNDARY.*BOUNDARY CONDITION", "BOUNDARY.*CONNECTIONS",
        "BOUNDARY.*LOADING SEQUENCE", "CRACK.approximations",
    ]
    preview = (
        "expand notch_v1 from 2 to 8 plies at constant total thickness 2.0; "
        "repeat [75,15], add seven constitutive-3 interfaces, and replicate in-plane loading"
    )
    selector = {
        "transformation_id": "notch-v1-expand-plies/1.0.0",
        "source_profile": "notch_v1-two-ply",
        "input_plies": 2,
        "output_plies": 8,
        "total_thickness": 2.0,
        "ply_thickness": 0.25,
        "layup_degrees": [75, 15, 75, 15, 75, 15, 75, 15],
        "ply_constitutives": [1, 2, 1, 2, 1, 2, 1, 2],
        "interface_constitutive": 3,
        "z_restraint": "PLY1.ZMIN only",
        "in_plane_policy": "replicate to every ply",
    }
    changes = [
        {"operation": "expand", "target": model_paths[0], "summary": "2 plies -> 8 plies, 0.25 thick each"},
        {"operation": "replicate", "target": model_paths[1], "summary": "in-plane constraints on all plies; Z restraint on PLY1 only"},
        {"operation": "expand", "target": model_paths[2], "summary": "one chained penalty group with 7 constitutive-3 master surfaces"},
        {"operation": "replicate", "target": model_paths[3], "summary": "XMAX displacement loading on all 8 plies"},
        {"operation": "replicate", "target": model_paths[4], "summary": "alternating 75/15 crack definitions for approximations 1-8"},
    ]
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source),
        "workspace_root": str(source_set.workspace_root),
        "base_sha256": document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_sha256": updated_document.sha256,
        "proposed_source_set_sha256": source_set.digest_with({source: updated}),
        "operation": "expand-notch-plies",
        "selector": selector,
        "patches": patches,
        "changed_model_paths": model_paths,
        "affected_files": [str(source)],
        "changes": changes,
        "source_diff": _source_diff(source, document.raw, updated),
        "validation": validation,
        "preview": preview,
    }
    digest = _plan_digest(plan)
    plan["plan_digest"] = digest
    plan["plan_id"] = digest[:16]
    return plan


def plan_parameter_change(
    source: Path,
    block: str,
    construct_name: str,
    parameter: str,
    value: str,
    occurrence: int = 1,
    workspace_root: Path | None = None,
    parameter_occurrence: int | None = None,
    insert_repeated: bool = False,
) -> dict[str, Any]:
    _validate_raw_value(value)
    source = source.resolve()
    source_set = SourceSet.read(source, workspace_root)
    document = source_set.documents[source]
    construct = _construct_record(block, construct_name)
    _validate_replacement(construct, parameter, value)
    definition = _parameter_definition(construct, parameter)
    start_line, end_line = _find_construct_lines(document, block, construct, occurrence)
    if str(definition["value_type"]).casefold() == "flag":
        return _flag_parameter_plan(
            source_set, construct, block, parameter, value, occurrence, start_line,
        )
    candidates: list[tuple[SourceLine, int, int]] = []
    for line in document.lines[start_line:end_line]:
        candidates.extend((line, *span) for span in _value_spans(line, parameter))
    if insert_repeated:
        if parameter_occurrence is not None:
            raise ChangeError(
                "parameter_occurrence cannot be combined with insert_repeated",
                "invalid_parameter_occurrence",
            )
        if definition.get("cardinality", "single") != "repeated-last-wins":
            raise ChangeError(
                f"parameter {parameter} is not registered as repeated",
                "parameter_edit_unsupported",
            )
        if definition.get("edit_operations", {}).get("insert") != "verified":
            raise ChangeError(
                f"insertion of repeated parameter {parameter} is not verified",
                "parameter_edit_unsupported",
            )
        selected_parameter_occurrence = len(candidates) + 1
    if candidates and not insert_repeated:
        selected, selected_parameter_occurrence = _select_parameter_candidate(
            candidates, definition, parameter, parameter_occurrence,
        )
        line, start, end = selected
        old_bytes = document.raw[start:end]
        new_bytes = value.encode("latin-1")
        if old_bytes == new_bytes:
            raise ChangeError("requested value is identical to the existing value")
        patch = {
            "start": start,
            "end": end,
            "line": line.number,
            "old": old_bytes.decode("latin-1"),
            "new": value,
        }
        operation = "set-existing-parameter"
        preview = f"line {line.number}: {parameter} = {old_bytes.decode('latin-1')} -> {value}"
    else:
        if parameter_occurrence is not None:
            raise ChangeError(
                f"parameter {parameter} occurrence {parameter_occurrence} was not found; found 0",
                "missing_parameter",
            )
        if definition.get("edit_operations", {}).get("insert") != "verified":
            raise ChangeError(
                f"parameter {parameter} was not found in {construct['canonical']} occurrence "
                f"{occurrence}; insertion is not verified",
                "missing_parameter",
            )
        insertion = document.lines[end_line].start if end_line < len(document.lines) else len(document.raw)
        line_number = (
            document.lines[end_line].number if end_line < len(document.lines)
            else len(document.lines) + 1
        )
        newline = next(
            (item.newline for item in reversed(document.lines[:end_line]) if item.newline),
            b"\n",
        )
        prefix = b"" if insertion == 0 or document.raw[:insertion].endswith((b"\r", b"\n")) else newline
        record = prefix + f"{definition['name']}={value}".encode("latin-1") + newline
        patch = {
            "start": insertion,
            "end": insertion,
            "line": line_number,
            "old": "",
            "new": record.decode("latin-1"),
        }
        operation = (
            "insert-repeated-parameter" if insert_repeated
            else "insert-optional-parameter"
        )
        if insert_repeated:
            previous = (
                document.raw[candidates[-1][1]:candidates[-1][2]].decode("latin-1")
                if candidates else str(definition.get("default", "absent"))
            )
            preview = (
                f"line {line_number}: append {definition['name']} occurrence "
                f"{selected_parameter_occurrence} = {value}; effective value was {previous}"
            )
        else:
            default = (
                f"registered default {definition['default']}"
                if "default" in definition else "absent"
            )
            preview = f"line {line_number}: add {definition['name']} = {value} (was {default})"
    updated = _patched_bytes(document, patch)
    updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
    validation = _validation_result(source_set, {source: updated})
    if validation["summary"]["errors"]:
        messages = "; ".join(item["message"] for item in validation["diagnostics"] if item["severity"] == "error")
        raise ChangeError(f"planned source set failed dependency validation: {messages}")
    parameter_path = (
        f"{parameter}[{selected_parameter_occurrence}]"
        if insert_repeated or parameter_occurrence is not None else parameter
    )
    model_path = f"{block.upper()}.{construct['canonical']}[{occurrence}].{parameter_path}"
    selector = {
        "block": block.upper(),
        "construct": construct["canonical"],
        "construct_occurrence": occurrence,
        "parameter": parameter,
        "requested_value": value,
    }
    if insert_repeated:
        selector.update({
            "insert_repeated": True,
            "parameter_occurrence": selected_parameter_occurrence,
        })
    elif parameter_occurrence is not None:
        selector["parameter_occurrence"] = parameter_occurrence
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source.resolve()),
        "workspace_root": str(source_set.workspace_root),
        "base_sha256": document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_sha256": updated_document.sha256,
        "proposed_source_set_sha256": source_set.digest_with({source: updated}),
        "operation": operation,
        "selector": selector,
        "patch": patch,
        "changed_model_paths": [model_path],
        "affected_files": [str(source.resolve())],
        "changes": [{
            "operation": "create" if insert_repeated else "modify",
            "target": model_path,
            "summary": preview,
        }],
        "source_diff": _source_diff(source, document.raw, updated),
        "validation": validation,
        "preview": preview,
    }
    digest = _plan_digest(plan)
    plan["plan_digest"] = digest
    plan["plan_id"] = digest[:16]
    return plan


def plan_parameter_removal(
    source: Path,
    block: str,
    construct_name: str,
    parameter: str,
    occurrence: int = 1,
    workspace_root: Path | None = None,
    parameter_occurrence: int | None = None,
) -> dict[str, Any]:
    """Plan removal of one explicit optional parameter with verified reset semantics."""
    source = source.resolve()
    source_set = SourceSet.read(source, workspace_root)
    document = source_set.documents[source]
    construct = _construct_record(block, construct_name)
    definition = _parameter_definition(construct, parameter)
    if definition.get("edit_operations", {}).get("remove") != "verified":
        raise ChangeError(
            f"removal of parameter {parameter} is not verified",
            "parameter_edit_unsupported",
        )
    if definition.get("required") or "default" not in definition:
        raise ChangeError(
            f"parameter {parameter} cannot be safely reset by omission",
            "parameter_edit_unsupported",
        )
    start_line, end_line = _find_construct_lines(document, block, construct, occurrence)
    candidates: list[tuple[SourceLine, int, int]] = []
    for line in document.lines[start_line:end_line]:
        candidates.extend((line, *span) for span in _value_spans(line, parameter))
    if not candidates:
        raise ChangeError(
            f"parameter {parameter} was not found in {construct['canonical']} occurrence {occurrence}",
            "missing_parameter",
        )
    selected, selected_parameter_occurrence = _select_parameter_candidate(
        candidates, definition, parameter, parameter_occurrence,
    )
    line, value_start, value_end = selected
    if "#" in line.text or "," in line.text:
        raise ChangeError(
            f"parameter {parameter} shares line {line.number}; minimal removal is not verified",
            "parameter_edit_unsupported",
        )
    local_start = value_start - line.start
    local_end = value_end - line.start
    before = line.text[:local_start]
    after = line.text[local_end:]
    expected_prefix = re.fullmatch(
        rf"\s*{re.escape(parameter)}\s*=\s*", before, re.IGNORECASE,
    )
    if expected_prefix is None or after.strip():
        raise ChangeError(
            f"parameter {parameter} is not an isolated record; minimal removal is not verified",
            "parameter_edit_unsupported",
        )
    old_record = document.raw[line.start:line.end]
    patch = {
        "source": str(source),
        "start": line.start,
        "end": line.end,
        "line": line.number,
        "old": old_record.decode("latin-1"),
        "new": "",
    }
    parameter_path = (
        f"{parameter}[{selected_parameter_occurrence}]"
        if parameter_occurrence is not None else parameter
    )
    model_path = f"{block.upper()}.{construct['canonical']}[{occurrence}].{parameter_path}"
    repeated_removal = parameter_occurrence is not None
    if repeated_removal:
        remaining = [item for index, item in enumerate(candidates, start=1) if index != selected_parameter_occurrence]
        effective = (
            document.raw[remaining[-1][1]:remaining[-1][2]].decode("latin-1")
            if remaining else str(definition["default"])
        )
        preview = (
            f"line {line.number}: remove {parameter} occurrence "
            f"{selected_parameter_occurrence}; effective value becomes {effective}"
        )
    else:
        preview = (
            f"line {line.number}: remove explicit {parameter}; restore registered default "
            f"{definition['default']}"
        )
    selector = {
        "block": block.upper(),
        "construct": construct["canonical"],
        "construct_occurrence": occurrence,
        "parameter": parameter,
    }
    if repeated_removal:
        selector["parameter_occurrence"] = selected_parameter_occurrence
    return _typed_plan(
        source_set,
        patch,
        "remove-repeated-parameter" if repeated_removal else "remove-optional-parameter",
        selector,
        model_path,
        preview,
        "delete",
    )


def write_plan(plan: dict[str, Any], destination: Path) -> None:
    if destination.exists():
        raise ChangeError(f"plan destination already exists: {destination}")
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")


def _validate_plan_object(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ChangeError("change plan must be a JSON object")
    if plan.get("schema_version") not in SUPPORTED_PLAN_SCHEMA_VERSIONS:
        raise ChangeError("unsupported change-plan schema version")
    required = {"source", "base_sha256", "operation", "selector", "preview"}
    missing = sorted(required - plan.keys())
    if missing:
        raise ChangeError(f"change plan is missing required fields: {', '.join(missing)}")
    has_patch = isinstance(plan.get("patch"), dict)
    has_patches = isinstance(plan.get("patches"), list) and bool(plan["patches"])
    if has_patch == has_patches:
        raise ChangeError("change plan must contain exactly one of patch or patches")
    digest = plan.get("plan_digest")
    content = {key: value for key, value in plan.items() if key not in {"plan_digest", "plan_id"}}
    expected = _plan_digest(content)
    if digest != expected or plan.get("plan_id") != expected[:16]:
        raise ChangeError("change-plan digest is invalid")
    return plan


def load_plan(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        plan = json.load(stream)
    return _validate_plan_object(plan)


def plan_refresh_change(
    source: Path,
    stale_plan_path: Path,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Re-preview a digest-valid stale plan by replaying only its typed selector."""
    source = source.resolve()
    plan = load_plan(stale_plan_path.resolve())
    planned_source = Path(str(plan["source"])).resolve()
    if planned_source != source:
        raise ChangeError("stale plan source does not match the requested source")
    current = SourceSet.read(source, workspace_root)
    same_root = current.documents[source].sha256 == plan["base_sha256"]
    expected_set = plan.get("base_source_set_sha256")
    same_set = (
        expected_set == current.sha256
        or (expected_set is None and len(current.documents) == 1)
    )
    if same_root and same_set:
        raise ChangeError("change plan is not stale; review the existing plan instead")

    operation = str(plan["operation"])
    selector = plan["selector"]
    if not isinstance(selector, dict):
        raise ChangeError("stale plan selector is malformed")
    if operation in {
        "set-existing-parameter", "insert-optional-parameter",
        "insert-repeated-parameter", "insert-optional-flag", "remove-optional-flag",
    }:
        patch = plan.get("patch")
        if not isinstance(patch, dict) or not isinstance(patch.get("new"), str):
            raise ChangeError("stale parameter plan is missing its requested value")
        requested_value = selector.get("requested_value")
        if not isinstance(requested_value, str):
            if operation != "set-existing-parameter":
                raise ChangeError("stale parameter plan is missing its requested value")
            requested_value = patch["new"]
        return plan_parameter_change(
            source, str(selector["block"]), str(selector["construct"]),
            str(selector["parameter"]), requested_value,
            int(selector["construct_occurrence"]), workspace_root,
            parameter_occurrence=(
                int(selector["parameter_occurrence"])
                if operation == "set-existing-parameter"
                and "parameter_occurrence" in selector else None
            ),
            insert_repeated=operation == "insert-repeated-parameter",
        )
    if operation in {"remove-optional-parameter", "remove-repeated-parameter"}:
        return plan_parameter_removal(
            source, str(selector["block"]), str(selector["construct"]),
            str(selector["parameter"]), int(selector["construct_occurrence"]),
            workspace_root,
            parameter_occurrence=(
                int(selector["parameter_occurrence"])
                if "parameter_occurrence" in selector else None
            ),
        )
    if operation == "rename-boundary-condition":
        return plan_rename_boundary_condition(
            source, str(selector["old_name"]), str(selector["new_name"]), workspace_root,
        )
    if operation == "add-node":
        coordinates = selector.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 3:
            raise ChangeError("stale add-node selector is malformed")
        return plan_add_node(
            source, str(selector["cluster"]), int(selector["label"]),
            *(str(item) for item in coordinates), workspace_root=workspace_root,
        )
    if operation == "add-element":
        node_labels = selector.get("node_labels")
        if not isinstance(node_labels, list):
            raise ChangeError("stale add-element selector is malformed")
        return plan_add_element(
            source, str(selector["cluster"]), int(selector["label"]),
            str(selector["element_type"]), [int(item) for item in node_labels],
            str(selector["elset"]) if selector.get("elset") is not None else None,
            workspace_root,
        )
    if operation == "delete-node":
        return plan_delete_node(
            source, str(selector["cluster"]), int(selector["label"]), workspace_root,
        )
    if operation == "delete-element":
        return plan_delete_element(
            source, str(selector["cluster"]), int(selector["label"]), workspace_root,
        )
    if operation in {"create-set", "add-set-members"}:
        members = selector.get("members")
        if not isinstance(members, list):
            raise ChangeError(f"stale {operation} selector is malformed")
        planner = plan_create_set if operation == "create-set" else plan_add_set_members
        return planner(
            source, str(selector["cluster"]), str(selector["member_kind"]),
            str(selector["name"]), [int(item) for item in members], workspace_root,
        )
    if operation == "remove-set-member":
        return plan_remove_set_member(
            source, str(selector["cluster"]), str(selector["member_kind"]),
            str(selector["name"]), int(selector["member"]), workspace_root,
        )
    if operation == "delete-set":
        return plan_delete_set(
            source, str(selector["cluster"]), str(selector["member_kind"]),
            str(selector["name"]), workspace_root,
        )
    if operation == "retarget-nodal-record":
        return plan_retarget_nodal_record(
            source, str(selector["capability"]), str(selector["cluster"]),
            str(selector["current_target"]), str(selector["new_target"]),
            int(selector["occurrence"]), workspace_root,
        )
    if operation == "retarget-section":
        return plan_retarget_section(
            source, str(selector["cluster"]), str(selector["current_target"]),
            str(selector["new_target"]), int(selector["occurrence"]), workspace_root,
        )
    if operation == "retarget-coordinate-operation":
        return plan_retarget_coordinate_operation(
            source, str(selector["capability"]), str(selector["cluster"]),
            str(selector["current_target"]), str(selector["new_target"]),
            int(selector["occurrence"]), workspace_root,
        )
    if operation == "migrate-legacy-solver":
        return plan_migrate_legacy_solver(source, workspace_root)
    if operation == "expand-notch-plies":
        return plan_expand_notch_plies(source, workspace_root)
    if operation == "import-mesh":
        mesh = selector.get("mesh")
        if not isinstance(mesh, dict) or not isinstance(mesh.get("path"), str):
            raise ChangeError("stale import-mesh selector is malformed")
        return plan_import_mesh(
            source, Path(mesh["path"]), str(selector["cluster"]), workspace_root,
        )
    raise ChangeError(f"stale-plan recovery is unsupported for operation {operation}")


def _validated_plan_proposal(
    plan: dict[str, Any],
    source: Path,
    document: SourceDocument,
    source_set: SourceSet,
) -> tuple[dict[Path, bytes], SourceDocument, list[str], str, dict[str, Any]]:
    """Re-derive a plan through registered typing and exact source selection."""
    operation = plan.get("operation")
    if operation == "compose-changes":
        components = plan.get("components")
        if not isinstance(components, list):
            raise ChangeError("composite change plan is missing its components")
        expected = _composite_plan(components, source_set)
        checked_fields = (
            "selector", "components", "patches", "changed_model_paths",
            "affected_files", "changes", "inputs", "source_diff", "validation",
            "preview", "proposed_sha256", "proposed_source_set_sha256",
        )
        for field in checked_fields:
            if plan.get(field) != expected.get(field):
                raise ChangeError(
                    f"composite change plan {field} does not match its typed components"
                )
        replacements = _patched_source_files(source_set, expected["patches"])
        root_raw = replacements.get(source.resolve(), document.raw)
        updated_document = SourceDocument.from_bytes(root_raw, str(source.resolve()))
        return (
            replacements,
            updated_document,
            expected["changed_model_paths"],
            expected["source_diff"],
            expected["validation"],
        )

    if operation == "rename-boundary-condition":
        selector = plan.get("selector")
        if not isinstance(selector, dict):
            raise ChangeError("boundary-condition rename plan is missing its selector")
        try:
            old_name = str(selector["old_name"])
            new_name = str(selector["new_name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ChangeError("boundary-condition rename selector is malformed") from exc
        expected = plan_rename_boundary_condition(
            source, old_name, new_name, source_set.workspace_root
        )
        checked_fields = (
            "selector", "patches", "changed_model_paths", "affected_files", "changes",
            "source_diff", "validation", "preview", "proposed_sha256",
            "proposed_source_set_sha256",
        )
        for field in checked_fields:
            if plan.get(field) != expected.get(field):
                raise ChangeError(
                    f"boundary-condition rename plan {field} does not match its typed selector"
                )
        updated = _patched_bytes_many(document, expected["patches"])
        updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
        return (
            {source.resolve(): updated},
            updated_document,
            expected["changed_model_paths"],
            expected["source_diff"],
            expected["validation"],
        )

    if operation == "expand-notch-plies":
        expected = plan_expand_notch_plies(source, source_set.workspace_root)
        checked_fields = (
            "selector", "patches", "changed_model_paths", "affected_files", "changes",
            "source_diff", "validation", "preview", "proposed_sha256",
            "proposed_source_set_sha256",
        )
        for field in checked_fields:
            if plan.get(field) != expected.get(field):
                raise ChangeError(f"notch expansion plan {field} does not match its typed selector")
        patches = expected["patches"]
        updated = _patched_bytes_many(document, patches)
        updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
        return (
            {source.resolve(): updated},
            updated_document,
            expected["changed_model_paths"],
            expected["source_diff"],
            expected["validation"],
        )

    if operation == "migrate-legacy-solver":
        expected = plan_migrate_legacy_solver(source, source_set.workspace_root)
        checked_fields = (
            "selector", "patch", "changed_model_paths", "affected_files", "changes",
            "source_diff", "validation", "preview", "proposed_sha256",
            "proposed_source_set_sha256",
        )
        for field in checked_fields:
            if plan.get(field) != expected.get(field):
                raise ChangeError(f"solver migration plan {field} does not match its typed selector")
        updated = _patched_bytes(document, expected["patch"])
        updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
        return (
            {source.resolve(): updated},
            updated_document,
            expected["changed_model_paths"],
            expected["source_diff"],
            expected["validation"],
        )

    if operation in {
        "add-node", "add-element", "delete-node", "delete-element", "create-set", "add-set-members",
        "remove-set-member", "delete-set", "retarget-nodal-record", "retarget-section",
        "retarget-coordinate-operation", "import-mesh",
    }:
        selector = plan.get("selector")
        if not isinstance(selector, dict):
            raise ChangeError("change plan is missing its selector")
        try:
            cluster = str(selector["cluster"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ChangeError(f"{operation} selector is malformed") from exc
        if operation in {"add-node", "add-element", "delete-node", "delete-element"}:
            try:
                label = int(selector["label"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ChangeError(f"{operation} selector is malformed") from exc
        if operation == "add-node":
            values = selector.get("coordinates")
            if not isinstance(values, list) or len(values) != 3:
                raise ChangeError("add-node selector is malformed")
            coordinates = (str(values[0]), str(values[1]), str(values[2]))
            patch = _node_patch(source_set, cluster, label, coordinates)
            model_path = f"CLUSTERS[{cluster.casefold()}].nodes[{label}]"
            preview = (
                f"line {patch['line']}: add node {label} to cluster {cluster} at "
                f"({coordinates[0]}, {coordinates[1]}, {coordinates[2]})"
            )
            change_operation = "create"
        elif operation == "add-element":
            values = selector.get("node_labels")
            if not isinstance(values, list) or not values:
                raise ChangeError("add-element selector is malformed")
            try:
                node_labels = tuple(int(item) for item in values)
            except (TypeError, ValueError) as exc:
                raise ChangeError("add-element node labels are malformed") from exc
            element_type = str(selector.get("element_type", ""))
            elset_value = selector.get("elset")
            if elset_value is not None and not isinstance(elset_value, str):
                raise ChangeError("add-element ELSET is malformed")
            patch = _element_patch(
                source_set, cluster, label, element_type, node_labels, elset_value
            )
            model_path = f"CLUSTERS[{cluster.casefold()}].elements[{label}]"
            preview = (
                f"line {patch['line']}: add {element_type.upper()} element {label} "
                f"to cluster {cluster}"
            )
            change_operation = "create"
        elif operation == "delete-node":
            patch = _delete_node_patch(source_set, cluster, label)
            model_path = f"CLUSTERS[{cluster.casefold()}].nodes[{label}]"
            preview = f"line {patch['line']}: delete unreferenced node {label} from cluster {cluster}"
            change_operation = "delete"
        elif operation == "delete-element":
            patch = _delete_mesh_entity_patch(source_set, cluster, label, "element")
            model_path = f"CLUSTERS[{cluster.casefold()}].elements[{label}]"
            preview = (
                f"line {patch['line']}: delete unreferenced element {label} "
                f"from cluster {cluster}"
            )
            change_operation = "delete"
        elif operation in {"create-set", "add-set-members"}:
            member_kind = str(selector.get("member_kind", ""))
            name = str(selector.get("name", ""))
            values = selector.get("members")
            if not isinstance(values, list) or not values:
                raise ChangeError(f"{operation} member list is malformed")
            try:
                members = tuple(int(item) for item in values)
            except (TypeError, ValueError) as exc:
                raise ChangeError(f"{operation} member list is malformed") from exc
            creating = operation == "create-set"
            patch = _set_patch(
                source_set, cluster, member_kind, name, members, creating
            )
            set_kind = f"{member_kind}-sets"
            model_path = f"CLUSTERS[{cluster.casefold()}].{set_kind}[{name.casefold()}]"
            if creating:
                preview = (
                    f"line {patch['line']}: create {member_kind} set {name} "
                    f"with {len(members)} members"
                )
                change_operation = "create"
            else:
                model_path += ".members"
                preview = (
                    f"line {patch['line']}: add {len(members)} members to "
                    f"{member_kind} set {name}"
                )
                change_operation = "modify"
        elif operation == "remove-set-member":
            member_kind = str(selector.get("member_kind", ""))
            name = str(selector.get("name", ""))
            try:
                member = int(selector["member"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ChangeError("remove-set-member selector is malformed") from exc
            patch = _remove_set_member_patch(
                source_set, cluster, member_kind, name, member,
            )
            set_kind = f"{member_kind}-sets"
            model_path = (
                f"CLUSTERS[{cluster.casefold()}].{set_kind}[{name.casefold()}]"
                f".members[{member}]"
            )
            preview = (
                f"line {patch['line']}: remove member {member} from "
                f"{member_kind} set {name}"
            )
            change_operation = "delete"
        elif operation == "delete-set":
            member_kind = str(selector.get("member_kind", ""))
            name = str(selector.get("name", ""))
            patch = _delete_set_patch(source_set, cluster, member_kind, name)
            set_kind = f"{member_kind}-sets"
            model_path = f"CLUSTERS[{cluster.casefold()}].{set_kind}[{name.casefold()}]"
            preview = f"line {patch['line']}: delete unreferenced {member_kind} set {name}"
            change_operation = "delete"
        elif operation == "retarget-nodal-record":
            capability = str(selector.get("capability", ""))
            current_target = str(selector.get("current_target", ""))
            new_target = str(selector.get("new_target", ""))
            try:
                occurrence = int(selector["occurrence"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ChangeError("retarget-nodal-record selector is malformed") from exc
            patch, selected_occurrence, entity_kind = _nodal_record_target_patch(
                source_set, capability, cluster, current_target, new_target, occurrence,
            )
            model_path = (
                f"CLUSTERS[{cluster.casefold()}].{entity_kind}[{selected_occurrence}].target"
            )
            preview = (
                f"line {patch['line']}: retarget {capability} record from "
                f"{current_target} to {new_target}"
            )
            change_operation = "modify"
        elif operation == "retarget-section":
            current_target = str(selector.get("current_target", ""))
            new_target = str(selector.get("new_target", ""))
            try:
                occurrence = int(selector["occurrence"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ChangeError("retarget-section selector is malformed") from exc
            patch, selected_occurrence = _section_target_patch(
                source_set, cluster, current_target, new_target, occurrence,
            )
            model_path = (
                f"CLUSTERS[{cluster.casefold()}].sections[{selected_occurrence}].elset"
            )
            preview = (
                f"line {patch['line']}: retarget section from "
                f"{current_target} to {new_target}"
            )
            change_operation = "modify"
        elif operation == "retarget-coordinate-operation":
            capability = str(selector.get("capability", ""))
            current_target = str(selector.get("current_target", ""))
            new_target = str(selector.get("new_target", ""))
            try:
                occurrence = int(selector["occurrence"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ChangeError("retarget-coordinate-operation selector is malformed") from exc
            patch, selected_occurrence, operation_name = _coordinate_operation_target_patch(
                source_set, capability, cluster, current_target, new_target, occurrence,
            )
            model_path = (
                f"CLUSTERS[{cluster.casefold()}].coordinate-operations"
                f"[{operation_name}:{selected_occurrence}].nset"
            )
            preview = (
                f"line {patch['line']}: retarget {operation_name} from "
                f"{current_target} to {new_target}"
            )
            change_operation = "modify"
        else:
            mesh_input = selector.get("mesh")
            if not isinstance(mesh_input, dict):
                raise ChangeError("import-mesh selector is malformed")
            mesh_path = mesh_input.get("path")
            mesh_sha256 = mesh_input.get("sha256")
            if not isinstance(mesh_path, str) or not isinstance(mesh_sha256, str):
                raise ChangeError("import-mesh selector is malformed")
            patch, mesh = _mesh_import_patch(
                source_set, cluster, Path(mesh_path), mesh_sha256
            )
            model_path = f"CLUSTERS[{cluster.casefold()}].mesh"
            summary = mesh.as_dict()["summary"]
            preview = (
                f"line {patch['line']}: import {summary['nodes']} nodes and "
                f"{summary['elements']} elements into cluster {cluster}"
            )
            change_operation = "create"
            expected_input = {
                "role": "mesh",
                "format": "abaqus-style-ele",
                "path": mesh.source,
                "sha256": mesh.sha256,
            }
            if mesh_input != expected_input or plan.get("inputs") != [expected_input]:
                raise ChangeError("change plan mesh provenance does not match its input")
        if plan.get("patch") != patch:
            raise ChangeError(f"change plan patch does not match its typed {operation} selector")
        patch_source = Path(str(patch.get("source", source))).resolve()
        patch_document = source_set.documents.get(patch_source)
        if patch_document is None:
            raise ChangeError("planned patch source is not in the bound source set")
        updated = _patched_bytes(patch_document, patch)
        replacements = {patch_source: updated}
        root_raw = replacements.get(source.resolve(), document.raw)
        updated_document = SourceDocument.from_bytes(root_raw, str(source.resolve()))
        source_diff = _source_diff(patch_source, patch_document.raw, updated)
        validation = _validation_result(source_set, replacements)
        expected_changes = [{"operation": change_operation, "target": model_path, "summary": preview}]
        if plan.get("proposed_sha256") not in {None, updated_document.sha256}:
            raise ChangeError("change plan proposed-output digest is invalid")
        if plan.get("source_diff") != source_diff:
            raise ChangeError("change plan source diff does not match its exact patch")
        if plan.get("validation") != validation:
            raise ChangeError("change plan validation preview does not match its exact patch")
        if validation["summary"]["errors"]:
            raise ChangeError("planned source set failed dependency validation")
        if plan.get("changed_model_paths") != [model_path]:
            raise ChangeError("change plan model path does not match its typed selector")
        if plan.get("changes") != expected_changes or plan.get("preview") != preview:
            raise ChangeError("change plan semantic changes do not match its typed selector")
        if plan.get("affected_files") != [str(patch_source)]:
            raise ChangeError("change plan affected files do not match its source")
        return replacements, updated_document, [model_path], source_diff, validation

    if plan.get("operation") in {
        "remove-optional-parameter", "remove-repeated-parameter",
    }:
        selector = plan.get("selector")
        if not isinstance(selector, dict):
            raise ChangeError("removed parameter plan is missing its selector")
        try:
            expected = plan_parameter_removal(
                source,
                str(selector["block"]),
                str(selector["construct"]),
                str(selector["parameter"]),
                int(selector["construct_occurrence"]),
                source_set.workspace_root,
                parameter_occurrence=(
                    int(selector["parameter_occurrence"])
                    if "parameter_occurrence" in selector else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ChangeError("removed parameter selector is malformed") from exc
        checked_fields = (
            "operation", "selector", "patch", "changed_model_paths", "affected_files",
            "changes", "source_diff", "validation", "preview", "proposed_sha256",
            "proposed_source_set_sha256",
        )
        for field in checked_fields:
            if plan.get(field) != expected.get(field):
                raise ChangeError(
                    f"removed parameter plan {field} does not match its typed selector"
                )
        updated = _patched_bytes(document, expected["patch"])
        updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
        return (
            {source.resolve(): updated}, updated_document,
            expected["changed_model_paths"], expected["source_diff"], expected["validation"],
        )

    if plan.get("operation") in {
        "insert-optional-parameter", "insert-repeated-parameter",
        "insert-optional-flag", "remove-optional-flag",
    }:
        selector = plan.get("selector")
        patch = plan.get("patch")
        if not isinstance(selector, dict) or not isinstance(patch, dict):
            raise ChangeError("change plan is missing its selector or patch")
        if not isinstance(patch.get("new"), str):
            raise ChangeError("change plan new value must be a string")
        try:
            expected = plan_parameter_change(
                source,
                str(selector["block"]),
                str(selector["construct"]),
                str(selector["parameter"]),
                str(selector["requested_value"]),
                int(selector["construct_occurrence"]),
                source_set.workspace_root,
                insert_repeated=plan.get("operation") == "insert-repeated-parameter",
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ChangeError("inserted parameter selector or patch is malformed") from exc
        checked_fields = (
            "operation", "selector", "patch", "changed_model_paths", "affected_files",
            "changes", "source_diff", "validation", "preview", "proposed_sha256",
            "proposed_source_set_sha256",
        )
        for field in checked_fields:
            if plan.get(field) != expected.get(field):
                raise ChangeError(
                    f"parameter plan {field} does not match its typed selector"
                )
        updated = _patched_bytes(document, expected["patch"])
        updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
        return (
            {source.resolve(): updated}, updated_document,
            expected["changed_model_paths"], expected["source_diff"], expected["validation"],
        )

    if plan.get("operation") != "set-existing-parameter":
        raise ChangeError("unsupported change-plan operation")
    selector = plan.get("selector")
    patch = plan.get("patch")
    if not isinstance(selector, dict) or not isinstance(patch, dict):
        raise ChangeError("change plan is missing its selector or patch")
    if not isinstance(patch.get("old"), str) or not isinstance(patch.get("new"), str):
        raise ChangeError("change plan old and new values must be strings")
    try:
        block = str(selector["block"])
        construct_name = str(selector["construct"])
        occurrence = int(selector["construct_occurrence"])
        parameter = str(selector["parameter"])
        new_value = str(patch["new"])
        planned_start = int(patch["start"])
        planned_end = int(patch["end"])
        planned_line = int(patch["line"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ChangeError("change plan selector or patch is malformed") from exc
    _validate_raw_value(new_value)
    construct = _construct_record(block, construct_name)
    _validate_replacement(construct, parameter, new_value)
    requested_value = selector.get("requested_value")
    if requested_value is not None and requested_value != new_value:
        raise ChangeError("change plan requested value does not match its exact patch")
    start_line, end_line = _find_construct_lines(document, block, construct, occurrence)
    candidates: list[tuple[SourceLine, int, int]] = []
    for line in document.lines[start_line:end_line]:
        candidates.extend((line, *span) for span in _value_spans(line, parameter))
    try:
        parameter_occurrence = (
            int(selector["parameter_occurrence"])
            if "parameter_occurrence" in selector else None
        )
    except (TypeError, ValueError) as exc:
        raise ChangeError("parameter occurrence selector is malformed") from exc
    if not candidates:
        raise ChangeError("planned parameter no longer resolves to a registered value")
    selected, selected_parameter_occurrence = _select_parameter_candidate(
        candidates, _parameter_definition(construct, parameter), parameter,
        parameter_occurrence,
    )
    line, start, end = selected
    if (start, end, line.number) != (planned_start, planned_end, planned_line):
        raise ChangeError("planned patch does not match the registered parameter source span")

    updated = _patched_bytes(document, patch)
    updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
    if plan.get("proposed_sha256") not in {None, updated_document.sha256}:
        raise ChangeError("change plan proposed-output digest is invalid")
    source_diff = _source_diff(source, document.raw, updated)
    if plan.get("source_diff") is not None and plan["source_diff"] != source_diff:
        raise ChangeError("change plan source diff does not match its exact patch")
    validation = _validation_result(source_set, {source.resolve(): updated})
    if (
        plan.get("schema_version") == PLAN_SCHEMA_VERSION
        and plan.get("validation") is not None
        and plan["validation"] != validation
    ):
        raise ChangeError("change plan validation preview does not match its exact patch")
    if validation["summary"]["errors"]:
        messages = "; ".join(
            item["message"] for item in validation["diagnostics"] if item["severity"] == "error"
        )
        raise ChangeError(f"planned source set failed dependency validation: {messages}")
    parameter_path = (
        f"{parameter}[{selected_parameter_occurrence}]"
        if parameter_occurrence is not None else parameter
    )
    model_path = f"{block.upper()}.{construct['canonical']}[{occurrence}].{parameter_path}"
    if plan.get("changed_model_paths") is not None and plan["changed_model_paths"] != [model_path]:
        raise ChangeError("change plan model path does not match its registered selector")
    expected_preview = f"line {line.number}: {parameter} = {patch['old']} -> {new_value}"
    if plan["preview"] != expected_preview:
        raise ChangeError("change plan preview does not match its registered selector and patch")
    expected_changes = [{
        "operation": "modify",
        "target": model_path,
        "summary": expected_preview,
    }]
    if plan.get("changes") is not None and plan["changes"] != expected_changes:
        raise ChangeError("change plan semantic changes do not match its registered selector")
    expected_files = [str(source.resolve())]
    if plan.get("affected_files") is not None and plan["affected_files"] != expected_files:
        raise ChangeError("change plan affected files do not match its source")
    return {source.resolve(): updated}, updated_document, [model_path], source_diff, validation


def _composite_plan(
    components: list[dict[str, Any]], source_set: SourceSet,
) -> dict[str, Any]:
    """Build one validated plan from independent, same-revision typed plans."""
    if not 2 <= len(components) <= 8:
        raise ChangeError("a composite change plan requires between 2 and 8 component plans")
    source = source_set.root.resolve()
    document = source_set.documents[source]
    patches: list[dict[str, Any]] = []
    model_paths: list[str] = []
    changes: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    component_ids: list[str] = []

    for raw_component in components:
        component = _validate_plan_object(raw_component)
        if component.get("operation") == "compose-changes":
            raise ChangeError("nested composite change plans are not supported")
        if Path(str(component["source"])).resolve() != source:
            raise ChangeError("component plans must target the same source deck")
        if component.get("base_sha256") != document.sha256:
            raise ChangeError("component plans must share the same source revision")
        if component.get("base_source_set_sha256") != source_set.sha256:
            raise ChangeError("component plans must share the same source-set revision")
        _validated_plan_proposal(component, source, document, source_set)
        patches.extend(component.get("patches") or [component["patch"]])
        for model_path in component.get("changed_model_paths", []):
            if model_path not in model_paths:
                model_paths.append(model_path)
        changes.extend(deepcopy(component.get("changes", [])))
        for item in component.get("inputs", []):
            if item not in inputs:
                inputs.append(deepcopy(item))
        component_ids.append(str(component["plan_id"]))

    replacements = _patched_source_files(source_set, patches)
    root_raw = replacements.get(source, document.raw)
    updated_document = SourceDocument.from_bytes(root_raw, str(source))
    validation = _validation_result(source_set, replacements)
    if validation["summary"]["errors"]:
        messages = "; ".join(
            item["message"] for item in validation["diagnostics"]
            if item["severity"] == "error"
        )
        raise ChangeError(f"composite source set failed dependency validation: {messages}")
    preview = (
        f"{len(components)} deterministic operations: "
        + "; ".join(str(item["preview"]) for item in components)
    )
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source),
        "workspace_root": str(source_set.workspace_root),
        "base_sha256": document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_sha256": updated_document.sha256,
        "proposed_source_set_sha256": source_set.digest_with(replacements),
        "operation": "compose-changes",
        "selector": {"component_plan_ids": component_ids},
        "components": deepcopy(components),
        "patches": deepcopy(patches),
        "changed_model_paths": model_paths,
        "affected_files": [str(path) for path in replacements],
        "changes": changes,
        "inputs": inputs,
        "source_diff": "".join(
            _source_diff(path, source_set.documents[path].raw, replacements[path])
            for path in replacements
        ),
        "validation": validation,
        "preview": preview,
    }
    digest = _plan_digest(plan)
    plan["plan_digest"] = digest
    plan["plan_id"] = digest[:16]
    return plan


def plan_compose_changes(
    source: Path,
    plan_paths: list[Path],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Compose independent typed plans against one revision into one review boundary."""
    source = source.resolve()
    source_set = SourceSet.read(source, workspace_root)
    components = [load_plan(path.resolve()) for path in plan_paths]
    return _composite_plan(components, source_set)


def _source_set_for_plan(plan: dict[str, Any], source: Path) -> SourceSet:
    workspace = plan.get("workspace_root")
    boundary = Path(workspace) if isinstance(workspace, str) else None
    source_set = SourceSet.read(source, boundary)
    document = source_set.documents[source.resolve()]
    if document.sha256 != plan["base_sha256"]:
        raise ChangeError("source changed after planning; create a new change plan")
    expected = plan.get("base_source_set_sha256")
    if expected is None and len(source_set.documents) > 1:
        raise ChangeError(
            "legacy change plan is not bound to the include source set; create a new change plan"
        )
    if expected is not None and source_set.sha256 != expected:
        raise ChangeError("source set changed after planning; create a new change plan")
    return source_set


def review_plan(path: Path) -> dict[str, Any]:
    """Return review data only after revalidating the plan and source revision."""
    plan = load_plan(path)
    source = Path(plan["source"])
    source_set = _source_set_for_plan(plan, source)
    document = source_set.documents[source.resolve()]
    if document.sha256 != plan["base_sha256"]:
        raise ChangeError("source changed after planning; create a new change plan")
    replacements, updated_document, model_paths, source_diff, validation = _validated_plan_proposal(
        plan, source, document, source_set
    )
    proposed_source_set_sha256 = source_set.digest_with(replacements)
    if plan.get("proposed_source_set_sha256") not in {None, proposed_source_set_sha256}:
        raise ChangeError("change plan proposed source-set digest is invalid")
    return {
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
        "source": str(source.resolve()),
        "base_sha256": document.sha256,
        "proposed_sha256": updated_document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_source_set_sha256": proposed_source_set_sha256,
        "changed_model_paths": model_paths,
        "affected_files": plan.get("affected_files", [str(source.resolve())]),
        "changes": plan.get("changes", [{
            "operation": "modify",
            "target": model_paths[0],
            "summary": plan["preview"],
        }]),
        "source_diff": source_diff,
        "validation": validation,
    }


def _default_audit_path(destination: Path) -> Path:
    return Path(str(destination) + ".audit.json")


def _source_set_output_map(
    source_set: SourceSet, destination: Path,
) -> dict[Path, Path]:
    """Map a source set to a new root location without changing include spellings."""
    destination = destination.resolve()
    if destination.parent == source_set.input_directory:
        return {source_set.root: destination}
    output = {source_set.root: destination}
    for source_path in source_set.documents:
        if source_path == source_set.root:
            continue
        try:
            relative = source_path.relative_to(source_set.input_directory)
        except ValueError as exc:
            raise ChangeError(
                "source-set copying requires include files beneath the input directory"
            ) from exc
        output[source_path] = (destination.parent / relative).resolve()
    return output


def apply_plan(
    plan_path: Path,
    destination: Path,
    audit_destination: Path | None = None,
) -> dict[str, Any]:
    plan = load_plan(plan_path)
    source = Path(plan["source"])
    audit_destination = audit_destination or _default_audit_path(destination)
    if source.resolve() == destination.resolve():
        raise ChangeError("in-place replacement is not allowed; choose a separate destination")
    if destination.exists():
        raise ChangeError(f"destination already exists: {destination}")
    if audit_destination.exists():
        raise ChangeError(f"audit destination already exists: {audit_destination}")
    if audit_destination.resolve() == destination.resolve():
        raise ChangeError("audit destination must be separate from the output deck")
    source_set = _source_set_for_plan(plan, source)
    document = source_set.documents[source.resolve()]
    if document.sha256 != plan["base_sha256"]:
        raise ChangeError("source changed after planning; create a new change plan")
    patches = plan.get("patches") or [plan["patch"]]
    replacements, updated_document, model_paths, source_diff, validation = _validated_plan_proposal(
        plan, source, document, source_set
    )
    output_source_set_sha256 = source_set.digest_with(replacements)
    if plan.get("proposed_source_set_sha256") not in {None, output_source_set_sha256}:
        raise ChangeError("updated source set does not match the plan's proposed digest")
    output_map = _source_set_output_map(source_set, destination)
    included_replacements = [path for path in replacements if path != source_set.root]
    if included_replacements and destination.resolve().parent == source_set.input_directory:
        raise ChangeError(
            "a plan that changes include files requires a separate destination directory"
        )
    output_paths = list(output_map.values())
    conflicts = [path for path in output_paths if path.exists()]
    if conflicts:
        raise ChangeError(f"source-set output already exists: {conflicts[0]}")
    if audit_destination.resolve() in {path.resolve() for path in output_paths}:
        raise ChangeError("audit destination must be separate from every source-set output")

    registry = load_registry()
    audit: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "operation": plan["operation"],
        "plan": {
            "path": str(plan_path.resolve()),
            "id": plan["plan_id"],
            "digest": plan["plan_digest"],
        },
        "source": str(source.resolve()),
        "destination": str(destination.resolve()),
        "base_sha256": document.sha256,
        "output_sha256": updated_document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "output_source_set_sha256": output_source_set_sha256,
        "changed_model_paths": model_paths,
        "affected_files": [str(output_map[path]) for path in replacements],
        "output_files": [str(path) for path in output_paths],
        "inputs": plan.get("inputs", []),
        "source_diff": source_diff,
        "validation": validation,
        "registered_baseline": registry["target"],
        "run_directory": None,
    }
    audit_digest = _plan_digest(audit)
    audit["audit_digest"] = audit_digest
    audit["audit_id"] = audit_digest[:16]
    written: list[Path] = []
    try:
        for source_path, output_path in output_map.items():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            raw = replacements.get(source_path, source_set.documents[source_path].raw)
            with output_path.open("xb") as stream:
                stream.write(raw)
            written.append(output_path)
        copied = SourceSet.read(destination.resolve(), destination.resolve().parent)
        if copied.sha256 != output_source_set_sha256:
            raise ChangeError("copied source set does not match the reviewed output digest")
        with audit_destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, ChangeError):
        audit_destination.unlink(missing_ok=True)
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return {
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
        "source": str(source.resolve()),
        "destination": str(destination.resolve()),
        "base_sha256": document.sha256,
        "output_sha256": updated_document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "output_source_set_sha256": output_source_set_sha256,
        "changed_model_paths": audit["changed_model_paths"],
        "changed_line": patches[0]["line"],
        "changed_lines": [patch["line"] for patch in patches],
        "output_files": audit["output_files"],
        "inputs": audit["inputs"],
        "validation": validation,
        "audit": str(audit_destination.resolve()),
        "audit_id": audit["audit_id"],
        "audit_digest": audit["audit_digest"],
        "preview": plan["preview"],
    }
