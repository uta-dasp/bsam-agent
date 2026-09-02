"""Revision-bound minimal patches for existing BSAM key/value parameters."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .document import SourceDocument, SourceLine
from .mesh import MeshModel, import_ele, render_bsam_commands
from .registry import load_registry
from .source_set import SourceSet


PLAN_SCHEMA_VERSION = "1.7.0"
SUPPORTED_PLAN_SCHEMA_VERSIONS = {
    "1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", "1.6.0",
    PLAN_SCHEMA_VERSION,
}
AUDIT_SCHEMA_VERSION = "1.0.0"


class ChangeError(ValueError):
    """Raised when a requested change cannot be planned or safely applied."""


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
        "summary": {
            "errors": sum(item.severity == "error" for item in diagnostics),
            "warnings": sum(item.severity == "warning" for item in diagnostics),
        },
    }


def _validate_raw_value(value: str) -> None:
    if any(character in value for character in "\r\n\x00,"):
        raise ChangeError("replacement value must be a single non-comma record value")
    if not value.strip():
        raise ChangeError("replacement value must not be empty")


def _cluster_boundary(document: SourceDocument, cluster: str) -> SourceLine:
    if not cluster.strip():
        raise ChangeError("cluster name must not be empty")
    matches: list[SourceLine] = []
    for block in (item for item in document.blocks() if item["name"] == "CLUSTERS"):
        final = block["end_line"] or len(document.lines)
        for index in range(block["start_line"], final):
            line = document.lines[index]
            if line.text.lstrip().upper()[:5] != "*NAME":
                continue
            name_line = next(
                (
                    item for item in document.lines[index + 1:final]
                    if item.stripped and not item.stripped.startswith("**")
                ),
                None,
            )
            if name_line is None or name_line.stripped.casefold() != cluster.casefold():
                continue
            boundary = next(
                (
                    item for item in document.lines[name_line.number:final]
                    if item.text.lstrip().upper()[:5] in {"*TYPE", "*STOP"}
                ),
                None,
            )
            if boundary is None:
                raise ChangeError(f"cluster {cluster} has no following *TYPE or *STOP boundary")
            matches.append(boundary)
    if not matches:
        raise ChangeError(f"cluster {cluster} was not found in the root deck")
    if len(matches) > 1:
        raise ChangeError(f"cluster name {cluster} is ambiguous in the root deck")
    return matches[0]


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

    document = source_set.documents[source_set.root]
    boundary = _cluster_boundary(document, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    record = (
        b"*NODE" + newline
        + f"{label},{coordinates[0]},{coordinates[1]},{coordinates[2]}".encode("latin-1")
        + newline
    )
    return {
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
    document = source_set.documents[source]
    updated = _patched_bytes(document, patch)
    updated_document = SourceDocument.from_bytes(updated, str(source))
    validation = _validation_result(source_set, {source: updated})
    if validation["summary"]["errors"]:
        messages = "; ".join(
            item["message"] for item in validation["diagnostics"] if item["severity"] == "error"
        )
        raise ChangeError(f"planned source set failed dependency validation: {messages}")
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source),
        "workspace_root": str(source_set.workspace_root),
        "base_sha256": document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_sha256": updated_document.sha256,
        "proposed_source_set_sha256": source_set.digest_with({source: updated}),
        "operation": operation,
        "selector": selector,
        "patch": patch,
        "changed_model_paths": [model_path],
        "affected_files": [str(source)],
        "changes": [{"operation": change_operation, "target": model_path, "summary": preview}],
        "source_diff": _source_diff(source, document.raw, updated),
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

    document = source_set.documents[source_set.root]
    boundary = _cluster_boundary(document, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    options = f"*ELEMENT,TYPE={requested_type}"
    if elset:
        options += f",ELSET={elset}"
    record = (
        options.encode("latin-1") + newline
        + (str(label) + "," + ",".join(map(str, node_labels))).encode("ascii") + newline
    )
    return {
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


def _delete_node_patch(source_set: SourceSet, cluster: str, label: int) -> dict[str, Any]:
    key = f"cluster:{cluster.casefold()}/node:{label}"
    semantic = source_set.semantic_index()
    matches = [item for item in semantic.entities if item.key == key]
    if not matches:
        raise ChangeError(f"node {label} was not found in cluster {cluster}")
    if len(matches) > 1:
        raise ChangeError(f"node {label} is ambiguous in cluster {cluster}")
    entity = matches[0]
    if entity.location.source != "<root>":
        raise ChangeError("deleting entities from included files is not yet supported")
    dependents = [item for item in semantic.references if item.target_key == key]
    if dependents:
        kinds = ", ".join(sorted({item.kind for item in dependents}))
        raise ChangeError(f"node {label} has dependent references ({kinds}); deletion is blocked")
    document = source_set.documents[source_set.root]
    line = document.lines[entity.location.line - 1]
    return {
        "start": line.start,
        "end": line.end,
        "line": line.number,
        "old": document.raw[line.start:line.end].decode("latin-1"),
        "new": "",
    }


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

    document = source_set.documents[source_set.root]
    boundary = _cluster_boundary(document, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    command = "*NSET,NSET=" if member_kind == "node" else "*ELSET,ELSET="
    record = (
        (command + name).encode("latin-1") + newline
        + ",".join(map(str, members)).encode("ascii") + newline
    )
    return {
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
    document = source_set.documents[source_set.root]
    boundary = _cluster_boundary(document, cluster)
    newline = next((line.newline for line in document.lines if line.newline), b"\n")
    rendered = render_bsam_commands(mesh, newline)
    return ({
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
    block_by_name = {item["canonical"].upper(): item["id"] for item in registry["top_level_blocks"]}
    block_id = block_by_name.get(block_name.upper())
    if block_id is None:
        raise ChangeError(f"unknown registered block: {block_name}")
    requested = construct_name.upper()
    if not requested.startswith("*"):
        requested = "*" + requested
    matches = [
        item for item in registry["nested_constructs"]
        if item["parent_block_id"] == block_id and item["canonical"].upper() == requested
    ]
    if not matches:
        raise ChangeError(f"unknown registered construct {construct_name} in {block_name}")
    return matches[0]


def _validate_replacement(construct: dict[str, Any], parameter: str, value: str) -> None:
    parameters = {item["name"].lower(): item for item in construct["parameters"]}
    definition = parameters.get(parameter.lower())
    if definition is None:
        raise ChangeError(
            f"parameter {parameter} is not registered for {construct['canonical']}; untyped edits are blocked"
        )
    value_type = definition["value_type"].lower()
    try:
        if "integer" in value_type:
            parsed: int | float = int(value)
        elif "real" in value_type:
            parsed = float(value)
        else:
            parsed = 0
    except ValueError as exc:
        raise ChangeError(f"value {value!r} is not a valid {definition['value_type']}") from exc
    if value_type.startswith("positive-") and parsed <= 0:
        raise ChangeError(f"value for {parameter} must be positive")
    allowed = definition.get("allowed_values")
    if allowed is not None and value.lower() not in {str(item).lower() for item in allowed}:
        raise ChangeError(f"value for {parameter} must be one of: {', '.join(map(str, allowed))}")


def _find_construct_lines(
    document: SourceDocument,
    block_name: str,
    construct: dict[str, Any],
    occurrence: int,
) -> tuple[int, int]:
    if occurrence < 1:
        raise ChangeError("occurrence must be at least 1")
    blocks = [item for item in document.blocks() if item["name"].upper() == block_name.upper()]
    if not blocks:
        raise ChangeError(f"block {block_name} was not found")
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
            f"construct {construct['canonical']} occurrence {occurrence} was not found; found {len(matches)}"
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
                raise ChangeError(f"parameter {parameter} has an empty value on line {line.number}")
            spans.append((line.start + value_start, line.start + value_end))
            cursor = value_end
            continue
        cursor = found + 1


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
) -> dict[str, Any]:
    _validate_raw_value(value)
    source = source.resolve()
    source_set = SourceSet.read(source, workspace_root)
    document = source_set.documents[source]
    construct = _construct_record(block, construct_name)
    _validate_replacement(construct, parameter, value)
    start_line, end_line = _find_construct_lines(document, block, construct, occurrence)
    candidates: list[tuple[SourceLine, int, int]] = []
    for line in document.lines[start_line:end_line]:
        candidates.extend((line, *span) for span in _value_spans(line, parameter))
    if not candidates:
        raise ChangeError(
            f"parameter {parameter} was not found in {construct['canonical']} occurrence {occurrence}"
        )
    if len(candidates) > 1:
        lines = ", ".join(str(item[0].number) for item in candidates)
        raise ChangeError(f"parameter {parameter} is ambiguous in the selected construct (lines {lines})")
    line, start, end = candidates[0]
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
    updated = _patched_bytes(document, patch)
    updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
    validation = _validation_result(source_set, {source: updated})
    if validation["summary"]["errors"]:
        messages = "; ".join(item["message"] for item in validation["diagnostics"] if item["severity"] == "error")
        raise ChangeError(f"planned source set failed dependency validation: {messages}")
    model_path = f"{block.upper()}.{construct['canonical']}[{occurrence}].{parameter}"
    preview = f"line {line.number}: {parameter} = {old_bytes.decode('latin-1')} -> {value}"
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source": str(source.resolve()),
        "workspace_root": str(source_set.workspace_root),
        "base_sha256": document.sha256,
        "base_source_set_sha256": source_set.sha256,
        "proposed_sha256": updated_document.sha256,
        "proposed_source_set_sha256": source_set.digest_with({source: updated}),
        "operation": "set-existing-parameter",
        "selector": {
            "block": block.upper(),
            "construct": construct["canonical"],
            "construct_occurrence": occurrence,
            "parameter": parameter,
        },
        "patch": patch,
        "changed_model_paths": [model_path],
        "affected_files": [str(source.resolve())],
        "changes": [{
            "operation": "modify",
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


def write_plan(plan: dict[str, Any], destination: Path) -> None:
    if destination.exists():
        raise ChangeError(f"plan destination already exists: {destination}")
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(plan, indent=2, sort_keys=True) + "\n")


def load_plan(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        plan = json.load(stream)
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


def _validated_plan_proposal(
    plan: dict[str, Any],
    source: Path,
    document: SourceDocument,
    source_set: SourceSet,
) -> tuple[bytes, SourceDocument, list[str], str, dict[str, Any]]:
    """Re-derive a plan through registered typing and exact source selection."""
    operation = plan.get("operation")
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
            updated,
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
            updated,
            updated_document,
            expected["changed_model_paths"],
            expected["source_diff"],
            expected["validation"],
        )

    if operation in {
        "add-node", "add-element", "delete-node", "create-set", "add-set-members", "import-mesh"
    }:
        selector = plan.get("selector")
        if not isinstance(selector, dict):
            raise ChangeError("change plan is missing its selector")
        try:
            cluster = str(selector["cluster"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ChangeError(f"{operation} selector is malformed") from exc
        if operation in {"add-node", "add-element", "delete-node"}:
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
        updated = _patched_bytes(document, patch)
        updated_document = SourceDocument.from_bytes(updated, str(source.resolve()))
        source_diff = _source_diff(source, document.raw, updated)
        validation = _validation_result(source_set, {source.resolve(): updated})
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
        if plan.get("affected_files") != [str(source.resolve())]:
            raise ChangeError("change plan affected files do not match its source")
        return updated, updated_document, [model_path], source_diff, validation

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
    start_line, end_line = _find_construct_lines(document, block, construct, occurrence)
    candidates: list[tuple[SourceLine, int, int]] = []
    for line in document.lines[start_line:end_line]:
        candidates.extend((line, *span) for span in _value_spans(line, parameter))
    if len(candidates) != 1:
        raise ChangeError("planned parameter no longer resolves to one exact registered value")
    line, start, end = candidates[0]
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
    model_path = f"{block.upper()}.{construct['canonical']}[{occurrence}].{parameter}"
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
    return updated, updated_document, [model_path], source_diff, validation


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
    _, updated_document, model_paths, source_diff, validation = _validated_plan_proposal(
        plan, source, document, source_set
    )
    proposed_source_set_sha256 = source_set.digest_with({source.resolve(): updated_document.raw})
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
    if len(source_set.documents) > 1 and destination.resolve().parent != source.resolve().parent:
        raise ChangeError(
            "a deck with include files must be written in its original input directory; "
            "source-set copying is not implemented"
        )
    document = source_set.documents[source.resolve()]
    if document.sha256 != plan["base_sha256"]:
        raise ChangeError("source changed after planning; create a new change plan")
    patches = plan.get("patches") or [plan["patch"]]
    updated, updated_document, model_paths, source_diff, validation = _validated_plan_proposal(
        plan, source, document, source_set
    )
    output_source_set_sha256 = source_set.digest_with({source.resolve(): updated})
    if plan.get("proposed_source_set_sha256") not in {None, output_source_set_sha256}:
        raise ChangeError("updated source set does not match the plan's proposed digest")

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
        "affected_files": [str(destination.resolve())],
        "inputs": plan.get("inputs", []),
        "source_diff": source_diff,
        "validation": validation,
        "registered_baseline": registry["target"],
        "run_directory": None,
    }
    audit_digest = _plan_digest(audit)
    audit["audit_digest"] = audit_digest
    audit["audit_id"] = audit_digest[:16]
    with destination.open("xb") as stream:
        stream.write(updated)
    try:
        with audit_destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    except OSError:
        destination.unlink(missing_ok=True)
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
        "inputs": audit["inputs"],
        "validation": validation,
        "audit": str(audit_destination.resolve()),
        "audit_id": audit["audit_id"],
        "audit_digest": audit["audit_digest"],
        "preview": plan["preview"],
    }
