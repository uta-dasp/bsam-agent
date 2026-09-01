"""Strict importer for manually prepared Abaqus-style BSAM mesh interchange files."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MeshImportError(ValueError):
    """Raised when a mesh interchange file is invalid or unsupported."""


def _fields(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _integer(value: str, line: int, role: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise MeshImportError(f"line {line}: {role} must be an integer") from exc
    if result <= 0:
        raise MeshImportError(f"line {line}: {role} must be positive")
    return result


def _real(value: str, line: int, role: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise MeshImportError(f"line {line}: {role} must be a real number") from exc
    if not math.isfinite(result):
        raise MeshImportError(f"line {line}: {role} must be finite")
    return result


def _heading(text: str) -> tuple[str, dict[str, str | None]]:
    parts = [item.strip() for item in text.split(",")]
    command = parts[0].upper()
    options: dict[str, str | None] = {}
    for part in parts[1:]:
        if not part:
            continue
        if "=" in part:
            name, value = part.split("=", 1)
            options[name.strip().upper()] = value.strip()
        else:
            options[part.upper()] = None
    return command, options


@dataclass(frozen=True)
class MeshNode:
    label: int
    coordinates: tuple[float, float, float]
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "coordinates": list(self.coordinates), "line": self.line}


@dataclass(frozen=True)
class MeshElement:
    label: int
    element_type: str
    connectivity: tuple[int, ...]
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "element_type": self.element_type,
            "connectivity": list(self.connectivity),
            "line": self.line,
        }


@dataclass(frozen=True)
class MeshSet:
    kind: str
    name: str
    members: tuple[int, ...]
    generated: bool
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "members": list(self.members),
            "generated": self.generated,
            "line": self.line,
        }


@dataclass(frozen=True)
class MeshSurface:
    name: str
    surface_type: str
    facets: tuple[tuple[str, str], ...]
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "surface_type": self.surface_type,
            "facets": [{"element_set": item[0], "side": item[1]} for item in self.facets],
            "line": self.line,
        }


@dataclass(frozen=True)
class MeshOrientation:
    element_label: int
    v1: tuple[float, float, float]
    v3: tuple[float, float, float]
    fiber_volume: float
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "element_label": self.element_label,
            "v1": list(self.v1),
            "v3": list(self.v3),
            "fiber_volume": self.fiber_volume,
            "line": self.line,
        }


@dataclass(frozen=True)
class MeshModel:
    source: str
    sha256: str
    dimensions: tuple[int, ...] | None
    nodes: tuple[MeshNode, ...]
    elements: tuple[MeshElement, ...]
    sets: tuple[MeshSet, ...]
    surfaces: tuple[MeshSurface, ...]
    orientation_name: str | None
    orientations: tuple[MeshOrientation, ...]

    def as_dict(self) -> dict[str, Any]:
        node_sets = sum(item.kind == "node" for item in self.sets)
        element_sets = sum(item.kind == "element" for item in self.sets)
        return {
            "schema_version": "0.1.0",
            "format": "abaqus-style-ele",
            "provenance": {"source": self.source, "sha256": self.sha256},
            "dimensions": list(self.dimensions) if self.dimensions is not None else None,
            "nodes": [item.as_dict() for item in self.nodes],
            "elements": [item.as_dict() for item in self.elements],
            "sets": [item.as_dict() for item in self.sets],
            "surfaces": [item.as_dict() for item in self.surfaces],
            "orientation": {
                "name": self.orientation_name,
                "records": [item.as_dict() for item in self.orientations],
            } if self.orientation_name is not None else None,
            "summary": {
                "nodes": len(self.nodes),
                "elements": len(self.elements),
                "node_sets": node_sets,
                "element_sets": element_sets,
                "surfaces": len(self.surfaces),
                "orientations": len(self.orientations),
                "element_types": sorted({item.element_type for item in self.elements}),
            },
        }


def _spans(lines: list[str]) -> list[tuple[int, str, list[tuple[int, str]]]]:
    result: list[tuple[int, str, list[tuple[int, str]]]] = []
    active_line: int | None = None
    active_heading = ""
    body: list[tuple[int, str]] = []
    for number, text in enumerate(lines, start=1):
        stripped = text.strip()
        if not stripped or stripped.startswith("**"):
            continue
        if stripped.startswith("*"):
            if active_line is not None:
                result.append((active_line, active_heading, body))
            active_line, active_heading, body = number, stripped, []
        elif active_line is None:
            raise MeshImportError(f"line {number}: data appears before the first keyword")
        else:
            body.append((number, stripped))
    if active_line is not None:
        result.append((active_line, active_heading, body))
    return result


def _generated_members(body: list[tuple[int, str]]) -> tuple[int, ...]:
    result: list[int] = []
    for line, text in body:
        values = _fields(text)
        if len(values) != 3:
            raise MeshImportError(f"line {line}: generated set row requires first,last,increment")
        first, last, increment = (int(item) for item in values)
        if first <= 0 or last <= 0 or increment == 0 or (last - first) * increment < 0:
            raise MeshImportError(f"line {line}: generated set range is invalid")
        stop = last + (1 if increment > 0 else -1)
        expanded = list(range(first, stop, increment))
        if len(result) + len(expanded) > 10_000_000:
            raise MeshImportError("generated set exceeds the importer safety limit")
        result.extend(expanded)
    return tuple(result)


def import_ele(path: Path) -> MeshModel:
    path = path.resolve()
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MeshImportError("mesh file must be UTF-8 compatible text") from exc

    dimensions: tuple[int, ...] | None = None
    nodes: list[MeshNode] = []
    elements: list[MeshElement] = []
    sets: list[MeshSet] = []
    surfaces: list[MeshSurface] = []
    orientations: list[MeshOrientation] = []
    orientation_name: str | None = None

    for heading_line, heading, body in _spans(text.splitlines()):
        command, options = _heading(heading)
        if command == "*DIMENSIONS":
            if dimensions is not None or len(body) != 1:
                raise MeshImportError(f"line {heading_line}: *DIMENSIONS requires one unique row")
            dimensions = tuple(_integer(item, body[0][0], "dimension") for item in _fields(body[0][1]))
        elif command == "*NODE":
            for line, record in body:
                values = _fields(record)
                if len(values) != 4:
                    raise MeshImportError(f"line {line}: node row requires label,x,y,z")
                nodes.append(MeshNode(
                    _integer(values[0], line, "node label"),
                    tuple(_real(item, line, "coordinate") for item in values[1:4]),  # type: ignore[arg-type]
                    line,
                ))
        elif command == "*ELEMENT":
            element_type = options.get("TYPE")
            if not element_type:
                raise MeshImportError(f"line {heading_line}: *ELEMENT requires TYPE")
            for line, record in body:
                values = _fields(record)
                if len(values) < 2:
                    raise MeshImportError(f"line {line}: element row requires label and connectivity")
                elements.append(MeshElement(
                    _integer(values[0], line, "element label"),
                    element_type.upper(),
                    tuple(_integer(item, line, "connectivity label") for item in values[1:]),
                    line,
                ))
        elif command in {"*NSET", "*ELSET"}:
            kind = "node" if command == "*NSET" else "element"
            option = "NSET" if kind == "node" else "ELSET"
            name = options.get(option)
            if not name:
                raise MeshImportError(f"line {heading_line}: {command} requires {option}")
            generated = "GENERATE" in options
            members = _generated_members(body) if generated else tuple(
                _integer(item, line, f"{kind}-set member")
                for line, record in body for item in _fields(record)
            )
            sets.append(MeshSet(kind, name, members, generated, heading_line))
        elif command == "*SURFACE":
            name = options.get("NAME")
            surface_type = options.get("TYPE")
            if not name or not surface_type:
                raise MeshImportError(f"line {heading_line}: *SURFACE requires NAME and TYPE")
            facets: list[tuple[str, str]] = []
            for line, record in body:
                values = _fields(record)
                if len(values) != 2:
                    raise MeshImportError(f"line {line}: surface row requires element-set and side")
                facets.append((values[0], values[1].upper()))
            surfaces.append(MeshSurface(name, surface_type, tuple(facets), heading_line))
        elif command == "*ORIENTATION":
            if orientation_name is not None:
                raise MeshImportError(f"line {heading_line}: multiple orientation blocks are unsupported")
            orientation_name = options.get("NAME")
            if not orientation_name:
                raise MeshImportError(f"line {heading_line}: *ORIENTATION requires NAME")
            for line, record in body:
                values = _fields(record)
                if len(values) != 8:
                    raise MeshImportError(
                        f"line {line}: orientation row requires element,v1(3),v3(3),fiber-volume"
                    )
                orientations.append(MeshOrientation(
                    _integer(values[0], line, "orientation element label"),
                    tuple(_real(item, line, "V1 component") for item in values[1:4]),  # type: ignore[arg-type]
                    tuple(_real(item, line, "V3 component") for item in values[4:7]),  # type: ignore[arg-type]
                    _real(values[7], line, "fiber volume"),
                    line,
                ))
        else:
            raise MeshImportError(f"line {heading_line}: unsupported mesh keyword {command}")

    _validate_mesh(dimensions, nodes, elements, sets, surfaces, orientations)
    return MeshModel(
        str(path), hashlib.sha256(raw).hexdigest().upper(), dimensions,
        tuple(nodes), tuple(elements), tuple(sets), tuple(surfaces),
        orientation_name, tuple(orientations),
    )


def _validate_mesh(
    dimensions: tuple[int, ...] | None,
    nodes: list[MeshNode],
    elements: list[MeshElement],
    sets: list[MeshSet],
    surfaces: list[MeshSurface],
    orientations: list[MeshOrientation],
) -> None:
    node_labels = [item.label for item in nodes]
    element_labels = [item.label for item in elements]
    if len(set(node_labels)) != len(node_labels):
        raise MeshImportError("duplicate node labels")
    if len(set(element_labels)) != len(element_labels):
        raise MeshImportError("duplicate element labels")
    node_keys, element_keys = set(node_labels), set(element_labels)
    for element in elements:
        missing = sorted(set(element.connectivity) - node_keys)
        if missing:
            raise MeshImportError(
                f"line {element.line}: element {element.label} references missing nodes {missing}"
            )
    set_keys: set[tuple[str, str]] = set()
    for mesh_set in sets:
        key = (mesh_set.kind, mesh_set.name.casefold())
        if key in set_keys:
            raise MeshImportError(f"duplicate {mesh_set.kind} set name {mesh_set.name}")
        set_keys.add(key)
        allowed = node_keys if mesh_set.kind == "node" else element_keys
        missing = sorted(set(mesh_set.members) - allowed)
        if missing:
            raise MeshImportError(
                f"line {mesh_set.line}: {mesh_set.kind} set {mesh_set.name} has missing members {missing}"
            )
    element_set_names = {item.name.casefold() for item in sets if item.kind == "element"}
    for surface in surfaces:
        for name, _side in surface.facets:
            if name.casefold() not in element_set_names:
                raise MeshImportError(
                    f"line {surface.line}: surface {surface.name} references missing element set {name}"
                )
    for orientation in orientations:
        if orientation.element_label not in element_keys:
            raise MeshImportError(
                f"line {orientation.line}: orientation references missing element {orientation.element_label}"
            )
        v1_norm = math.sqrt(sum(item * item for item in orientation.v1))
        v3_norm = math.sqrt(sum(item * item for item in orientation.v3))
        dot = sum(a * b for a, b in zip(orientation.v1, orientation.v3))
        if v1_norm == 0 or v3_norm == 0 or abs(dot) > 1e-8 * v1_norm * v3_norm:
            raise MeshImportError(f"line {orientation.line}: V1 and V3 must be nonzero and normal")
    if dimensions is not None:
        if len(dimensions) != 4:
            raise MeshImportError("*DIMENSIONS must contain node, element, node-set, orientation-block counts")
        actual = (len(nodes), len(elements), sum(item.kind == "node" for item in sets), int(bool(orientations)))
        if dimensions != actual:
            raise MeshImportError(f"*DIMENSIONS declares {dimensions}, but imported counts are {actual}")
