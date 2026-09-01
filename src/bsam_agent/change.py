"""Revision-bound minimal patches for existing BSAM key/value parameters."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .document import SourceDocument, SourceLine
from .mesh import MeshModel, import_ele, render_bsam_commands
from .registry import load_registry
from .source_set import SourceSet


PLAN_SCHEMA_VERSION = "1.6.0"
SUPPORTED_PLAN_SCHEMA_VERSIONS = {
    "1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", PLAN_SCHEMA_VERSION
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
    required = {"source", "base_sha256", "operation", "selector", "patch", "preview"}
    missing = sorted(required - plan.keys())
    if missing:
        raise ChangeError(f"change plan is missing required fields: {', '.join(missing)}")
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
) -> tuple[bytes, SourceDocument, str, str, dict[str, Any]]:
    """Re-derive a plan through registered typing and exact source selection."""
    operation = plan.get("operation")
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
        return updated, updated_document, model_path, source_diff, validation

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
    return updated, updated_document, model_path, source_diff, validation


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
    _, updated_document, model_path, source_diff, validation = _validated_plan_proposal(
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
        "changed_model_paths": [model_path],
        "affected_files": plan.get("affected_files", [str(source.resolve())]),
        "changes": plan.get("changes", [{
            "operation": "modify",
            "target": model_path,
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
    patch = plan["patch"]
    updated, updated_document, model_path, source_diff, validation = _validated_plan_proposal(
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
        "changed_model_paths": [model_path],
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
        "changed_line": patch["line"],
        "inputs": audit["inputs"],
        "validation": validation,
        "audit": str(audit_destination.resolve()),
        "audit_id": audit["audit_id"],
        "audit_digest": audit["audit_digest"],
        "preview": plan["preview"],
    }
