"""Conservative semantic records for the documented FE vertical slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .document import SourceLine


@dataclass(frozen=True)
class SourceLocation:
    source: str
    line: int
    byte_start: int
    byte_end: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "line": self.line,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
        }


@dataclass(frozen=True)
class SemanticEntity:
    id: str
    key: str
    kind: str
    name: str
    location: SourceLocation
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "key": self.key,
            "kind": self.kind,
            "name": self.name,
            "location": self.location.as_dict(),
        }
        if self.attributes:
            result["attributes"] = self.attributes
        return result


@dataclass(frozen=True)
class SemanticReference:
    id: str
    kind: str
    source_entity_id: str
    target_key: str
    location: SourceLocation
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "kind": self.kind,
            "source_entity_id": self.source_entity_id,
            "target_key": self.target_key,
            "location": self.location.as_dict(),
        }
        if self.attributes:
            result["attributes"] = self.attributes
        return result


@dataclass
class SemanticIndex:
    entities: list[SemanticEntity] = field(default_factory=list)
    references: list[SemanticReference] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for entity in self.entities:
            counts[entity.kind] = counts.get(entity.kind, 0) + 1
        return {
            "schema_version": "0.1.0",
            "coverage": "documented-fe-explicit-records",
            "entities": [item.as_dict() for item in self.entities],
            "references": [item.as_dict() for item in self.references],
            "summary": {
                "entities": len(self.entities),
                "references": len(self.references),
                "entities_by_kind": dict(sorted(counts.items())),
            },
        }


def _fields(text: str) -> list[str]:
    return [value.strip() for value in text.replace(",", " ").split() if value.strip()]


def _options(line: SourceLine) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for field in line.text[:240].split(",")[1:]:
        value = field.strip()
        if not value:
            continue
        if "=" in value:
            name, setting = value.split("=", 1)
            result[name.strip().upper()] = setting.strip()
        else:
            result[value.upper()] = None
    return result


def _location(source: str, line: SourceLine) -> SourceLocation:
    return SourceLocation(source, line.number, line.start, line.end)


def _entity(index: SemanticIndex, kind: str, name: str, source: str, line: SourceLine,
            attributes: dict[str, Any] | None = None) -> SemanticEntity:
    key = f"{kind}:{name.casefold()}"
    entity = SemanticEntity(
        id=f"{key}@{source}:{line.number}",
        key=key,
        kind=kind,
        name=name,
        location=_location(source, line),
        attributes=attributes or {},
    )
    index.entities.append(entity)
    return entity


def _reference(index: SemanticIndex, source_entity: SemanticEntity, kind: str,
               target_key: str, source: str, line: SourceLine,
               attributes: dict[str, Any] | None = None) -> None:
    ordinal = len(index.references) + 1
    index.references.append(SemanticReference(
        id=f"reference:{ordinal}",
        kind=kind,
        source_entity_id=source_entity.id,
        target_key=target_key,
        location=_location(source, line),
        attributes=attributes or {},
    ))


def _command_spans(lines: Iterable[SourceLine]) -> list[tuple[SourceLine, list[SourceLine]]]:
    active: SourceLine | None = None
    body: list[SourceLine] = []
    result: list[tuple[SourceLine, list[SourceLine]]] = []
    for line in lines:
        stripped = line.stripped
        if stripped.startswith("*") and not stripped.startswith("**"):
            if active is not None:
                result.append((active, body))
            active, body = line, []
        elif active is not None:
            body.append(line)
    if active is not None:
        result.append((active, body))
    return result


def build_semantic_index(sources: Iterable[tuple[Path, str, Iterable[SourceLine]]]) -> SemanticIndex:
    """Index only explicit FE records whose grammar is documented in the registry."""
    index = SemanticIndex()
    for _path, source, lines in sources:
        for command_line, body in _command_spans(lines):
            command = command_line.text.lstrip().split(",", 1)[0].upper()[:5]
            options = _options(command_line)
            records = [line for line in body if line.stripped and not line.stripped.startswith("**")]

            if command == "*NODE":
                nset = options.get("NSET")
                if nset:
                    _entity(index, "node-set", nset, source, command_line, {
                        "definition": "implicit-command-membership",
                    })
                for line in records:
                    values = _fields(line.text)
                    if len(values) < 4 or not values[0].isdigit():
                        continue
                    node = _entity(index, "node", values[0], source, line, {
                        "coordinates": values[1:4],
                    })
                    if nset:
                        _reference(index, node, "member-of", f"node-set:{nset.casefold()}", source, line)

            elif command == "*ELEM":
                elset = options.get("ELSET")
                element_type = options.get("TYPE")
                if elset:
                    _entity(index, "element-set", elset, source, command_line, {
                        "definition": "implicit-command-membership",
                    })
                for line in records:
                    values = _fields(line.text)
                    if len(values) < 2 or not values[0].isdigit():
                        continue
                    element = _entity(index, "element", values[0], source, line, {
                        "element_type": element_type,
                        "connectivity": values[1:],
                    })
                    for position, label in enumerate(values[1:], start=1):
                        if label.isdigit():
                            _reference(index, element, "connectivity", f"node:{label}", source, line, {
                                "position": position,
                            })
                    if elset:
                        _reference(index, element, "member-of", f"element-set:{elset.casefold()}", source, line)

            elif command in {"*NSET", "*ELSE"}:
                entity_kind = "node-set" if command == "*NSET" else "element-set"
                member_kind = "node" if command == "*NSET" else "element"
                option_name = "NSET" if command == "*NSET" else "ELSET"
                name = options.get(option_name)
                if not name:
                    continue
                entity = _entity(index, entity_kind, name, source, command_line, {
                    "mode": "generate" if "GENERATE" in options else "box" if "BOX" in options else "explicit",
                })
                if "GENERATE" not in options and "BOX" not in options:
                    for line in records:
                        for label in _fields(line.text):
                            if label.isdigit():
                                _reference(index, entity, "contains", f"{member_kind}:{label}", source, line)

            elif command == "*SECT":
                elset = options.get("ELSET")
                if elset:
                    section = _entity(index, "section", elset, source, command_line, {
                        "layers": options.get("LAYERS"),
                    })
                    _reference(index, section, "assigns-to", f"element-set:{elset.casefold()}", source, command_line)
    return index
