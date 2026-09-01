"""Conservative semantic records for the documented FE vertical slice."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from .document import Diagnostic, SourceLine


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
    status: str = "unresolved"
    target_entity_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "kind": self.kind,
            "source_entity_id": self.source_entity_id,
            "target_key": self.target_key,
            "location": self.location.as_dict(),
            "status": self.status,
            "target_entity_ids": list(self.target_entity_ids),
        }
        if self.attributes:
            result["attributes"] = self.attributes
        return result


@dataclass
class SemanticIndex:
    entities: list[SemanticEntity] = field(default_factory=list)
    references: list[SemanticReference] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

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
                "resolved_references": sum(item.status == "resolved" for item in self.references),
                "unresolved_references": sum(item.status == "unresolved" for item in self.references),
                "ambiguous_references": sum(item.status == "ambiguous" for item in self.references),
                "type_mismatches": sum(item.status == "type-mismatch" for item in self.references),
                "entities_by_kind": dict(sorted(counts.items())),
            },
        }

    def resolve(self) -> None:
        by_key: dict[str, list[SemanticEntity]] = {}
        for entity in self.entities:
            by_key.setdefault(entity.key, []).append(entity)

        for key, definitions in by_key.items():
            if len(definitions) > 1 and definitions[0].kind in {"node", "element"}:
                for duplicate in definitions[1:]:
                    self.diagnostics.append(Diagnostic(
                        code="BSAM-E300",
                        severity="error",
                        message=f"duplicate semantic entity {key}",
                        line=duplicate.location.line,
                        source=duplicate.location.source,
                    ))

        resolved: list[SemanticReference] = []
        for reference in self.references:
            matches = by_key.get(reference.target_key, [])
            target_kind = reference.target_key.rsplit("/", 1)[-1].split(":", 1)[0]
            if matches and (len(matches) == 1 or target_kind.endswith("-set")):
                status = "resolved"
            elif matches:
                status = "ambiguous"
            else:
                target_scope, target_tail = _split_key(reference.target_key)
                _target_kind, target_name = target_tail.split(":", 1)
                wrong_type = [
                    item for item in self.entities
                    if _split_key(item.key)[0] == target_scope and item.name.casefold() == target_name
                ]
                status = "type-mismatch" if wrong_type else "unresolved"
            resolved.append(replace(
                reference,
                status=status,
                target_entity_ids=tuple(item.id for item in matches),
            ))
            if status != "resolved":
                code = {
                    "unresolved": "BSAM-E301",
                    "type-mismatch": "BSAM-E302",
                    "ambiguous": "BSAM-E303",
                }[status]
                self.diagnostics.append(Diagnostic(
                    code=code,
                    severity="error",
                    message=f"{status} semantic reference to {reference.target_key}",
                    line=reference.location.line,
                    source=reference.location.source,
                ))
        self.references = resolved


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


def _split_key(key: str) -> tuple[str | None, str]:
    if "/" not in key:
        return None, key
    return tuple(key.rsplit("/", 1))  # type: ignore[return-value]


def _key(kind: str, name: str, cluster: str | None) -> str:
    local = f"{kind}:{name.casefold()}"
    return f"cluster:{cluster.casefold()}/{local}" if cluster else local


def _entity(index: SemanticIndex, kind: str, name: str, source: str, line: SourceLine,
            cluster: str | None,
            attributes: dict[str, Any] | None = None) -> SemanticEntity:
    key = _key(kind, name, cluster)
    values = dict(attributes or {})
    if cluster:
        values["cluster"] = cluster
    entity = SemanticEntity(
        id=f"{key}@{source}:{line.number}",
        key=key,
        kind=kind,
        name=name,
        location=_location(source, line),
        attributes=values,
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
        cluster: str | None = None
        for command_line, body in _command_spans(lines):
            command = command_line.text.lstrip().split(",", 1)[0].upper()[:5]
            options = _options(command_line)
            records = [line for line in body if line.stripped and not line.stripped.startswith("**")]

            if command == "*NAME" and records:
                cluster = records[0].stripped.casefold()
                continue

            if command == "*NODE":
                nset = options.get("NSET")
                if nset:
                    _entity(index, "node-set", nset, source, command_line, cluster, {
                        "definition": "implicit-command-membership",
                    })
                for line in records:
                    values = _fields(line.text)
                    if len(values) < 4 or not values[0].isdigit():
                        continue
                    node = _entity(index, "node", values[0], source, line, cluster, {
                        "coordinates": values[1:4],
                    })
                    if nset:
                        _reference(index, node, "member-of", _key("node-set", nset, cluster), source, line)

            elif command == "*ELEM":
                elset = options.get("ELSET")
                element_type = options.get("TYPE")
                if elset:
                    _entity(index, "element-set", elset, source, command_line, cluster, {
                        "definition": "implicit-command-membership",
                    })
                for line in records:
                    values = _fields(line.text)
                    if len(values) < 2 or not values[0].isdigit():
                        continue
                    element = _entity(index, "element", values[0], source, line, cluster, {
                        "element_type": element_type,
                        "connectivity": values[1:],
                    })
                    for position, label in enumerate(values[1:], start=1):
                        if label.isdigit():
                            _reference(index, element, "connectivity", _key("node", label, cluster), source, line, {
                                "position": position,
                            })
                    if elset:
                        _reference(index, element, "member-of", _key("element-set", elset, cluster), source, line)

            elif command in {"*NSET", "*ELSE"}:
                entity_kind = "node-set" if command == "*NSET" else "element-set"
                member_kind = "node" if command == "*NSET" else "element"
                option_name = "NSET" if command == "*NSET" else "ELSET"
                name = options.get(option_name)
                if not name:
                    continue
                entity = _entity(index, entity_kind, name, source, command_line, cluster, {
                    "mode": "generate" if "GENERATE" in options else "box" if "BOX" in options else "explicit",
                })
                if "GENERATE" not in options and "BOX" not in options:
                    for line in records:
                        for label in _fields(line.text):
                            if label.isdigit():
                                _reference(index, entity, "contains", _key(member_kind, label, cluster), source, line)

            elif command == "*SECT":
                elset = options.get("ELSET")
                if elset:
                    section = _entity(index, "section", elset, source, command_line, cluster, {
                        "layers": options.get("LAYERS"),
                    })
                    _reference(index, section, "assigns-to", _key("element-set", elset, cluster), source, command_line)
    index.resolve()
    return index
