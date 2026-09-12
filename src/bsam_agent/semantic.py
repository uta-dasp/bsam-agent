"""Conservative semantic records for documented FE and control constructs."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from pathlib import Path
import re
from typing import Any, Iterable

from .capabilities import canonical_parameter, match_nested_construct, nested_constructs, operational_support
from .document import Diagnostic, SourceLine
from .registry import load_registry


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


@dataclass(frozen=True)
class RegisteredConstruct:
    """A lossless semantic view over one registry-matched construct occurrence."""

    id: str
    capability_id: str
    canonical: str
    occurrence: int
    location: SourceLocation
    parameters: dict[str, tuple[dict[str, Any], ...]] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)
    operations: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "capability_id": self.capability_id,
            "canonical": self.canonical,
            "occurrence": self.occurrence,
            "location": self.location.as_dict(),
            "parameters": {name: list(values) for name, values in self.parameters.items()},
            "defaults": self.defaults,
            "operations": self.operations,
        }
        if self.attributes:
            result["attributes"] = self.attributes
        return result


@dataclass
class SemanticIndex:
    entities: list[SemanticEntity] = field(default_factory=list)
    references: list[SemanticReference] = field(default_factory=list)
    capability_records: list[RegisteredConstruct] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    _entity_identity_counts: dict[str, int] = field(default_factory=dict, repr=False)
    _reference_identity_counts: dict[str, int] = field(default_factory=dict, repr=False)

    def entity_id(self, base: str) -> str:
        """Allocate a stable occurrence ID without changing the semantic key."""
        occurrence = self._entity_identity_counts.get(base, 0) + 1
        self._entity_identity_counts[base] = occurrence
        return base if occurrence == 1 else f"{base}#{occurrence}"

    def reference_id(
        self, source_entity_id: str, kind: str, target_key: str,
        source: str, line: int,
    ) -> str:
        """Allocate an ID stable against unrelated references elsewhere in the model."""
        base = (
            f"reference:{kind}:{source_entity_id}->{target_key}"
            f"@{source}:{line}"
        )
        occurrence = self._reference_identity_counts.get(base, 0) + 1
        self._reference_identity_counts[base] = occurrence
        return base if occurrence == 1 else f"{base}#{occurrence}"

    def as_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for entity in self.entities:
            counts[entity.kind] = counts.get(entity.kind, 0) + 1
        return {
            "schema_version": "0.5.0",
            "coverage": "documented-fe-control-named-data-and-declaration-references",
            "entities": [item.as_dict() for item in self.entities],
            "references": [item.as_dict() for item in self.references],
            "capability_records": [item.as_dict() for item in self.capability_records],
            "summary": {
                "entities": len(self.entities),
                "references": len(self.references),
                "registered_constructs": len(self.capability_records),
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
            if len(definitions) > 1 and definitions[0].kind in {
                "node", "element", "cluster", "constitutive", "boundary-condition",
                "connection", "cluster-constitutive", "crack", "table", "user-function",
                "statistical-distribution", "failure",
                "material", "selection",
            }:
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


def _record_options(line: SourceLine) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in line.text[:500].split(","):
        if "=" not in field:
            continue
        name, value = field.split("=", 1)
        result[name.strip().casefold()] = value.strip()
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
        id=index.entity_id(f"{key}@{source}:{line.number}"),
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
    index.references.append(SemanticReference(
        id=index.reference_id(
            source_entity.id, kind, target_key, source, line.number,
        ),
        kind=kind,
        source_entity_id=source_entity.id,
        target_key=target_key,
        location=_location(source, line),
        attributes=attributes or {},
    ))


def _reference_once(index: SemanticIndex, source_entity: SemanticEntity, kind: str,
                    target_key: str, source: str, line: SourceLine,
                    attributes: dict[str, Any] | None = None) -> None:
    if any(
        reference.source_entity_id == source_entity.id
        and reference.kind == kind
        and reference.target_key == target_key
        for reference in index.references
    ):
        return
    _reference(index, source_entity, kind, target_key, source, line, attributes)


def augment_include_graph_semantics(
    index: SemanticIndex,
    files: Iterable[tuple[str, SourceLine | None]],
    references: Iterable[tuple[str, int, str | None, str | None, str]],
) -> None:
    """Link typed INCLUDE operations to stable workspace-relative source-file entities."""
    reference_items = tuple(references)
    if not reference_items:
        return
    file_entities: dict[str, SemanticEntity] = {}
    for label, first_line in files:
        key = _key("source-file", label, None)
        if first_line is None:
            base_id = f"{key}@{label}:1"
            entity = SemanticEntity(
                id=index.entity_id(base_id),
                key=key,
                kind="source-file",
                name=label,
                location=SourceLocation(label, 1, 0, 0),
                attributes={"role": "root" if label == "<root>" else "include"},
            )
            index.entities.append(entity)
        else:
            entity = _entity(
                index, "source-file", label, label, first_line, None,
                {"role": "root" if label == "<root>" else "include"},
            )
        file_entities[label] = entity

    for source, line_number, spelling, target, status in reference_items:
        matching_positions = [
            position for position, entity in enumerate(index.entities)
            if entity.kind == "include-operation"
            and entity.location.source == source
            and entity.location.line == line_number
        ]
        for position in matching_positions:
            operation = index.entities[position]
            attributes = {
                **operation.attributes,
                "graph_status": status,
                "target_source": target,
            }
            operation = replace(operation, attributes=attributes)
            index.entities[position] = operation
            if target is None or target not in file_entities or status not in {
                "resolved", "already-loaded",
            }:
                continue
            target_key = file_entities[target].key
            if any(
                item.source_entity_id == operation.id
                and item.kind == "includes-file"
                and item.target_key == target_key
                for item in index.references
            ):
                continue
            index.references.append(SemanticReference(
                id=index.reference_id(
                    operation.id, "includes-file", target_key,
                    operation.location.source, operation.location.line,
                ),
                kind="includes-file",
                source_entity_id=operation.id,
                target_key=target_key,
                location=operation.location,
                attributes={"spelling": spelling, "graph_status": status},
            ))


def _cluster_nodal_target_key(
    index: SemanticIndex, target: str, cluster: str, *, node_only: bool = False,
) -> tuple[str, str]:
    """Mirror BSAM's set-first target lookup without guessing missing names."""
    node_set_key = _key("node-set", target, cluster)
    if not node_only and any(item.key == node_set_key for item in index.entities):
        return node_set_key, "targets-node-set"
    if target.isdigit():
        return _key("node", target, cluster), "targets-node"
    return node_set_key, "targets-node-set"


def _set_member_entities(
    index: SemanticIndex, set_key: str, member_kind: str,
) -> list[SemanticEntity]:
    set_ids = {item.id for item in index.entities if item.key == set_key}
    entity_by_id = {item.id: item for item in index.entities}
    entity_by_key = {item.key: item for item in index.entities}
    result: list[SemanticEntity] = []
    seen: set[str] = set()
    for reference in index.references:
        member: SemanticEntity | None = None
        if reference.kind == "contains" and reference.source_entity_id in set_ids:
            member = entity_by_key.get(reference.target_key)
        elif reference.kind == "member-of" and reference.target_key == set_key:
            member = entity_by_id.get(reference.source_entity_id)
        if member is not None and member.kind == member_kind and member.key not in seen:
            seen.add(member.key)
            result.append(member)
    return result


def _bounded_generated_labels(start: int, end: int, increment: int) -> tuple[int, ...]:
    if increment == 0 or (end - start) * increment <= 0:
        return ()
    count = max(0, (abs(end - start) - 1) // abs(increment))
    if count > 100_000:
        return ()
    return tuple(range(start + increment, end, increment))


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


def _top_block_body(lines: tuple[SourceLine, ...], name: str) -> list[SourceLine]:
    start_tokens = {name}
    if name == "STATISTICAL":
        start_tokens.add("STATISTICAL DISTRIBUTIONS")
    start = next(
        (index for index, line in enumerate(lines) if line.stripped in start_tokens), None
    )
    if start is None:
        return []
    terminators = {f"END {name}"}
    if name == "STATISTICAL":
        terminators = {"END STATISTICAL DISTRIBUTIONS"}
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].stripped in terminators),
        len(lines),
    )
    return list(lines[start + 1:end])


_KEY_VALUE = re.compile(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*([^,\s]+)")


def _registered_parameter_values(
    construct: dict[str, Any], command_line: SourceLine, body: list[SourceLine], source: str,
) -> dict[str, tuple[dict[str, Any], ...]]:
    found: dict[str, list[dict[str, Any]]] = {}
    active_lines = [command_line, *(
        line for line in body if line.stripped and not line.stripped.startswith("**")
    )]
    for line in active_lines:
        searchable = line.text.split("#", 1)[0]
        for match in _KEY_VALUE.finditer(searchable):
            definition = canonical_parameter(construct, match.group(1))
            if definition is None:
                continue
            name = str(definition["name"])
            found.setdefault(name, []).append({
                "value": match.group(2),
                "spelling": match.group(1),
                "location": _location(source, line).as_dict(),
            })

    flag_parameters = [
        item for item in construct.get("parameters", []) if item.get("value_type") == "flag"
    ]
    if flag_parameters:
        for token in re.split(r"[\s,]+", command_line.text.split("#", 1)[0]):
            definition = canonical_parameter(construct, token)
            if definition not in flag_parameters:
                continue
            name = str(definition["name"])
            found.setdefault(name, []).append({
                "value": True,
                "spelling": token,
                "location": _location(source, command_line).as_dict(),
            })

    parameters = construct.get("parameters", [])
    if (
        len(parameters) == 1 and not found
        and construct.get("id") != "command.tolerance"
    ):
        record = next((line for line in active_lines[1:] if "=" not in line.text), None)
        if record is not None:
            definition = parameters[0]
            found[str(definition["name"])] = [{
                "value": record.stripped,
                "spelling": str(definition["name"]),
                "location": _location(source, record).as_dict(),
            }]
    return {name: tuple(values) for name, values in found.items()}


def _registered_record_parameter_values(
    construct: dict[str, Any], body: list[SourceLine], source: str,
) -> dict[str, tuple[dict[str, Any], ...]]:
    """Read a registry-declared repeated key/value record body."""
    found: dict[str, list[dict[str, Any]]] = {}
    for line in body:
        text = line.text.split("#", 1)[0].strip()
        if "=" not in text or text.startswith("**"):
            continue
        raw_name, raw_value = text.split("=", 1)
        definition = canonical_parameter(construct, raw_name.strip())
        if definition is None:
            continue
        name = str(definition["name"])
        value_type = str(definition["value_type"]).casefold()
        raw_values = (
            [item for item in re.split(r"[\s,]+", raw_value.strip()) if item]
            if value_type.endswith("-list") else [raw_value.strip()]
        )
        for raw in raw_values:
            value: Any = raw.casefold()
            if "integer" in value_type and raw.lstrip("+").isdigit():
                value = int(raw)
            found.setdefault(name, []).append({
                "value": value,
                "spelling": raw_name.strip(),
                "location": _location(source, line).as_dict(),
            })
    return {name: tuple(values) for name, values in found.items()}


def _validate_registered_values(
    index: SemanticIndex, construct: dict[str, Any],
    values: dict[str, tuple[dict[str, Any], ...]],
) -> None:
    if operational_support(construct)["static_validation"] != "verified":
        return
    definitions = {item["name"]: item for item in construct.get("parameters", [])}
    for name, occurrences in values.items():
        definition = definitions[name]
        value_type = str(definition["value_type"]).casefold()
        for occurrence in occurrences:
            raw = occurrence["value"]
            invalid = False
            try:
                numeric: int | float | None = None
                if "integer" in value_type:
                    numeric = int(str(raw))
                elif "real" in value_type:
                    numeric = _fortran_real(str(raw))
                if isinstance(numeric, float) and not math.isfinite(numeric):
                    invalid = True
                if value_type.startswith("positive-") and numeric is not None and numeric <= 0:
                    invalid = True
            except ValueError:
                invalid = True
            allowed = definition.get("allowed_values")
            if allowed is not None:
                raw_text = str(raw).casefold()
                allowed_text = [str(item).casefold() for item in allowed]
                prefix_matches = [item for item in allowed_text if item.startswith(raw_text)]
                if raw_text not in allowed_text and not (
                    len(raw_text) >= 3 and len(prefix_matches) == 1
                ):
                    invalid = True
            if invalid:
                location = occurrence["location"]
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310",
                    severity="error",
                    message=(
                        f"invalid {construct['canonical']} parameter {name}={raw!r}; "
                        f"expected {definition['value_type']}"
                    ),
                    line=location["line"],
                    source=location["source"],
                ))


def augment_registered_boundary_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Match BOUNDARY constructs and parameters from registry data without rewriting source."""
    all_lines = tuple(lines)
    constructs = nested_constructs("block.boundary")
    occurrences: dict[str, int] = {}
    for command_line, body in _command_spans(_top_block_body(all_lines, "BOUNDARY")):
        construct = match_nested_construct(command_line.text, constructs)
        if construct is None:
            continue
        capability_id = str(construct["id"])
        occurrences[capability_id] = occurrences.get(capability_id, 0) + 1
        occurrence = occurrences[capability_id]
        parameters = _registered_parameter_values(construct, command_line, body, source)
        defaults = {
            str(item["name"]): item["default"]
            for item in construct.get("parameters", []) if "default" in item
        }
        index.capability_records.append(RegisteredConstruct(
            id=f"{capability_id}[{occurrence}]@{source}:{command_line.number}",
            capability_id=capability_id,
            canonical=str(construct["canonical"]),
            occurrence=occurrence,
            location=_location(source, command_line),
            parameters=parameters,
            defaults=defaults,
            operations=operational_support(construct),
        ))
        if construct.get("body", {}).get("style") != "nested-records":
            _validate_registered_values(index, construct, parameters)


def augment_registered_top_level_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Expose simple top-level records selected entirely by registry shape."""
    all_lines = tuple(lines)
    for definition in load_registry()["top_level_blocks"]:
        parameters_defined = definition.get("parameters", [])
        body = definition.get("body")
        is_container = body is None and not parameters_defined
        is_single_record = (
            isinstance(body, dict)
            and body.get("style") == "single-record"
            and len(parameters_defined) == 1
        )
        variants = body.get("variants", []) if isinstance(body, dict) else []
        rows = variants[0].get("rows", []) if len(variants) == 1 else []
        fields = rows[0].get("fields", []) if len(rows) == 1 else []
        is_key_value_records = (
            isinstance(body, dict)
            and body.get("style") == "records"
            and len(rows) == 1
            and rows[0].get("repetition") == "repeated"
            and [item.get("name") for item in fields] == ["key", "value"]
        )
        if not (is_container or is_single_record or is_key_value_records):
            continue

        canonical = str(definition["canonical"])
        header = next(
            (line for line in all_lines if line.stripped == canonical), None
        )
        if header is None:
            continue
        capability_id = str(definition["id"])
        block_body = _top_block_body(all_lines, canonical)
        if is_single_record:
            parameters = _registered_parameter_values(
                definition, header, block_body, source,
            )
        elif is_key_value_records:
            parameters = _registered_record_parameter_values(
                definition, block_body, source,
            )
        else:
            parameters = {}
        defaults = {
            str(item["name"]): item["default"]
            for item in parameters_defined if "default" in item
        }
        attributes: dict[str, Any] = {}
        entity_kind = definition.get("entity_kind")
        if is_key_value_records and entity_kind:
            effective = dict(defaults)
            definitions = {
                str(item["name"]): item for item in parameters_defined
            }
            for name, values in parameters.items():
                value_type = str(definitions[name]["value_type"]).casefold()
                effective[name] = (
                    [item["value"] for item in values]
                    if value_type.endswith("-list") else values[-1]["value"]
                )
            entity_attributes: dict[str, Any] = {"effective_settings": effective}
            if operational_support(definition)["execute"] == "unsupported":
                entity_attributes["execution"] = "blocked"
            entity = _entity(
                index, str(entity_kind), "1", source, header, None,
                entity_attributes,
            )
            attributes = {
                "entity_id": entity.id,
                "syntax": "canonical-key-value",
            }
        index.capability_records.append(RegisteredConstruct(
            id=f"{capability_id}[1]@{source}:{header.number}",
            capability_id=capability_id,
            canonical=canonical,
            occurrence=1,
            location=_location(source, header),
            parameters=parameters,
            defaults=defaults,
            operations=operational_support(definition),
            attributes=(
                {"record_role": "container"} if is_container else attributes
            ),
        ))
        if (
            is_single_record
            and operational_support(definition)["static_validation"] == "verified"
        ):
            headers = [line for line in all_lines if line.stripped == canonical]
            terminators = {
                str(token) for token in definition.get("termination", {}).get("tokens", [])
            }
            header_index = next(
                (position for position, line in enumerate(all_lines) if line is header), None
            )
            end = None if header_index is None else next(
                (
                    line for line in all_lines[header_index + 1:]
                    if line.stripped in terminators
                ),
                None,
            )
            active_records = [
                line for line in block_body
                if line.stripped and not line.stripped.startswith(("#", "**"))
            ]
            if len(headers) != 1:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E390", severity="error",
                    message=f"{canonical} must occur exactly once; found {len(headers)}",
                    line=header.number, source=source,
                ))
            if end is None:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E390", severity="error",
                    message=f"{canonical} is missing an exact registered terminator",
                    line=header.number, source=source,
                ))
            elif len(active_records) != 1:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E390", severity="error",
                    message=(
                        f"{canonical} requires exactly one active data record; "
                        f"found {len(active_records)}"
                    ),
                    line=header.number, source=source,
                ))
        _validate_registered_values(index, definition, parameters)


def augment_crack_capability_records(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Type the fixed leading records of global FE crack declarations."""
    definition = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.crack"
    )
    body = [
        line for line in _top_block_body(tuple(lines), "CRACK")
        if line.stripped and not line.stripped.startswith(("#", "**"))
    ]
    header_positions = [
        position for position, line in enumerate(body)
        if not line.text[:1].isspace()
        and _fields(line.text)[:1] in (["101"], ["201"], ["301"])
    ]
    entities_by_line = {
        item.location.line: item for item in index.entities
        if item.kind == "crack" and item.location.source == source
    }

    def parameter(value: Any, spelling: str, line: SourceLine) -> dict[str, Any]:
        return {
            "value": value, "spelling": spelling,
            "location": _location(source, line).as_dict(),
        }

    defaults = {
        str(item["name"]): item["default"]
        for item in definition["parameters"] if "default" in item
    }
    for ordinal, position in enumerate(header_positions, start=1):
        end = (
            header_positions[ordinal]
            if ordinal < len(header_positions) else len(body)
        )
        header = body[position]
        entry = body[position + 1:end]
        positional = [line for line in entry if not line.stripped.startswith("*")]
        parameters: dict[str, tuple[dict[str, Any], ...]] = {
            "type": (parameter(int(_fields(header.text)[0]), "type", header),),
        }
        if positional:
            values = _fields(positional[0].text)
            if values and values[0].lstrip("+").isdigit():
                parameters["predefined_count"] = (
                    parameter(int(values[0]), "predefined_count", positional[0]),
                )
            if len(values) > 1 and values[1].lstrip("+").isdigit():
                parameters["maximum_count"] = (
                    parameter(int(values[1]), "maximum_count", positional[0]),
                )
        if len(positional) > 1:
            values = _fields(positional[1].text)
            if values and values[0].lstrip("+-").isdigit():
                parameters["n_gap"] = (
                    parameter(int(values[0]), "n_gap", positional[1]),
                )
        if len(positional) > 2:
            values = _fields(positional[2].text)
            if values:
                cluster_value: Any = (
                    int(values[0]) if values[0].lstrip("+").isdigit()
                    else values[0].casefold()
                )
                parameters["cluster"] = (
                    parameter(cluster_value, "cluster", positional[2]),
                )
        entity = entities_by_line.get(header.number)
        index.capability_records.append(RegisteredConstruct(
            id=f"block.crack[{ordinal}]@{source}:{header.number}",
            capability_id="block.crack",
            canonical="CRACK",
            occurrence=ordinal,
            location=_location(source, header),
            parameters=parameters,
            defaults=defaults,
            operations=operational_support(definition),
            attributes={
                "entity_id": entity.id if entity is not None else None,
                "syntax": "fixed-leading-records",
            },
        ))
        _validate_registered_values(index, definition, parameters)


def augment_numeric_user_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Cursor-parse deterministic numeric USER declarations and preserve blocked forms."""
    definition = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.user"
    )
    body = [
        line for line in _top_block_body(tuple(lines), "USER")
        if line.stripped and not line.stripped.startswith(("#", "**"))
    ]
    cursor = 0
    ordinal = 0

    def parameter(value: Any, spelling: str, line: SourceLine) -> dict[str, Any]:
        return {
            "value": value, "spelling": spelling,
            "location": _location(source, line).as_dict(),
        }

    while cursor < len(body):
        header = body[cursor]
        fields = _fields(header.text)
        if not fields or not fields[0].lstrip("+-").isdigit():
            break
        function_type = int(fields[0])
        if function_type <= 0:
            break
        ordinal += 1
        cursor += 1
        parameters: dict[str, tuple[dict[str, Any], ...]] = {
            "type": (parameter(function_type, "type", header),),
        }
        attributes: dict[str, Any] = {
            "type": function_type, "declaration_ordinal": ordinal,
        }
        complete = True

        if function_type == 100:
            if cursor >= len(body):
                complete = False
            else:
                file_line = body[cursor]
                cursor += 1
                external_file = file_line.text[:30].strip()
                parameters["external_file"] = (
                    parameter(external_file, "external_file", file_line),
                )
                attributes.update({
                    "external_file": external_file,
                    "preservation": "external-file-not-in-source-set",
                })
        elif function_type == 301:
            attributes["preservation"] = "blocked-sparse-matrix"
        elif function_type in {1, 2, 3, 4, 5, 101, 201}:
            if cursor >= len(body):
                complete = False
                count = -1
                count_line = header
            else:
                count_line = body[cursor]
                cursor += 1
                count_fields = _fields(count_line.text)
                try:
                    count = int(count_fields[0])
                except (IndexError, ValueError):
                    count = -1
                    complete = False
            if count >= 0:
                parameters["count"] = (parameter(count, "count", count_line),)
                attributes["count"] = count
            row_count = count + 1 if function_type == 1 else count
            row_width = 1 if function_type == 1 else 2
            if function_type == 201:
                row_width = 4
            data: list[list[float]] = []
            if function_type == 5 and complete:
                if cursor >= len(body):
                    complete = False
                else:
                    range_line = body[cursor]
                    cursor += 1
                    try:
                        range_values = [float(value) for value in _fields(range_line.text)[:2]]
                    except ValueError:
                        range_values = []
                    if len(range_values) != 2 or not all(map(math.isfinite, range_values)):
                        complete = False
                    else:
                        attributes["range"] = range_values
            coefficient_values: list[dict[str, Any]] = []
            if complete and row_count >= 0:
                for _row in range(row_count):
                    if cursor >= len(body):
                        complete = False
                        break
                    row_line = body[cursor]
                    cursor += 1
                    try:
                        row = [float(value) for value in _fields(row_line.text)[:row_width]]
                    except ValueError:
                        row = []
                    if len(row) != row_width or not all(map(math.isfinite, row)):
                        complete = False
                        break
                    data.append(row)
                    if function_type in {1, 2, 3, 4, 5}:
                        coefficient_values.extend(
                            parameter(value, "coefficient", row_line) for value in row
                        )
            attributes["data"] = data
            if coefficient_values:
                parameters["coefficient"] = tuple(coefficient_values)
            if function_type in {101, 201} and complete:
                x_values = [row[0] for row in data]
                monotonic = len(x_values) >= 2 and (
                    all(right > left for left, right in zip(x_values, x_values[1:]))
                    or all(right < left for left, right in zip(x_values, x_values[1:]))
                )
                if not monotonic:
                    complete = False
        else:
            attributes["preservation"] = "unsupported-type"
            complete = False

        attributes["complete"] = complete
        entity = _entity(
            index, "numeric-user-function", str(ordinal), source, header, None,
            attributes,
        )
        index.capability_records.append(RegisteredConstruct(
            id=f"block.user[{ordinal}]@{source}:{header.number}",
            capability_id="block.user",
            canonical="USER",
            occurrence=ordinal,
            location=_location(source, header),
            parameters=parameters,
            operations=operational_support(definition),
            attributes={
                "entity_id": entity.id,
                "syntax": "preservation-only" if function_type in {100, 301}
                else "inline-numeric",
                "complete": complete,
            },
        ))
        if not complete and function_type not in {100, 301}:
            _table_error(
                index, "BSAM-E380",
                f"numeric USER function {ordinal} has an incomplete or invalid type-{function_type} body",
                source, header,
            )
            break
        if function_type == 301:
            break


def _solver_parameter(
    definition: dict[str, Any], value: Any, spelling: str, source: str, line: SourceLine,
) -> dict[str, Any]:
    return {
        "value": value,
        "spelling": spelling,
        "location": _location(source, line).as_dict(),
    }


def augment_solver_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Parse authoritative current and legacy SOLVER record groups."""
    all_lines = tuple(lines)
    body = [
        line for line in _top_block_body(all_lines, "SOLVER")
        if line.stripped and not line.stripped.startswith(("#", "**"))
    ]
    if not body:
        return
    solver = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.solver"
    )
    definitions = {
        str(item["name"]).casefold(): item for item in solver["parameters"]
    }
    defaults = {
        str(item["name"]): item["default"]
        for item in solver["parameters"] if "default" in item
    }

    def add_record(
        ordinal: int, line: SourceLine, parameters: dict[str, list[dict[str, Any]]],
        syntax: str,
    ) -> None:
        frozen = {name: tuple(values) for name, values in parameters.items()}
        operations = operational_support(solver)
        if syntax == "legacy":
            operations = {**operations, "modify": "unsupported"}
        index.capability_records.append(RegisteredConstruct(
            id=f"block.solver[{ordinal}]@{source}:{line.number}",
            capability_id="block.solver",
            canonical="SOLVER",
            occurrence=ordinal,
            location=_location(source, line),
            parameters=frozen,
            defaults=defaults,
            operations=operations,
            attributes={"syntax": syntax},
        ))
        solver_type = next(iter(parameters.get("*type", [])), {}).get("value", "unknown")
        _entity(
            index, "solver", str(ordinal), source, line, None,
            {"type": solver_type, "syntax": syntax},
        )
        if syntax == "current":
            _validate_registered_values(index, solver, frozen)
            if str(solver_type).casefold() in {"pardiso", "cpardiso"}:
                for required in ("n_threads", "matrix_type"):
                    if required not in parameters:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E311",
                            severity="error",
                            message=f"current {solver_type} solver requires explicit {required}",
                            line=line.number,
                            source=source,
                        ))

    if body[0].stripped.casefold().startswith("*type"):
        cursor = 0
        ordinal = 0
        while cursor < len(body):
            header = body[cursor]
            if not header.stripped.casefold().startswith("*type"):
                break
            header_index = cursor
            ordinal += 1
            parameters: dict[str, list[dict[str, Any]]] = {}
            while cursor < len(body):
                line = body[cursor]
                text = line.text.split("#", 1)[0].strip()
                if cursor > header_index and text.casefold().startswith("*type"):
                    break
                if text.casefold() == "end solver":
                    cursor += 1
                    break
                if "=" in text:
                    spelling, raw = text.split("=", 1)
                    name = spelling.strip().casefold()
                    definition = definitions.get(name)
                    if definition is not None:
                        canonical = str(definition["name"])
                        parameters.setdefault(canonical, []).append(
                            _solver_parameter(definition, raw.strip(), spelling.strip(), source, line)
                        )
                cursor += 1
            add_record(ordinal, header, parameters, "current")
        return

    type_line = body[0]
    type_fields = _fields(type_line.text.split("#", 1)[0])
    if not type_fields:
        return
    parameters = {
        "*type": [_solver_parameter(definitions["*type"], type_fields[0], "type", source, type_line)]
    }
    if len(body) > 1:
        thread_fields = _fields(body[1].text.split("#", 1)[0])
        if thread_fields:
            parameters["n_threads"] = [
                _solver_parameter(definitions["n_threads"], thread_fields[0], "n_threads", source, body[1])
            ]
    if len(body) > 2:
        marker = body[2].stripped.casefold()
        matrix = "indefinite" if marker.startswith("*in") else (
            "unsymmetric" if marker.startswith("*un") else "definite"
        )
        matrix_line = body[2]
    else:
        matrix = "definite"
        matrix_line = type_line
    parameters["matrix_type"] = [
        _solver_parameter(definitions["matrix_type"], matrix, "marker", source, matrix_line)
    ]
    add_record(1, type_line, parameters, "legacy")


def _table_error(
    index: SemanticIndex, code: str, message: str, source: str, line: SourceLine,
) -> None:
    index.diagnostics.append(Diagnostic(
        code=code, severity="error", message=message, line=line.number, source=source,
    ))


def _table_parameter(value: Any, spelling: str, source: str, line: SourceLine) -> dict[str, Any]:
    return {
        "value": value,
        "spelling": spelling,
        "location": _location(source, line).as_dict(),
    }


def _material_reference_owner(
    index: SemanticIndex, source: str, line: SourceLine, text: str,
) -> SemanticEntity:
    owner = next((
        item for item in index.entities
        if item.kind == "structured-material"
        and item.location.source == source
        and int(item.attributes.get("body_start_line", 0)) <= line.number
        <= int(item.attributes.get("body_end_line", -1))
    ), None)
    if owner is not None:
        return owner
    key = _key("material-parameter", f"line-{line.number}", None)
    existing = next((item for item in index.entities if item.key == key), None)
    if existing is not None:
        return existing
    return _entity(
        index, "material-parameter", f"line-{line.number}", source, line, None,
        {"record": text.strip(), "declaration": "unattributed-preserved"},
    )


def augment_structured_material_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Identify only exact unindented 998/999 material groups; preserve all legacy bodies."""
    all_lines = tuple(lines)
    material_record = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.materials"
    )
    body = _top_block_body(all_lines, "MATERIALS")
    cursor = 0
    occurrence = 0
    while cursor < len(body):
        line = body[cursor]
        text = line.text.split("#", 1)[0].strip()
        fields = _fields(text)
        if line.text[:1].isspace() or not fields or fields[0] not in {"998", "999"}:
            cursor += 1
            continue
        occurrence += 1
        material_type = int(fields[0])
        terminator = next(
            (
                position for position in range(cursor + 1, len(body))
                if body[position].text.split("#", 1)[0].strip() == "*end"
            ),
            None,
        )
        next_header = next((
            position for position in range(cursor + 1, len(body))
            if not body[position].text[:1].isspace()
            and _fields(body[position].text.split("#", 1)[0].strip())[:1]
            in (["998"], ["999"])
        ), None)
        if next_header is not None and (terminator is None or next_header < terminator):
            _table_error(
                index, "BSAM-E350",
                f"structured material type {material_type} is missing exact *end",
                source, line,
            )
            end = next_header
            body_end_line = body[end - 1].number if end > cursor + 1 else line.number
            next_cursor = next_header
        elif terminator is None:
            _table_error(
                index, "BSAM-E350",
                f"structured material type {material_type} is missing exact *end",
                source, line,
            )
            end = len(body)
            body_end_line = body[-1].number if body else line.number
            next_cursor = len(body)
        else:
            end = terminator
            body_end_line = body[end].number
            next_cursor = terminator + 1
        parameter_lines = [
            item for item in body[cursor + 1:end]
            if "=" in item.text.split("#", 1)[0]
            and not item.text.lstrip().startswith("**")
        ]
        material = _entity(
            index, "structured-material", f"type-{material_type}-line-{line.number}",
            source, line, None,
            {
                "type": material_type,
                "syntax": "structured",
                "body_start_line": line.number,
                "body_end_line": body_end_line,
                "parameter_record_count": len(parameter_lines),
            },
        )
        parameters = {
            "type": (_table_parameter(str(material_type), "type", source, line),),
            "material_parameter": tuple(
                _table_parameter(
                    item.text.split("#", 1)[0].strip(), "key/value", source, item,
                )
                for item in parameter_lines
            ),
        }
        instance_operations = operational_support(material_record)
        instance_operations = {
            **instance_operations,
            "parse": "verified", "semantic": "verified", "inspect": "verified",
            "static_validation": "verified",
        }
        index.capability_records.append(RegisteredConstruct(
            id=f"block.materials.structured[{occurrence}]@{source}:{line.number}",
            capability_id="block.materials",
            canonical="MATERIALS",
            occurrence=occurrence,
            location=_location(source, line),
            parameters=parameters,
            operations=instance_operations,
            attributes={"entity_id": material.id, "syntax": "structured"},
        ))
        cursor = next_cursor


def augment_table_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Parse named rectangular TABLES and structured material table references."""
    all_lines = tuple(lines)
    table_record = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.tables"
    )
    active = [
        (line, line.text.split("#", 1)[0].strip())
        for line in _top_block_body(all_lines, "TABLES")
        if line.text.split("#", 1)[0].strip()
        and not line.text.lstrip().startswith("**")
    ]
    cursor = 0
    occurrence = 0
    while cursor < len(active):
        header, header_text = active[cursor]
        if not header_text.casefold().startswith("table-"):
            _table_error(
                index, "BSAM-E320", "TABLES entry must start with table-<name>", source, header,
            )
            cursor += 1
            continue
        occurrence += 1
        name = header_text[6:].strip().casefold()
        end = next(
            (position for position in range(cursor + 1, len(active)) if active[position][1] == "*end"),
            None,
        )
        if end is None:
            _table_error(
                index, "BSAM-E320", f"table {name or '<unnamed>'} is missing exact *end",
                source, header,
            )
            entry = active[cursor + 1:]
            cursor = len(active)
        else:
            entry = active[cursor + 1:end]
            cursor = end + 1

        parameters: dict[str, list[dict[str, Any]]] = {
            "name": [_table_parameter(name, "table-", source, header)],
        }
        row_label = ""
        column_label = ""
        horizontal: list[float] = []
        vertical: list[float] = []
        values: list[list[float]] = []
        valid_grid = True
        if not name or "_" in name:
            _table_error(
                index, "BSAM-E320",
                "table name must be non-empty and may not contain underscores",
                source, header,
            )
            valid_grid = False
        if not entry:
            _table_error(index, "BSAM-E320", f"table {name} has no axis header", source, header)
            valid_grid = False
        else:
            axis_line, axis_text = entry[0]
            axis_fields = _fields(axis_text)
            labels = re.split(r"[-/|_]", axis_fields[0], maxsplit=2) if axis_fields else []
            if len(labels) != 2 or not all(labels):
                _table_error(
                    index, "BSAM-E320", f"table {name} axis header requires row-column labels",
                    source, axis_line,
                )
                valid_grid = False
            else:
                row_label, column_label = (item.casefold() for item in labels)
                parameters["row_label"] = [
                    _table_parameter(row_label, labels[0], source, axis_line)
                ]
                parameters["column_label"] = [
                    _table_parameter(column_label, labels[1], source, axis_line)
                ]
            for raw in axis_fields[1:]:
                try:
                    number = float(raw)
                    if not math.isfinite(number):
                        raise ValueError
                    horizontal.append(number)
                    parameters.setdefault("horizontal_lookup", []).append(
                        _table_parameter(raw, "horizontal_lookup", source, axis_line)
                    )
                except ValueError:
                    _table_error(
                        index, "BSAM-E320", f"table {name} has a non-finite horizontal coordinate",
                        source, axis_line,
                    )
                    valid_grid = False
            if not horizontal:
                _table_error(
                    index, "BSAM-E320", f"table {name} requires a horizontal coordinate",
                    source, axis_line,
                )
                valid_grid = False
            elif any(right <= left for left, right in zip(horizontal, horizontal[1:])):
                _table_error(
                    index, "BSAM-E321", f"table {name} horizontal coordinates must increase",
                    source, axis_line,
                )
                valid_grid = False

            for data_line, data_text in entry[1:]:
                fields = _fields(data_text)
                if len(fields) != len(horizontal) + 1:
                    _table_error(
                        index, "BSAM-E320",
                        f"table {name} row width must be {len(horizontal) + 1}",
                        source, data_line,
                    )
                    valid_grid = False
                    continue
                try:
                    numbers = [float(item) for item in fields]
                    if any(not math.isfinite(item) for item in numbers):
                        raise ValueError
                except ValueError:
                    _table_error(
                        index, "BSAM-E320", f"table {name} data rows must contain finite reals",
                        source, data_line,
                    )
                    valid_grid = False
                    continue
                vertical.append(numbers[0])
                values.append(numbers[1:])
                parameters.setdefault("vertical_lookup", []).append(
                    _table_parameter(fields[0], "vertical_lookup", source, data_line)
                )
                for raw in fields[1:]:
                    parameters.setdefault("value", []).append(
                        _table_parameter(raw, "value", source, data_line)
                    )
            if not vertical:
                _table_error(
                    index, "BSAM-E320", f"table {name} requires at least one data row",
                    source, axis_line,
                )
                valid_grid = False
            elif any(right <= left for left, right in zip(vertical, vertical[1:])):
                _table_error(
                    index, "BSAM-E321", f"table {name} vertical coordinates must increase",
                    source, entry[1][0],
                )
                valid_grid = False

        table = _entity(index, "table", name or f"unnamed-{occurrence}", source, header, None, {
            "row_label": row_label,
            "column_label": column_label,
            "horizontal_lookup": horizontal,
            "vertical_lookup": vertical,
            "values": values,
            "shape": [len(vertical), len(horizontal)],
            "valid_grid": valid_grid,
        })
        index.capability_records.append(RegisteredConstruct(
            id=f"block.tables[{occurrence}]@{source}:{header.number}",
            capability_id="block.tables",
            canonical="TABLES",
            occurrence=occurrence,
            location=_location(source, header),
            parameters={key: tuple(items) for key, items in parameters.items()},
            operations=operational_support(table_record),
            attributes={"entity_id": table.id, "shape": [len(vertical), len(horizontal)]},
        ))

    table_reference = re.compile(r"(?i)(?:^|[^a-z0-9])table_([^_,\s]+)")
    polynomial_reference = re.compile(r"(?i)(?:^|[^a-z0-9])poly_([^,\s]+)")
    for line in _top_block_body(all_lines, "MATERIALS"):
        text = line.text.split("#", 1)[0]
        if "=" not in text or line.text.lstrip().startswith("**"):
            continue
        right = text.split("=", 1)[1]
        targets = [match.group(1).casefold() for match in table_reference.finditer(right)]
        for match in polynomial_reference.finditer(right):
            targets.extend(
                name.casefold() for name in match.group(1).split("_") if name
            )
        if not targets:
            continue
        parameter = _material_reference_owner(index, source, line, text)
        for target in targets:
            _reference(
                index, parameter, "uses-table", _key("table", target, None), source, line,
            )


def augment_ufunction_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Parse named two-column UFUNCTIONS and structured material references."""
    all_lines = tuple(lines)
    function_record = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.ufunctions"
    )
    active = [
        (line, line.text.split("#", 1)[0].strip())
        for line in _top_block_body(all_lines, "UFUNCTIONS")
        if line.text.split("#", 1)[0].strip()
        and not line.text.lstrip().startswith("**")
    ]
    cursor = 0
    occurrence = 0
    while cursor < len(active):
        header, header_text = active[cursor]
        if header_text == "*end":
            _table_error(
                index, "BSAM-E330", "UFUNCTIONS contains an empty entry", source, header,
            )
            cursor += 1
            continue
        occurrence += 1
        tokens = [item for item in re.split(r"[\s_-]+", header_text.casefold()) if item]
        name = tokens[-1] if tokens else ""
        end = next(
            (position for position in range(cursor + 1, len(active)) if active[position][1] == "*end"),
            None,
        )
        if end is None:
            _table_error(
                index, "BSAM-E330", f"user function {name or '<unnamed>'} is missing exact *end",
                source, header,
            )
            entry = active[cursor + 1:]
            cursor = len(active)
        else:
            entry = active[cursor + 1:end]
            cursor = end + 1
        while entry and entry[0][1].startswith("*"):
            entry = entry[1:]

        parameters: dict[str, list[dict[str, Any]]] = {
            "name": [_table_parameter(name, header_text, source, header)],
        }
        points: list[list[float]] = []
        valid_data = True
        if not name:
            _table_error(index, "BSAM-E330", "user function name is empty", source, header)
            valid_data = False
        for data_line, data_text in entry:
            fields = _fields(data_text)
            if len(fields) != 2:
                _table_error(
                    index, "BSAM-E330", f"user function {name} data must have two columns",
                    source, data_line,
                )
                valid_data = False
                continue
            try:
                point = [float(item) for item in fields]
                if any(not math.isfinite(item) for item in point):
                    raise ValueError
            except ValueError:
                _table_error(
                    index, "BSAM-E330", f"user function {name} data must contain finite reals",
                    source, data_line,
                )
                valid_data = False
                continue
            points.append(point)
            parameters.setdefault("x", []).append(
                _table_parameter(fields[0], "x", source, data_line)
            )
            parameters.setdefault("y", []).append(
                _table_parameter(fields[1], "y", source, data_line)
            )
        if len(points) < 2:
            _table_error(
                index, "BSAM-E330", f"user function {name} requires at least two points",
                source, header,
            )
            valid_data = False
        elif not (
            all(right[0] > left[0] for left, right in zip(points, points[1:]))
            or all(right[0] < left[0] for left, right in zip(points, points[1:]))
        ):
            _table_error(
                index, "BSAM-E331", f"user function {name} x coordinates must be strictly monotonic",
                source, entry[0][0],
            )
            valid_data = False

        function = _entity(
            index, "user-function", name or f"unnamed-{occurrence}", source, header, None,
            {"points": points, "point_count": len(points), "valid_data": valid_data},
        )
        index.capability_records.append(RegisteredConstruct(
            id=f"block.ufunctions[{occurrence}]@{source}:{header.number}",
            capability_id="block.ufunctions",
            canonical="UFUNCTIONS",
            occurrence=occurrence,
            location=_location(source, header),
            parameters={key: tuple(items) for key, items in parameters.items()},
            operations=operational_support(function_record),
            attributes={"entity_id": function.id, "point_count": len(points)},
        ))

    function_reference = re.compile(r"(?i)(?:^|[^a-z0-9])ufunc_([^_,\s]+)")
    for line in _top_block_body(all_lines, "MATERIALS"):
        text = line.text.split("#", 1)[0]
        if "=" not in text or line.text.lstrip().startswith("**"):
            continue
        right = text.split("=", 1)[1]
        targets = [match.group(1).casefold() for match in function_reference.finditer(right)]
        if not targets:
            continue
        parameter = _material_reference_owner(index, source, line, text)
        for target in targets:
            _reference(
                index, parameter, "uses-user-function",
                _key("user-function", target, None), source, line,
            )


def augment_statistical_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Parse canonical type-3 statistical distributions and their references."""
    all_lines = tuple(lines)
    stat_record = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.statistical-distributions"
    )
    active = [
        (line, line.text.split("#", 1)[0].strip())
        for line in _top_block_body(all_lines, "STATISTICAL")
        if line.text.split("#", 1)[0].strip()
        and not line.text.lstrip().startswith("**")
    ]
    clusters = [item for item in index.entities if item.kind == "cluster"]
    cursor = 0
    occurrence = 0
    while cursor < len(active):
        header, header_text = active[cursor]
        folded_header = header_text.casefold()
        if not folded_header.startswith(("stat-", "dist-")):
            _table_error(
                index, "BSAM-E340", "statistical entry must start with stat-<name>",
                source, header,
            )
            cursor += 1
            continue
        occurrence += 1
        name = folded_header.split("-", 1)[1].strip()
        end = next(
            (position for position in range(cursor + 1, len(active)) if active[position][1] == "*end"),
            None,
        )
        if end is None:
            _table_error(
                index, "BSAM-E340", f"statistical distribution {name} is missing exact *end",
                source, header,
            )
            entry = active[cursor + 1:]
            cursor = len(active)
        else:
            entry = active[cursor + 1:end]
            cursor = end + 1

        parameters: dict[str, list[dict[str, Any]]] = {
            "name": [_table_parameter(name, header_text, source, header)],
        }
        parsed: dict[str, tuple[str, SourceLine]] = {}
        positions: dict[str, int] = {}
        aliases = {
            "approximation": "approx", "seed": "seeding", "gen": "generation",
        }
        for position, (data_line, data_text) in enumerate(entry):
            if "=" not in data_text:
                _table_error(
                    index, "BSAM-E340", f"statistical distribution {name} requires key=value rows",
                    source, data_line,
                )
                continue
            left, right = data_text.split("=", 1)
            keys = _fields(left)
            if len(keys) != 1:
                _table_error(
                    index, "BSAM-E340",
                    f"statistical distribution {name} canonical rows require one key",
                    source, data_line,
                )
                continue
            key = aliases.get(keys[0].casefold(), keys[0].casefold())
            if key in parsed:
                _table_error(
                    index, "BSAM-E340", f"statistical distribution {name} repeats {key}",
                    source, data_line,
                )
                continue
            parsed[key] = (right.strip(), data_line)
            positions[key] = position

        required = {"type", "approx", "seeding", "alpha", "v0", "generation"}
        missing = sorted(required - parsed.keys())
        if missing:
            _table_error(
                index, "BSAM-E340",
                f"statistical distribution {name} is missing: {', '.join(missing)}",
                source, header,
            )
        seeding = parsed.get("seeding", ("", header))[0].casefold()
        if seeding:
            required.add(seeding)
        allowed_keys = {
            "type", "approx", "seeding", "alpha", "v0", "generation",
            "seed_window_section", seeding,
        }
        unknown = sorted(set(parsed) - allowed_keys)
        if unknown:
            _table_error(
                index, "BSAM-E340",
                f"statistical distribution {name} has unknown keys: {', '.join(unknown)}",
                source, parsed[unknown[0]][1],
            )
        if seeding not in {"coordinates", "fiber", "fibers"}:
            _table_error(
                index, "BSAM-E340",
                f"statistical distribution {name} seeding must be coordinates, fiber, or fibers",
                source, parsed.get("seeding", ("", header))[1],
            )
        seed_value = parsed.get(seeding)
        if seed_value is None:
            _table_error(
                index, "BSAM-E340",
                f"statistical distribution {name} requires dynamic {seeding or '<seeding>'} dimensions",
                source, header,
            )
        elif positions[seeding] <= positions.get("seeding", -1):
            _table_error(
                index, "BSAM-E340",
                f"statistical distribution {name} seed dimensions must follow seeding",
                source, seed_value[1],
            )

        numeric: dict[str, int | float | list[float]] = {}
        for key in ("type", "approx", "generation", "seed_window_section"):
            if key not in parsed:
                continue
            raw, data_line = parsed[key]
            try:
                numeric[key] = int(raw)
            except ValueError:
                _table_error(
                    index, "BSAM-E340", f"statistical distribution {name} {key} must be an integer",
                    source, data_line,
                )
        for key in ("alpha", "v0"):
            if key not in parsed:
                continue
            raw, data_line = parsed[key]
            try:
                value = float(raw)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError
                numeric[key] = value
            except ValueError:
                _table_error(
                    index, "BSAM-E340", f"statistical distribution {name} {key} must be positive",
                    source, data_line,
                )
        if seed_value is not None:
            raw, data_line = seed_value
            try:
                dimensions = [float(item) for item in _fields(raw)]
                if len(dimensions) != 3 or any(
                    not math.isfinite(item) or item <= 0 for item in dimensions
                ):
                    raise ValueError
                numeric["seed_dimensions"] = dimensions
            except ValueError:
                _table_error(
                    index, "BSAM-E340",
                    f"statistical distribution {name} seed dimensions must be three positive reals",
                    source, data_line,
                )
        if numeric.get("type") != 3:
            _table_error(
                index, "BSAM-E340", f"statistical distribution {name} generated type must be 3",
                source, parsed.get("type", ("", header))[1],
            )
        if not isinstance(numeric.get("approx"), int) or numeric["approx"] <= 0:
            _table_error(
                index, "BSAM-E340", f"statistical distribution {name} approx must be positive",
                source, parsed.get("approx", ("", header))[1],
            )
        if not isinstance(numeric.get("generation"), int) or numeric["generation"] <= 0:
            _table_error(
                index, "BSAM-E340", f"statistical distribution {name} generation must be positive",
                source, parsed.get("generation", ("", header))[1],
            )
        if seeding in {"fiber", "fibers"} and "seed_window_section" not in numeric:
            _table_error(
                index, "BSAM-E340",
                f"statistical distribution {name} fiber seeding requires seed_window_section",
                source, header,
            )
        if isinstance(numeric.get("seed_window_section"), int) and numeric["seed_window_section"] <= 0:
            _table_error(
                index, "BSAM-E340",
                f"statistical distribution {name} seed_window_section must be positive",
                source, parsed["seed_window_section"][1],
            )

        for key, (raw, data_line) in parsed.items():
            canonical = "seed_dimensions" if key == seeding else key
            parameters.setdefault(canonical, []).append(
                _table_parameter(raw, key, source, data_line)
            )
        distribution = _entity(
            index, "statistical-distribution", name or f"unnamed-{occurrence}",
            source, header, None,
            {"seeding": seeding, **numeric},
        )
        approximation = numeric.get("approx")
        target_cluster: SemanticEntity | None = None
        if isinstance(approximation, int):
            if 1 <= approximation <= len(clusters):
                target_cluster = clusters[approximation - 1]
                target_key = target_cluster.key
            else:
                target_key = _key("cluster", f"approximation-{approximation}", None)
            _reference(
                index, distribution, "uses-seed-cluster", target_key, source,
                parsed["approx"][1], {"approximation": approximation},
            )
        section_id = numeric.get("seed_window_section")
        if isinstance(section_id, int) and target_cluster is not None:
            sections = [
                item for item in index.entities
                if item.kind == "section"
                and item.attributes.get("cluster", "").casefold() == target_cluster.name.casefold()
            ]
            section_key = (
                sections[section_id - 1].key
                if 1 <= section_id <= len(sections)
                else f"{target_cluster.key}/section:ordinal-{section_id}"
            )
            _reference(
                index, distribution, "uses-seed-section", section_key, source,
                parsed["seed_window_section"][1], {"section": section_id},
            )
        index.capability_records.append(RegisteredConstruct(
            id=f"block.statistical-distributions[{occurrence}]@{source}:{header.number}",
            capability_id="block.statistical-distributions",
            canonical="STATISTICAL",
            occurrence=occurrence,
            location=_location(source, header),
            parameters={key: tuple(items) for key, items in parameters.items()},
            operations=operational_support(stat_record),
            attributes={"entity_id": distribution.id},
        ))

    stat_reference = re.compile(r"(?i)(?:^|[^a-z0-9])stat_([^_,\s]+)")
    for line in _top_block_body(all_lines, "MATERIALS"):
        text = line.text.split("#", 1)[0]
        if "=" not in text or line.text.lstrip().startswith("**"):
            continue
        right = text.split("=", 1)[1]
        targets = [match.group(1).casefold() for match in stat_reference.finditer(right)]
        if not targets:
            continue
        parameter = _material_reference_owner(index, source, line, text)
        for target in targets:
            _reference(
                index, parameter, "uses-statistical-distribution",
                _key("statistical-distribution", target, None), source, line,
            )


_CONSTITUTIVE_DIRECT_WIDTHS = {
    1: 3, 2: 5, 3: 8, 4: 10, 5: 3, 6: 4, 7: 2, 8: 2, 10: 3,
}
_CONSTITUTIVE_WRAPPER_TYPES = {11, 12, 13, 21, 110, 120, 130}


def _semantic_record_lines(lines: Iterable[SourceLine]) -> list[SourceLine]:
    """Return records visible to list-directed readers while retaining source locations."""
    return [
        line for line in lines
        if line.text.split("#", 1)[0].strip()
        and not line.text.lstrip().startswith("#")
    ]


def _record_fields(line: SourceLine) -> list[str]:
    return _fields(line.text.split("#", 1)[0])


def _fortran_real(value: str) -> float:
    return float(value.replace("d", "e").replace("D", "E"))


def _not_fortran_number(value: str) -> bool:
    try:
        _fortran_real(value)
    except ValueError:
        return True
    return False


def _validate_boundary_loading_sequence(records: list[SourceLine]) -> str | None:
    """Validate the bounded key/value rows consumed by IBN_INI's *LOAD branch."""
    if not records:
        return "BOUNDARY LOADING SEQUENCE requires at least one load header"
    current_family: str | None = None
    block_count: int | None = None
    header_count = 0
    for line in records:
        tokens = [
            token for token in re.split(
                r"[\s,=]+", line.text.split("#", 1)[0].strip(),
            ) if token
        ]
        if len(tokens) % 2:
            return "BOUNDARY LOADING SEQUENCE rows require key/value pairs"
        pairs = [(tokens[index].casefold()[:4], tokens[index + 1])
                 for index in range(0, len(tokens), 2)]
        if not pairs or len(pairs) > 9:
            return "BOUNDARY LOADING SEQUENCE rows require one to nine key/value pairs"
        values = {key: value for key, value in pairs}
        is_header = "nste" in values
        is_change = "chan" in values
        if is_header == is_change:
            return "each BOUNDARY LOADING SEQUENCE row requires exactly one of nstep or change"

        if is_header:
            header_count += 1
            allowed = {"type", "name", "nste", "incr", "bloc"}
            required = {"type", "name", "nste", "incr"}
            raw_type = values.get("type", "").casefold()
            if raw_type.startswith("stat"):
                current_family = "static"
            elif raw_type.startswith("fati"):
                current_family = "fatigue"
                allowed |= {"maxc", "minc", "r", "inic"}
                required |= {"maxc", "minc", "r", "inic"}
            elif raw_type.startswith("2dfa"):
                current_family = "2dfatigue"
                allowed |= {"maxc", "minc", "r", "inic"}
                required |= {"maxc", "minc", "r", "inic"}
            elif raw_type.startswith("redu"):
                current_family = "reduced_fatigue"
                allowed |= {"maxc", "minc", "r", "inic"}
                required |= {"maxc", "minc", "r", "inic"}
            else:
                return "BOUNDARY LOADING SEQUENCE header has an unsupported type"
            if not set(values) <= allowed:
                return "BOUNDARY LOADING SEQUENCE header contains an unknown option"
            if not required <= set(values):
                return "BOUNDARY LOADING SEQUENCE header is missing a required option"
            try:
                if int(values["nste"]) <= 0:
                    raise ValueError
                if not math.isfinite(_fortran_real(values["incr"])):
                    raise ValueError
                if current_family != "static":
                    int(values["maxc"])
                    for key in ("minc", "r", "inic"):
                        if not math.isfinite(_fortran_real(values[key])):
                            raise ValueError
            except ValueError:
                return "BOUNDARY LOADING SEQUENCE header contains an invalid numeric value"
            if "bloc" in values:
                if current_family in {"2dfatigue", "reduced_fatigue"}:
                    return f"{current_family} block repetition is blocked by incomplete source copying"
                try:
                    count = int(values["bloc"])
                    if count <= 0:
                        raise ValueError
                except ValueError:
                    return "BOUNDARY LOADING SEQUENCE block count must be a positive integer"
                if block_count is None:
                    block_count = count
                elif count == block_count:
                    block_count = None
                else:
                    return "BOUNDARY LOADING SEQUENCE block markers must have matching counts"
            continue

        if current_family is None:
            return "BOUNDARY LOADING SEQUENCE change must follow a load header"
        allowed = {"chan", "type", "valu"}
        if current_family != "static":
            allowed |= {"maxc", "minc", "r"}
        if not set(values) <= allowed:
            return "BOUNDARY LOADING SEQUENCE change contains an unknown option"
        if current_family in {"2dfatigue", "reduced_fatigue"}:
            return f"{current_family} change rows are blocked by incomplete source allocation"
        raw_change_type = values.get("type")
        if raw_change_type is not None and not (
            raw_change_type.casefold().startswith(("disp", "stre", "forc"))
            or raw_change_type.casefold().startswith("off")
        ):
            return "BOUNDARY LOADING SEQUENCE change has an unsupported type"
        try:
            if "valu" in values and not math.isfinite(_fortran_real(values["valu"])):
                raise ValueError
            if "maxc" in values:
                int(values["maxc"])
            if "minc" in values:
                int(values["minc"])
            if "r" in values and not math.isfinite(_fortran_real(values["r"])):
                raise ValueError
        except ValueError:
            return "BOUNDARY LOADING SEQUENCE change contains an invalid numeric value"
    if not header_count:
        return "BOUNDARY LOADING SEQUENCE requires at least one load header"
    if block_count is not None:
        return "BOUNDARY LOADING SEQUENCE repeated blocks require an explicit closing marker"
    return None


def _validate_boundary_connections(
    records: list[SourceLine], selected_clusters: list[str],
) -> str | None:
    """Validate the three connection row-state machines used by IBN_INI."""
    if not records:
        return "BOUNDARY CONNECTIONS requires at least one typed connection"
    selected = {name.casefold() for name in selected_clusters}
    header_positions = [
        index for index, line in enumerate(records) if "type" in _record_options(line)
    ]
    if not header_positions or header_positions[0] != 0:
        return "BOUNDARY CONNECTIONS must begin each connection with a type header"
    header_positions.append(len(records))
    penalty_count = 0

    def pairs(line: SourceLine) -> tuple[dict[str, str], str | None]:
        tokens = [token for token in re.split(
            r"[\s,=]+", line.text.split("#", 1)[0].strip(),
        ) if token]
        if len(tokens) % 2 or not tokens or len(tokens) > 8:
            return {}, "CONNECTIONS keyed rows require one to four key/value pairs"
        return {
            tokens[index].casefold()[:4]: tokens[index + 1]
            for index in range(0, len(tokens), 2)
        }, None

    def qualified(value: str) -> bool:
        if value.count(".") != 1:
            return False
        cluster_name, set_name = value.split(".", 1)
        return bool(cluster_name and set_name and cluster_name.casefold() in selected)

    def validate_pair_values(options: dict[str, str]) -> str | None:
        if not ({"mset", "sset"} & set(options)):
            return "CONNECTIONS assignment rows require mset or sset"
        for key in ("mset", "sset"):
            if key in options and not qualified(options[key]):
                return "CONNECTIONS set targets must be selected-cluster-qualified"
        for key in ("mate", "cons", "fail"):
            if key in options:
                try:
                    if int(options[key]) <= 0:
                        raise ValueError
                except ValueError:
                    return "CONNECTIONS declaration references must be positive integers"
        return None

    for ordinal in range(len(header_positions) - 1):
        start, end = header_positions[ordinal], header_positions[ordinal + 1]
        header, error = pairs(records[start])
        if error:
            return error
        connection_type = header.get("type", "").casefold()
        body = records[start + 1:end]
        common = {"type", "name", "tole", "sear"}
        if connection_type in {"-2", "-21"}:
            penalty_count += 1
            if penalty_count > 1:
                return "BOUNDARY CONNECTIONS permits only one active penalty chain"
            if not set(header) <= common:
                return "penalty CONNECTIONS header contains an unknown option"
            if connection_type == "-21":
                return "CONNECTIONS type -21 is rejected by the active execution dispatch"
            search = header.get("sear", "vtms").casefold()
            if not (search.startswith("vtms") or search.startswith("shef")):
                return "penalty CONNECTIONS search must begin vtms or shef"
            if len(body) < 2 or not body[-1].text.split("#", 1)[0].strip().casefold().startswith("last="):
                return "penalty CONNECTIONS requires assignments followed by one last row"
            for row in body[:-1]:
                options, error = pairs(row)
                if error:
                    return error
                if not set(options) <= {"mset", "sset", "mate", "cons", "fail"}:
                    return "penalty CONNECTIONS assignment contains an unknown option"
                error = validate_pair_values(options)
                if error:
                    return error
            terminals = [
                value.strip() for value in body[-1].text.split("#", 1)[0].split("=", 1)[1].split(",")
                if value.strip()
            ]
            if not terminals or (
                [value.casefold() for value in terminals] != ["none"]
                and any(value.casefold() not in selected for value in terminals)
            ):
                return "penalty CONNECTIONS last targets must be none or selected clusters"
        elif connection_type.startswith("noda"):
            if not set(header) <= {"type", "name", "comp"}:
                return "nodal CONNECTIONS header contains an unknown option"
            component = header.get("comp")
            if component is not None and component.casefold() not in {
                "x", "y", "z", "xy", "yx", "xz", "zx", "yz", "zy",
                "xyz", "yzx", "zxy", "xzy", "yxz", "zyx",
            }:
                return "nodal CONNECTIONS component is invalid"
            if len(body) != 2:
                return "nodal CONNECTIONS requires exactly one mset row and one sset row"
            for row, expected in zip(body, ("mset", "sset")):
                text = row.text.split("#", 1)[0].strip()
                if "=" not in text or text.split("=", 1)[0].strip().casefold()[:4] != expected:
                    return "nodal CONNECTIONS selector rows must be ordered mset then sset"
                targets = [value.strip() for value in text.split("=", 1)[1].split(",") if value.strip()]
                if not targets or not (
                    [value.casefold() for value in targets] == ["all"]
                    or all(qualified(value) for value in targets)
                ):
                    return "nodal CONNECTIONS selectors must be all or selected-cluster-qualified sets"
        elif connection_type.startswith("surf"):
            if not set(header) <= common:
                return "surface CONNECTIONS header contains an unknown option"
            if not header.get("sear", "").casefold().startswith("shef"):
                return "surface CONNECTIONS requires search=sheff"
            if not body:
                return "surface CONNECTIONS requires at least one contact-pair row"
            for row in body:
                options, error = pairs(row)
                if error:
                    return error
                if not set(options) <= {"mset", "sset", "mate", "cons", "fail"}:
                    return "surface CONNECTIONS pair contains an unknown option"
                if not {"mset", "sset"} <= set(options):
                    return "surface CONNECTIONS pairs require both mset and sset"
                error = validate_pair_values(options)
                if error:
                    return error
        else:
            return "BOUNDARY CONNECTIONS header has an unsupported type"
        if "tole" in header:
            try:
                tolerance = _fortran_real(header["tole"])
                if not math.isfinite(tolerance) or tolerance <= 0:
                    raise ValueError
            except ValueError:
                return "BOUNDARY CONNECTIONS tolerance must be a positive finite real"
    return None


def _constitutive_modifier(line: SourceLine) -> tuple[str, list[int]] | None:
    """Mirror CON_INI's five-character modifier dispatch without consuming data rows."""
    text = line.text.split("#", 1)[0].strip()
    fields = _fields(text)
    if not fields:
        return None
    dispatch = fields[0][:5]
    if dispatch == "*xyzl":
        return "xyzload", []
    if dispatch == "*fati":
        values = _fields(text[len(fields[0]):])
        try:
            return "fatigue", [int(values[0])] if values else []
        except ValueError:
            return "fatigue", []
    if dispatch == "*mic=":
        values = re.findall(r"(?<![A-Za-z0-9_.+-])[+-]?\d+(?![A-Za-z0-9_.])", text[4:])
        return "mic", [int(value) for value in values[:3]]
    return None


def augment_constitutive_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Consume every CON_INI declaration variant in declaration order without rewriting it."""
    records = _semantic_record_lines(_top_block_body(tuple(lines), "CONSTITUTIVE"))
    construct = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.constitutive"
    )
    cursor = 0
    ordinal = 0
    while cursor < len(records):
        type_line = records[cursor]
        type_fields = _record_fields(type_line)
        try:
            material_type = int(type_fields[0])
        except (IndexError, ValueError):
            _table_error(
                index, "BSAM-E360", "CONSTITUTIVE declaration requires an integer type",
                source, type_line,
            )
            break
        cursor += 1
        if material_type <= 0:
            break
        if material_type not in set(_CONSTITUTIVE_DIRECT_WIDTHS) | _CONSTITUTIVE_WRAPPER_TYPES:
            _table_error(
                index, "BSAM-E360",
                f"unsupported CONSTITUTIVE type {material_type}", source, type_line,
            )
            break

        modifiers: dict[str, Any] = {"xyzload": False, "mic": [], "fatigue": 0}
        modifier_lines: dict[str, SourceLine] = {}
        # CON_INI probes exactly three slots, backspacing an unrecognized record.
        for _slot in range(3):
            if cursor >= len(records):
                break
            parsed_modifier = _constitutive_modifier(records[cursor])
            if parsed_modifier is None:
                continue
            name, values = parsed_modifier
            modifier_lines[name] = records[cursor]
            if name == "xyzload":
                modifiers[name] = True
            elif name == "mic":
                modifiers[name] = values
            elif values:
                modifiers[name] = values[0]
            cursor += 1

        if cursor >= len(records):
            _table_error(
                index, "BSAM-E360",
                f"CONSTITUTIVE type {material_type} is missing its data record",
                source, type_line,
            )
            break
        data_line = records[cursor]
        data_fields = _record_fields(data_line)
        attributes: dict[str, Any] = {
            "type": material_type,
            "declaration_ordinal": ordinal + 1,
            "body_start_line": type_line.number,
            "modifiers": modifiers,
        }
        referenced_constitutives: list[tuple[int, SourceLine, str]] = []
        if material_type in _CONSTITUTIVE_DIRECT_WIDTHS:
            required = _CONSTITUTIVE_DIRECT_WIDTHS[material_type]
            if len(data_fields) < required:
                _table_error(
                    index, "BSAM-E360",
                    f"CONSTITUTIVE type {material_type} requires {required} data values",
                    source, data_line,
                )
                break
            try:
                attributes["material_id"] = int(data_fields[0])
                attributes["failure_id"] = int(data_fields[1])
                for value in data_fields[2:required]:
                    _fortran_real(value)
                if attributes["material_id"] <= 0 or attributes["failure_id"] <= 0:
                    raise ValueError
            except ValueError:
                _table_error(
                    index, "BSAM-E360",
                    f"CONSTITUTIVE type {material_type} requires positive material/failure IDs and numeric data",
                    source, data_line,
                )
                break
            if material_type in {3, 4}:
                user_count = 4 if material_type == 3 else 6
                try:
                    user_ids = [int(value) for value in data_fields[3:3 + user_count]]
                    if len(user_ids) != user_count or any(value <= 0 for value in user_ids):
                        raise ValueError
                except ValueError:
                    _table_error(
                        index, "BSAM-E360",
                        f"CONSTITUTIVE type {material_type} requires positive USER function IDs",
                        source, data_line,
                    )
                    break
                attributes["numeric_user_ids"] = user_ids
            cursor += 1
        else:
            header_width = 2 if material_type >= 110 else 1
            if len(data_fields) < header_width:
                _table_error(
                    index, "BSAM-E360",
                    f"CONSTITUTIVE wrapper type {material_type} has an incomplete header",
                    source, data_line,
                )
                break
            try:
                count = int(data_fields[0])
            except ValueError:
                count = -1
            if count <= 0:
                _table_error(
                    index, "BSAM-E360",
                    f"CONSTITUTIVE wrapper type {material_type} requires a positive count",
                    source, data_line,
                )
                break
            attributes["referenced_count"] = count
            if material_type >= 110:
                try:
                    attributes["property_subdivision_id"] = int(data_fields[1])
                except ValueError:
                    _table_error(
                        index, "BSAM-E360",
                        f"CONSTITUTIVE wrapper type {material_type} requires an integer subdivision ID",
                        source, data_line,
                    )
                    break
            cursor += 1
            if cursor + count > len(records):
                _table_error(
                    index, "BSAM-E360",
                    f"CONSTITUTIVE wrapper type {material_type} requires {count} mapping rows",
                    source, data_line,
                )
                break
            mapping_ids: list[int] = []
            malformed = False
            for mapping_line in records[cursor:cursor + count]:
                mapping = _record_fields(mapping_line)
                try:
                    int(mapping[0])
                    target = int(mapping[1])
                    if target <= 0:
                        raise ValueError
                except (IndexError, ValueError):
                    _table_error(
                        index, "BSAM-E360",
                        f"CONSTITUTIVE wrapper type {material_type} requires label/ID mappings",
                        source, mapping_line,
                    )
                    malformed = True
                    break
                mapping_ids.append(target)
                referenced_constitutives.append((target, mapping_line, "wrapper"))
            if malformed:
                break
            attributes["constitutive_ids"] = mapping_ids
            data_line = records[cursor + count - 1]
            cursor += count

        ordinal += 1
        attributes["body_end_line"] = data_line.number
        entity = _entity(
            index, "constitutive", str(ordinal), source, type_line, None, attributes,
        )
        for target in modifiers["mic"]:
            referenced_constitutives.append((target, modifier_lines["mic"], "mic"))
        for target, reference_line, reference_kind in referenced_constitutives:
            _reference(
                index, entity, "uses-constitutive", _key("constitutive", str(target), None),
                source, reference_line, {"source": reference_kind},
            )
        for position, target in enumerate(attributes.get("numeric_user_ids", []), start=1):
            _reference(
                index, entity, "uses-numeric-user-function",
                _key("numeric-user-function", str(target), None), source, data_line,
                {"position": position},
            )
        parameters = {
            "type": (_table_parameter(material_type, "type", source, type_line),),
        }
        for name, value in (
            ("material_id", attributes.get("material_id")),
            ("failure_id", attributes.get("failure_id")),
            ("mic", modifiers["mic"] or None),
            ("xyzload", True if modifiers["xyzload"] else None),
            ("fatigue", modifiers["fatigue"] or None),
        ):
            if value is None:
                continue
            value_line = modifier_lines.get(name, data_line)
            parameters[name] = (_table_parameter(value, name, source, value_line),)
        operations = {
            **operational_support(construct),
            "parse": "verified", "semantic": "verified", "inspect": "verified",
            "static_validation": "verified",
        }
        index.capability_records.append(RegisteredConstruct(
            id=f"block.constitutive[{ordinal}]@{source}:{type_line.number}",
            capability_id="block.constitutive",
            canonical="CONSTITUTIVE",
            occurrence=ordinal,
            location=_location(source, type_line),
            parameters=parameters,
            operations=operations,
            attributes={"entity_id": entity.id, "variant_type": material_type},
        ))


_FAILURE_NO_DATA_TYPES = {
    3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21,
    24, 27, 28, 31, 32, 33, 34, 35, 36, 45,
}
_FAILURE_SINGLE_REFERENCE_TYPES = {22, 23, 25, 29, 30}


def augment_failure_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> None:
    """Consume every FAI_INI variant and retain one-based declaration identities."""
    records = _semantic_record_lines(_top_block_body(tuple(lines), "FAILURE"))
    construct = next(
        item for item in load_registry()["top_level_blocks"]
        if item["id"] == "block.failure"
    )
    cursor = 0
    ordinal = 0
    while cursor < len(records):
        type_line = records[cursor]
        fields = _record_fields(type_line)
        try:
            failure_type = int(fields[0])
        except (IndexError, ValueError):
            _table_error(
                index, "BSAM-E370", "FAILURE declaration requires an integer type",
                source, type_line,
            )
            break
        cursor += 1
        if failure_type <= 0:
            break
        if failure_type not in (
            _FAILURE_NO_DATA_TYPES | _FAILURE_SINGLE_REFERENCE_TYPES | {1, 2, 18, 26}
        ):
            _table_error(
                index, "BSAM-E370", f"unsupported FAILURE type {failure_type}",
                source, type_line,
            )
            break

        body_end = type_line
        attributes: dict[str, Any] = {
            "type": failure_type,
            "declaration_ordinal": ordinal + 1,
            "body_start_line": type_line.number,
        }
        referenced_failure: tuple[int, SourceLine] | None = None
        required_rows = {1: 10, 2: 11}.get(failure_type, 0)
        if required_rows:
            if cursor + required_rows > len(records):
                _table_error(
                    index, "BSAM-E370",
                    f"FAILURE type {failure_type} requires {required_rows} degradation rows",
                    source, type_line,
                )
                break
            malformed = next((
                line for line in records[cursor:cursor + required_rows]
                if len(_record_fields(line)) < 8 or any(
                    _not_fortran_number(value) for value in _record_fields(line)[:8]
                )
            ), None)
            if malformed is not None:
                _table_error(
                    index, "BSAM-E370",
                    f"FAILURE type {failure_type} degradation rows require eight values",
                    source, malformed,
                )
                break
            body_end = records[cursor + required_rows - 1]
            attributes["degradation_row_count"] = required_rows
            cursor += required_rows
        elif failure_type == 18:
            if cursor >= len(records):
                _table_error(
                    index, "BSAM-E370", "FAILURE type 18 is missing its control row",
                    source, type_line,
                )
                break
            control_line = records[cursor]
            control = _record_fields(control_line)
            try:
                target, mode_count = int(control[0]), int(control[1])
                int(control[2])
                if target <= 0:
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E370",
                    "FAILURE type 18 requires criterion, mode-count, and level values",
                    source, control_line,
                )
                break
            if mode_count <= 0 or cursor + 1 + mode_count > len(records):
                _table_error(
                    index, "BSAM-E370",
                    f"FAILURE type 18 requires {max(mode_count, 0)} mode rows",
                    source, control_line,
                )
                break
            malformed = next((
                line for line in records[cursor + 1:cursor + 1 + mode_count]
                if len(_record_fields(line)) < 5 or any(
                    _not_fortran_number(value) for value in _record_fields(line)[:5]
                )
            ), None)
            if malformed is not None:
                _table_error(
                    index, "BSAM-E370", "FAILURE type 18 mode rows require five values",
                    source, malformed,
                )
                break
            referenced_failure = (target, control_line)
            attributes["base_failure_id"] = target
            attributes["mode_count"] = mode_count
            body_end = records[cursor + mode_count]
            cursor += mode_count + 1
        elif failure_type in _FAILURE_SINGLE_REFERENCE_TYPES:
            if cursor >= len(records):
                _table_error(
                    index, "BSAM-E370",
                    f"FAILURE type {failure_type} requires a referenced criterion row",
                    source, type_line,
                )
                break
            reference_line = records[cursor]
            try:
                target = int(_record_fields(reference_line)[0])
                if target <= 0:
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E370",
                    f"FAILURE type {failure_type} requires an integer criterion ID",
                    source, reference_line,
                )
                break
            referenced_failure = (target, reference_line)
            attributes["base_failure_id"] = target
            body_end = reference_line
            cursor += 1
        # Type 26 rereads its own declaration line to extract optional CFACTOR.
        if failure_type == 26:
            match = re.search(
                r"(?i)\bCFACTOR\s*[=, ]\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)",
                type_line.text.split("#", 1)[0],
            )
            attributes["cfactor"] = float(match.group(1).replace("d", "e").replace("D", "E")) if match else 10.0

        ordinal += 1
        attributes["body_end_line"] = body_end.number
        entity = _entity(
            index, "failure", str(ordinal), source, type_line, None, attributes,
        )
        if referenced_failure is not None:
            target, reference_line = referenced_failure
            _reference(
                index, entity, "uses-failure", _key("failure", str(target), None),
                source, reference_line,
            )
        operations = {
            **operational_support(construct),
            "parse": "verified", "semantic": "verified", "inspect": "verified",
            "static_validation": "verified",
        }
        index.capability_records.append(RegisteredConstruct(
            id=f"block.failure[{ordinal}]@{source}:{type_line.number}",
            capability_id="block.failure",
            canonical="FAILURE",
            occurrence=ordinal,
            location=_location(source, type_line),
            parameters={
                "type": (_table_parameter(failure_type, "type", source, type_line),),
            },
            operations=operations,
            attributes={"entity_id": entity.id, "variant_type": failure_type},
        ))


_MATERIAL_ORTHOTROPIC_TYPES = {1, 5, 6, 7, 100, 101, 102, 103, 104, 105, 106}
_MATERIAL_TYPES = (
    _MATERIAL_ORTHOTROPIC_TYPES
    | {2, 3, 4, 10, 11, 12, 15, 40, 41, 50, 200, 210, 300, 500, 800, 998, 999}
)


def _material_record_lines(lines: Iterable[SourceLine]) -> list[SourceLine]:
    records: list[SourceLine] = []
    for line in lines:
        text = line.text.strip()
        if not text or text.startswith("**"):
            continue
        if text.startswith("#") and text[:3].casefold() not in {"#ge", "#ap", "#se"}:
            continue
        records.append(line)
    return records


def _material_header_type(line: SourceLine) -> int | None:
    fields = _record_fields(line)
    try:
        return int(fields[0])
    except (IndexError, ValueError):
        text = line.text.split("#", 1)[0]
        match = re.search(r"(?i)(?:^|[,\s])type\s*=\s*(mises|50)(?:[,\s]|$)", text)
        return 50 if match else None


def _material_dispatch(line: SourceLine) -> str:
    raw = line.text.strip()
    text = raw if raw.startswith("#") else line.text.split("#", 1)[0]
    fields = _fields(text)
    return fields[0][:5].casefold() if fields else ""


def _consume_material_statistics(
    records: list[SourceLine], cursor: int, *, type_three: bool,
) -> int | None:
    """Consume the legacy inline *statistics body beginning after its marker."""
    for _entry in range(5):
        if cursor >= len(records):
            return None
        if _material_dispatch(records[cursor]) == "*end":
            return cursor + 1
        fields = _record_fields(records[cursor])
        try:
            stat_type = int(fields[0])
        except (IndexError, ValueError):
            return None
        cursor += 1
        if stat_type == 1:
            required = 2
        elif stat_type == 2 and not type_three:
            required = 2
        elif stat_type == 3 and not type_three:
            required = 4
        else:
            return None
        if cursor + required > len(records):
            return None
        cursor += required
        if cursor < len(records) and _material_dispatch(records[cursor]) == "#gene":
            cursor += 1
    return cursor if cursor <= len(records) else None


def _material_spans(
    lines: Iterable[SourceLine],
) -> list[tuple[int, SourceLine, SourceLine, tuple[SourceLine, ...]]] | None:
    """Mirror MAT_INI record consumption; return nothing unless the whole block is proven."""
    records = _material_record_lines(lines)
    spans: list[tuple[int, SourceLine, SourceLine, tuple[SourceLine, ...]]] = []
    cursor = 0
    while cursor < len(records):
        header = records[cursor]
        material_type = _material_header_type(header)
        if material_type is None:
            return None
        cursor += 1
        if material_type <= 0:
            return spans if cursor == len(records) else None
        if material_type not in _MATERIAL_TYPES:
            return None
        end_line = header
        body_start = cursor

        if material_type in {50, 998, 999}:
            end = next((
                position for position in range(cursor, len(records))
                if records[position].text.strip() == "*end"
            ), None)
            if end is None:
                return None
            end_line = records[end]
            cursor = end + 1
        elif material_type in _MATERIAL_ORTHOTROPIC_TYPES:
            features = {"*fibe", "*cfv_", "*shea", "*tens", "*bimo"}
            for _slot in range(5):
                if cursor < len(records) and _material_dispatch(records[cursor]) in features:
                    end_line = records[cursor]
                    cursor += 1
            if cursor >= len(records):
                return None
            if _material_dispatch(records[cursor]) == "*stre":
                end_line = records[cursor]
                cursor += 1
                property_rows = 19 if material_type in {1, 5, 6, 7, 100} else 18
            else:
                property_rows = 12
            if cursor + property_rows > len(records):
                return None
            end_line = records[cursor + property_rows - 1]
            cursor += property_rows
            if cursor < len(records) and _material_dispatch(records[cursor]) == "*s-n":
                if cursor + 1 >= len(records):
                    return None
                end_line = records[cursor + 1]
                cursor += 2
            if cursor < len(records) and _material_dispatch(records[cursor]) == "*stat":
                stat_start = cursor
                cursor = _consume_material_statistics(records, cursor + 1, type_three=False)
                if cursor is None:
                    return None
                end_line = records[cursor - 1] if cursor > stat_start + 1 else records[stat_start]
        elif material_type == 10:
            if cursor + 2 > len(records):
                return None
            end_line = records[cursor + 1]
            cursor += 2
        elif material_type == 12:
            if cursor + 3 > len(records):
                return None
            end_line = records[cursor + 2]
            cursor += 3
            for _slot in range(5):
                progressed = False
                if cursor < len(records) and _material_dispatch(records[cursor]) == "*dama":
                    end_line = records[cursor]
                    cursor += 1
                    continue
                for marker, extra in (("*maxg", 0), ("*fric", 0), ("*pari", 2), ("*s-n", 1)):
                    if cursor < len(records) and _material_dispatch(records[cursor]) == marker:
                        if cursor + extra >= len(records):
                            return None
                        end_line = records[cursor + extra]
                        cursor += extra + 1
                        progressed = True
                if not progressed:
                    continue
        elif material_type == 15:
            if cursor + 5 > len(records):
                return None
            end_line = records[cursor + 4]
            cursor += 5
        elif material_type in {2, 3, 4}:
            row_count = {2: 18, 3: 16, 4: 12}[material_type]
            if cursor + row_count > len(records):
                return None
            end_line = records[cursor + row_count - 1]
            cursor += row_count
        elif material_type == 11:
            if cursor >= len(records):
                return None
            end_line = records[cursor]
            cursor += 1
        elif material_type in {40, 41}:
            if cursor + 2 > len(records):
                return None
            end_line = records[cursor + 1]
            cursor += 2
        elif material_type == 200:
            if cursor + 2 > len(records):
                return None
            end_line = records[cursor + 1]
            cursor += 2
            if cursor < len(records) and _material_dispatch(records[cursor]) == "*delt":
                if cursor + 1 >= len(records):
                    return None
                end_line = records[cursor + 1]
                cursor += 2
        elif material_type == 210:
            if cursor >= len(records):
                return None
            if _material_dispatch(records[cursor]) == "*stre":
                cursor += 1
                property_rows = 14
            else:
                property_rows = 12
            if cursor + property_rows > len(records):
                return None
            end_line = records[cursor + property_rows - 1]
            cursor += property_rows
            if cursor < len(records) and _material_dispatch(records[cursor]) == "*stat":
                stat_start = cursor
                cursor = _consume_material_statistics(records, cursor + 1, type_three=True)
                if cursor is None:
                    return None
                end_line = records[cursor - 1] if cursor > stat_start + 1 else records[stat_start]
            if cursor + 2 > len(records):
                return None
            end_line = records[cursor + 1]
            cursor += 2
            if cursor < len(records) and _material_dispatch(records[cursor]) == "*delt":
                if cursor + 1 >= len(records):
                    return None
                end_line = records[cursor + 1]
                cursor += 2
        elif material_type == 300:
            if cursor >= len(records):
                return None
            try:
                count = int(_record_fields(records[cursor])[0])
            except (IndexError, ValueError):
                return None
            if count <= 0 or cursor + count + 2 > len(records):
                return None
            end_line = records[cursor + count + 1]
            cursor += count + 2
        elif material_type == 500:
            if cursor >= len(records):
                return None
            try:
                count = int(_record_fields(records[cursor])[0])
            except (IndexError, ValueError):
                return None
            if count <= 0 or cursor + count + 1 > len(records):
                return None
            end_line = records[cursor + count]
            cursor += count + 1
        elif material_type == 800:
            if cursor + 3 > len(records):
                return None
            end_line = records[cursor + 2]
            cursor += 3
        spans.append((material_type, header, end_line, tuple(records[body_start:cursor])))
    return spans


def augment_material_declaration_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine],
) -> bool:
    """Add ordinal material identities only after the complete block is cursor-proven."""
    spans = _material_spans(_top_block_body(tuple(lines), "MATERIALS"))
    if spans is None:
        return False
    structured_by_line = {
        item.location.line: item for item in index.entities
        if item.kind == "structured-material" and item.location.source == source
    }
    for ordinal, (material_type, header, end_line, body) in enumerate(spans, start=1):
        structured = structured_by_line.get(header.number)
        attributes: dict[str, Any] = {
            "type": material_type,
            "declaration_ordinal": ordinal,
            "body_start_line": header.number,
            "body_end_line": end_line.number,
            "syntax": "structured" if material_type in {50, 998, 999} else "legacy",
        }
        if structured is not None:
            attributes["structured_entity_id"] = structured.id
        user_selectors: list[tuple[str, int, SourceLine]] = []
        material_dependencies: list[tuple[int, SourceLine]] = []
        cluster_dependency: tuple[int, SourceLine] | None = None
        if material_type == 4:
            selector_lines = body[:12]
            try:
                user_ids = [int(_record_fields(line)[0]) for line in selector_lines]
                if len(user_ids) != 12 or any(value <= 0 for value in user_ids):
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 4 requires twelve positive USER function IDs",
                    source, header,
                )
            else:
                attributes["numeric_user_ids"] = user_ids
                user_selectors = [
                    (str(position), target, line)
                    for position, (target, line) in enumerate(
                        zip(user_ids, selector_lines), start=1,
                    )
                ]
        elif material_type == 40:
            fields = re.split(r"[\s,=]+", body[0].text.split("#", 1)[0].strip())
            try:
                if fields and fields[0][:1].isdigit():
                    values = [int(value) for value in fields[:3]]
                    if len(values) != 3 or any(value <= 0 for value in values):
                        raise ValueError
                    selectors = dict(zip(("e", "g", "alf"), values))
                else:
                    selectors: dict[str, int] = {}
                    cursor = 0
                    while cursor < len(fields):
                        name = fields[cursor].casefold()
                        if name not in {"e", "g", "u", "alf"} or cursor + 1 >= len(fields):
                            raise ValueError
                        value = int(fields[cursor + 1])
                        if value < 0:
                            raise ValueError
                        selectors[name] = value
                        cursor += 2
                    if not selectors:
                        raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 40 requires legacy E/G/ALF IDs or keyed E/G/U/ALF IDs",
                    source, header,
                )
            else:
                attributes["numeric_user_selectors"] = selectors
                user_selectors = [
                    (name, target, body[0]) for name, target in selectors.items()
                    if target > 0
                ]
        elif material_type == 41:
            try:
                values = [int(value) for value in _record_fields(body[0])[:4]]
                if len(values) != 4 or any(value <= 0 for value in values):
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 41 requires four positive USER function IDs",
                    source, header,
                )
            else:
                selectors = dict(zip(("e_j1", "e_j2", "nu", "alpha"), values))
                attributes["numeric_user_selectors"] = selectors
                user_selectors = [
                    (name, target, body[0]) for name, target in selectors.items()
                ]
        elif material_type == 15:
            names = ("mode_i", "mode_ii", "phase")
            selector_lines = body[2:5]
            try:
                values = [int(_record_fields(line)[0]) for line in selector_lines]
                if len(values) != 3 or any(value <= 0 for value in values):
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 15 requires three positive USER function IDs",
                    source, header,
                )
            else:
                selectors = dict(zip(names, values))
                attributes["numeric_user_selectors"] = selectors
                user_selectors = [
                    (name, target, line) for name, target, line in zip(
                        names, values, selector_lines,
                    )
                ]
        elif material_type == 500:
            try:
                target = int(_record_fields(body[0])[1])
                if target <= 0:
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 500 requires a positive USER function ID",
                    source, header,
                )
            else:
                attributes["numeric_user_selectors"] = {"function": target}
                user_selectors = [("function", target, body[0])]
        elif material_type == 11:
            fields = _record_fields(body[0])
            try:
                material_ids = [int(value) for value in fields[:2]]
                fractions = [_fortran_real(value) for value in fields[2:4]]
                if (
                    len(material_ids) != 2 or len(fractions) != 2
                    or any(value <= 0 or value >= ordinal for value in material_ids)
                    or any(not math.isfinite(value) or not 0 <= value <= 1 for value in fractions)
                    or not math.isclose(sum(fractions), 1.0, rel_tol=1e-9, abs_tol=1e-12)
                ):
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 11 requires two prior material IDs and fractions summing to one",
                    source, header,
                )
            else:
                attributes["material_ids"] = material_ids
                attributes["fractions"] = fractions
                material_dependencies = [(target, body[0]) for target in material_ids]
        elif material_type == 300:
            try:
                count = int(_record_fields(body[0])[0])
                source_rows = body[1:1 + count]
                material_ids = [int(_record_fields(line)[0]) for line in source_rows]
                fractions = [_fortran_real(_record_fields(line)[1]) for line in source_rows]
                default_fraction = _fortran_real(_record_fields(body[1 + count])[0])
                if (
                    count <= 0 or len(material_ids) != count
                    or any(value <= 0 or value >= ordinal for value in material_ids)
                    or any(not math.isfinite(value) or not 0 <= value <= 1 for value in fractions)
                    or not math.isfinite(default_fraction) or not 0 <= default_fraction <= 1
                ):
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 300 requires prior material IDs and bounded fractions",
                    source, header,
                )
            else:
                attributes["material_ids"] = material_ids
                attributes["fractions"] = fractions
                attributes["default_fraction"] = default_fraction
                material_dependencies = list(zip(material_ids, source_rows))
        elif material_type == 800:
            try:
                cluster_id = int(_record_fields(body[0])[0])
                if cluster_id <= 0:
                    raise ValueError
            except (IndexError, ValueError):
                _table_error(
                    index, "BSAM-E350",
                    "MATERIALS type 800 requires a positive cluster ID",
                    source, header,
                )
            else:
                attributes["cluster_id"] = cluster_id
                cluster_dependency = (cluster_id, body[0])
        elif material_type in _MATERIAL_ORTHOTROPIC_TYPES:
            feature_count = 0
            while (
                feature_count < len(body)
                and _material_dispatch(body[feature_count])
                in {"*fibe", "*cfv_", "*shea", "*tens", "*bimo"}
            ):
                feature_count += 1
            feature_lines = body[:feature_count]
            ordinary_rows = body[feature_count:feature_count + 12]
            nonlinear_shear = material_type == 105 or any(
                _material_dispatch(line) == "*shea" for line in feature_lines
            )
            alternate_strength = (
                feature_count < len(body)
                and _material_dispatch(body[feature_count]) == "*stre"
            )
            if nonlinear_shear and not alternate_strength:
                selector_rows = (
                    ("g13", ordinary_rows[6]), ("g12", ordinary_rows[8]),
                )
                try:
                    selectors = {
                        name: int(_record_fields(line)[1])
                        for name, line in selector_rows
                    }
                    if any(
                        _record_fields(line)[0].casefold() != "uf=" or target <= 0
                        for (name, line), target in zip(
                            selector_rows, selectors.values(),
                        )
                    ):
                        raise ValueError
                except (IndexError, ValueError):
                    _table_error(
                        index, "BSAM-E350",
                        "nonlinear-shear MATERIALS require positive uf= USER IDs for G13 and G12",
                        source, header,
                    )
                else:
                    attributes["numeric_user_selectors"] = selectors
                    user_selectors = [
                        (name, selectors[name], line) for name, line in selector_rows
                    ]
        material = _entity(
            index, "material", str(ordinal), source, header, None, attributes,
        )
        for position, (selector, target, line) in enumerate(user_selectors, start=1):
            _reference(
                index, material, "uses-numeric-user-function",
                _key("numeric-user-function", str(target), None), source, line,
                {"position": position, "selector": selector},
            )
        for position, (target, line) in enumerate(material_dependencies, start=1):
            _reference(
                index, material, "uses-material",
                _key("material", str(target), None), source, line,
                {"position": position},
            )
        if cluster_dependency is not None:
            target, line = cluster_dependency
            clusters = [item for item in index.entities if item.kind == "cluster"]
            target_key = (
                clusters[target - 1].key if target <= len(clusters)
                else _key("cluster", f"approximation-{target}", None)
            )
            _reference(
                index, material, "uses-cluster", target_key, source, line,
                {"approximation": target},
            )
    return True


def augment_direct_constitutive_references(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine], *,
    material_declarations_complete: bool, failure_declarations_complete: bool,
) -> None:
    """Link direct declarations only when the target declaration order is fully known."""
    by_number = {line.number: line for line in lines}
    for entity in index.entities:
        if entity.kind != "constitutive" or entity.location.source != source:
            continue
        material_id = entity.attributes.get("material_id")
        failure_id = entity.attributes.get("failure_id")
        line = by_number.get(int(entity.attributes.get("body_end_line", 0)))
        if line is None:
            continue
        if material_declarations_complete and isinstance(material_id, int):
            _reference(
                index, entity, "uses-material", _key("material", str(material_id), None),
                source, line,
            )
        if failure_declarations_complete and isinstance(failure_id, int):
            _reference(
                index, entity, "uses-failure", _key("failure", str(failure_id), None),
                source, line,
            )


def augment_root_semantics(
    index: SemanticIndex, source: str, lines: Iterable[SourceLine]
) -> None:
    """Add documented root control entities and their FE/cluster references."""
    all_lines = tuple(lines)
    augment_registered_top_level_semantics(index, source, all_lines)
    augment_numeric_user_semantics(index, source, all_lines)
    augment_registered_boundary_semantics(index, source, all_lines)
    augment_solver_semantics(index, source, all_lines)
    augment_structured_material_semantics(index, source, all_lines)
    material_declarations_complete = augment_material_declaration_semantics(
        index, source, all_lines,
    )
    augment_table_semantics(index, source, all_lines)
    augment_ufunction_semantics(index, source, all_lines)
    augment_statistical_semantics(index, source, all_lines)
    augment_constitutive_semantics(index, source, all_lines)
    failure_errors = sum(item.code == "BSAM-E370" for item in index.diagnostics)
    augment_failure_semantics(index, source, all_lines)
    failure_declarations_complete = failure_errors == sum(
        item.code == "BSAM-E370" for item in index.diagnostics
    )
    augment_direct_constitutive_references(
        index, source, all_lines,
        material_declarations_complete=material_declarations_complete,
        failure_declarations_complete=failure_declarations_complete,
    )

    boundary_body = _top_block_body(all_lines, "BOUNDARY")
    all_cluster_names = [item.name for item in index.entities if item.kind == "cluster"]
    selected_cluster_names = list(all_cluster_names)
    boundary_problem_ordinal = 0
    boundary_names: dict[str, int] = {}
    for command_line, body in _command_spans(boundary_body):
        command = command_line.text.lstrip().split(",", 1)[0].casefold()
        records = [line for line in body if line.stripped and not line.stripped.startswith("**")]
        if command.startswith("*type"):
            boundary_problem_ordinal += 1
            selected_cluster_names = list(all_cluster_names)
            type_error: str | None = None
            problem_type = (
                records[0].text.split("#", 1)[0].strip().casefold()
                if records else ""
            )
            option_flags = {
                "geo_nl", "fiber_rot", "dlm_normal_rot", "mic_normal_rot",
            }
            if not records or not problem_type:
                type_error = "BOUNDARY TYPE requires a problem-type record"
            elif problem_type.startswith("mech"):
                option_rows = records[1:]
                if len(option_rows) > 1:
                    type_error = "mechanical BOUNDARY TYPE permits at most one kinematic-options record"
            elif problem_type.startswith("ther"):
                if len(records) < 2:
                    type_error = "thermal BOUNDARY TYPE requires one finite temperature record"
                    option_rows = []
                else:
                    temperature_fields = _fields(records[1].text)
                    if (
                        len(temperature_fields) != 1
                        or _not_fortran_number(temperature_fields[0])
                        or not math.isfinite(_fortran_real(temperature_fields[0]))
                    ):
                        type_error = "thermal BOUNDARY TYPE temperature must be one finite real"
                    option_rows = records[2:]
                    if len(option_rows) > 1:
                        type_error = "thermal BOUNDARY TYPE permits at most one kinematic-options record"
            elif problem_type.startswith("cont"):
                option_rows = records[1:]
                type_error = "contact BOUNDARY TYPE is rejected by the active BSAM dispatch"
            else:
                option_rows = records[1:]
                type_error = "BOUNDARY TYPE must begin mechanical, thermal, or contact"

            if type_error is None and option_rows:
                flags = {
                    token.casefold()
                    for token in re.split(r"[\s,=]+", option_rows[0].text.split("#", 1)[0].strip())
                    if token
                }
                if not flags or not flags <= option_flags:
                    type_error = (
                        "BOUNDARY TYPE kinematic options must be a subset of "
                        "GEO_NL, FIBER_ROT, DLM_NORMAL_ROT, and MIC_NORMAL_ROT"
                    )
            if type_error is not None:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310", severity="error", message=type_error,
                    line=command_line.number, source=source,
                ))
        elif command.startswith("*g-co"):
            control_error: str | None = None
            if records:
                control_error = "BOUNDARY G-CONTROL accepts command-line options only"
            tokens = [
                token for token in re.split(
                    r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                ) if token
            ][1:]
            values: dict[str, float | int] = {
                "g_it": 1000, "gmin": 0.0, "gmax": 1.0e9, "gthr": 0.0,
            }
            update = False
            position = 0
            while control_error is None and position < len(tokens):
                spelling = tokens[position]
                key = spelling.casefold()[:4]
                if key in {"upda", "damp", "no_d"}:
                    update = update or key == "upda"
                    position += 1
                    continue
                canonical_key = "gmin" if key == "g_th" else key
                if canonical_key not in {"g_it", "gmin", "gmax", "gthr"}:
                    control_error = f"unknown BOUNDARY G-CONTROL option {spelling}"
                    break
                if position + 1 >= len(tokens):
                    control_error = f"BOUNDARY G-CONTROL option {spelling} requires a value"
                    break
                raw_value = tokens[position + 1]
                try:
                    if canonical_key == "g_it":
                        value: float | int = int(raw_value)
                        if value <= 0:
                            raise ValueError
                    else:
                        value = _fortran_real(raw_value)
                        if not math.isfinite(value) or value < 0:
                            raise ValueError
                except ValueError:
                    expected = "a positive integer" if canonical_key == "g_it" else "a nonnegative finite real"
                    control_error = f"BOUNDARY G-CONTROL option {spelling} requires {expected}"
                    break
                values[canonical_key] = value
                position += 2
            if control_error is None and values["gmin"] > values["gmax"]:
                control_error = "BOUNDARY G-CONTROL requires GMIN <= GMAX"
            if control_error is None and update and values["gthr"] <= 0:
                control_error = "BOUNDARY G-CONTROL UPDATE requires GTHR > 0"
            if control_error is not None:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310", severity="error", message=control_error,
                    line=command_line.number, source=source,
                ))
        elif command.startswith("*name"):
            if not records:
                continue
            tokens = records[0].text.split("#", 1)[0].replace(",", " ").split()
            reserved_names = {
                "input", "solver", "moisture", "boundary", "constitutive",
                "failure", "crack", "tables", "statistical", "ufunctions",
                "user", "clusters", "materials",
            }
            if (
                len(records) != 1 or len(tokens) != 1 or len(tokens[0]) > 80
                or tokens[0].casefold() in reserved_names
            ):
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310", severity="error",
                    message=(
                        "BOUNDARY NAME must be empty for its default or contain one "
                        "non-reserved token of at most 80 characters"
                    ),
                    line=command_line.number, source=source,
                ))
                continue
            normalized_name = tokens[0].casefold()
            previous_problem = boundary_names.get(normalized_name)
            if (
                previous_problem is not None
                and previous_problem != boundary_problem_ordinal
            ):
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E300", severity="error",
                    message=f"duplicate BOUNDARY problem name {tokens[0]}",
                    line=records[0].number, source=source,
                ))
            else:
                boundary_names[normalized_name] = boundary_problem_ordinal
        elif command.startswith("*clusters"):
            named_clusters = [
                (name, line)
                for line in records for name in _fields(line.text)
            ]
            select_all = (
                len(named_clusters) == 1
                and named_clusters[0][0].casefold() == "all"
            )
            if named_clusters and not select_all:
                selected_cluster_names = [name for name, _line in named_clusters]
            effective_clusters = (
                [(name, command_line) for name in selected_cluster_names]
                if select_all or not named_clusters else named_clusters
            )
            selection = _entity(
                index, "cluster-selection", f"line-{command_line.number}",
                source, command_line, None,
                {
                    "mode": "all" if select_all else (
                        "unchanged-empty" if not named_clusters else "explicit"
                    ),
                    "clusters": [name for name, _line in named_clusters],
                    "effective_clusters": [name for name, _line in effective_clusters],
                },
            )
            for cluster_name, line in effective_clusters:
                _reference(
                    index, selection, "selects-cluster",
                    _key("cluster", cluster_name, None), source, line,
                )
        elif command.startswith("*boundary condition"):
            for line in records:
                options = _record_options(line)
                name = options.get("name")
                if not name:
                    continue
                condition = _entity(
                    index, "boundary-condition", name, source, line, None,
                    {key: value for key, value in options.items() if key != "name"},
                )
                qualified = options.get("nset")
                if qualified and "." in qualified:
                    cluster, set_name = qualified.split(".", 1)
                    _reference(
                        index, condition, "targets-node-set",
                        _key("node-set", set_name, cluster), source, line,
                    )
                if str(options.get("type", "")).casefold().startswith("temp"):
                    for cluster_name in selected_cluster_names:
                        _reference(
                            index, condition, "targets-cluster",
                            _key("cluster", cluster_name, None), source, line,
                        )
        elif command.startswith("*output"):
            headers = [
                (position, line, _record_options(line))
                for position, line in enumerate(records)
                if "type" in _record_options(line)
            ]
            selected_keys = {name.casefold() for name in selected_cluster_names}
            for ordinal, (position, line, options) in enumerate(headers, start=1):
                next_position = (
                    headers[ordinal][0] if ordinal < len(headers) else len(records)
                )
                continuation = [
                    (value, body_line)
                    for body_line in records[position + 1:next_position]
                    for value in _fields(body_line.text)
                ]
                raw_type = str(options.get("type") or "")
                prefix = raw_type.casefold()[:3]
                output_type = {
                    "dat": "data-file", "sum": "sum-force",
                    "vol": "volume-average", "tra": "traction-average",
                    "cfv": "cfv",
                }.get(prefix)
                if output_type is None:
                    continue
                output = _entity(
                    index, "output-selection", f"line-{line.number}",
                    source, line, None,
                    {
                        "output_type": output_type, "ordinal": ordinal,
                        "coordinate_system": options.get("c_system", "global"),
                        "intermediate": options.get("intermediate"),
                    },
                )

                if output_type == "data-file":
                    selector_name, target_kind = "clusters", "cluster"
                elif output_type in {"sum-force", "traction-average"}:
                    selector_name, target_kind = "nset", "node-set"
                else:
                    selector_name, target_kind = "elset", "element-set"
                selector = str(options.get(selector_name) or "")
                tokens = continuation if selector.casefold() == "list" else [(selector, line)]

                if target_kind == "cluster":
                    if selector.casefold() == "all" or (
                        selector.casefold() == "list"
                        and len(tokens) == 1 and tokens[0][0].casefold() == "all"
                    ):
                        tokens = [(name, line) for name in selected_cluster_names]
                    for cluster_name, target_line in tokens:
                        if not cluster_name:
                            continue
                        _reference(
                            index, output, "selects-cluster",
                            _key("cluster", cluster_name, None), source, target_line,
                        )
                    continue

                if selector.casefold() == "all" or (
                    selector.casefold() == "list"
                    and len(tokens) == 1 and tokens[0][0].casefold() == "all"
                ):
                    seen_keys: set[str] = set()
                    for candidate in index.entities:
                        if candidate.kind != target_kind:
                            continue
                        candidate_cluster = str(candidate.attributes.get("cluster", "")).casefold()
                        if candidate_cluster not in selected_keys or candidate.key in seen_keys:
                            continue
                        seen_keys.add(candidate.key)
                        _reference(
                            index, output, f"selects-{target_kind}",
                            candidate.key, source, line,
                        )
                    continue

                for qualified, target_line in tokens:
                    if "." not in qualified:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E313", severity="error",
                            message=(
                                f"BOUNDARY output {selector_name} target must be "
                                f"cluster-qualified: {qualified or '<missing>'}"
                            ),
                            line=target_line.number, source=source,
                        ))
                        continue
                    cluster_name, set_name = qualified.split(".", 1)
                    if cluster_name.casefold() not in selected_keys:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E313", severity="error",
                            message=(
                                f"BOUNDARY output target cluster is outside the active "
                                f"cluster selection: {cluster_name}"
                            ),
                            line=target_line.number, source=source,
                        ))
                    if set_name.casefold() == "all":
                        seen_keys: set[str] = set()
                        for candidate in index.entities:
                            if (
                                candidate.kind == target_kind
                                and str(candidate.attributes.get("cluster", "")).casefold()
                                == cluster_name.casefold()
                                and candidate.key not in seen_keys
                            ):
                                seen_keys.add(candidate.key)
                                _reference(
                                    index, output, f"selects-{target_kind}",
                                    candidate.key, source, target_line,
                                )
                    else:
                        _reference(
                            index, output, f"selects-{target_kind}",
                            _key(target_kind, set_name, cluster_name), source, target_line,
                        )
        elif command.startswith("*connections"):
            connection_error = _validate_boundary_connections(
                records, selected_cluster_names,
            )
            if connection_error is not None:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310", severity="error", message=connection_error,
                    line=command_line.number, source=source,
                ))
            connection: SemanticEntity | None = None
            connection_type = ""
            ordinal = 0
            for line in records:
                options = _record_options(line)
                if "type" in options:
                    ordinal += 1
                    name = options.get("name", f"connection{ordinal}")
                    connection_type = options["type"].casefold()
                    connection = _entity(
                        index, "connection", name, source, line, None,
                        {"type": options["type"], "ordinal": ordinal},
                    )
                if connection is None:
                    continue
                for option in ("mset", "sset"):
                    qualified = options.get(option)
                    if not qualified:
                        continue
                    if connection_type.startswith("noda"):
                        fields = [value.strip() for value in line.text.split(",")]
                        targets = [qualified, *(
                            value for value in fields[1:] if value and "=" not in value
                        )]
                        if qualified.casefold() == "all":
                            targets = [
                                item.key for item in index.entities
                                if item.kind == "node-set"
                                and str(item.attributes.get("cluster", "")).casefold()
                                in {name.casefold() for name in selected_cluster_names}
                            ]
                        for target in targets:
                            if target.startswith("cluster:"):
                                target_key = target
                            elif "." in target:
                                cluster_name, set_name = target.split(".", 1)
                                if set_name.casefold() == "all":
                                    for candidate in index.entities:
                                        if (
                                            candidate.kind == "node-set"
                                            and str(candidate.attributes.get("cluster", "")).casefold()
                                            == cluster_name.casefold()
                                        ):
                                            _reference(
                                                index, connection, option,
                                                candidate.key, source, line,
                                            )
                                    continue
                                target_key = _key(
                                    "node-set", set_name, cluster_name,
                                )
                            else:
                                index.diagnostics.append(Diagnostic(
                                    code="BSAM-E313", severity="error",
                                    message=(
                                        "nodal CONNECTION set target must be all or "
                                        f"cluster-qualified: {target}"
                                    ),
                                    line=line.number, source=source,
                                ))
                                continue
                            _reference(
                                index, connection, option, target_key, source, line,
                            )
                    elif "." in qualified:
                        cluster_name, set_name = qualified.split(".", 1)
                        _reference(
                            index, connection, option,
                            _key("node-set", set_name, cluster_name), source, line,
                        )
                for option, reference_kind, target_kind in (
                    ("material", "uses-material", "material"),
                    ("constitutive", "uses-constitutive", "constitutive"),
                    ("failure", "uses-failure", "failure"),
                ):
                    target = options.get(option)
                    if target and target.isdigit():
                        _reference(
                            index, connection, reference_kind,
                            _key(target_kind, target, None), source, line,
                        )
                if "last" in options:
                    terminal_values = line.text.split("=", 1)[1].split(",")
                    for terminal in (value.strip() for value in terminal_values):
                        if terminal and terminal.casefold() != "none":
                            _reference(
                                index, connection, "terminal-cluster",
                                _key("cluster", terminal, None), source, line,
                            )
        elif command.startswith("*loading sequence"):
            loading_error = _validate_boundary_loading_sequence(records)
            if loading_error is not None:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310", severity="error", message=loading_error,
                    line=command_line.number, source=source,
                ))
            for ordinal, line in enumerate(records, start=1):
                options = _record_options(line)
                changed = options.get("change")
                if not changed:
                    continue
                change = _entity(
                    index, "load-change", f"{changed}:{ordinal}", source, line, None,
                    {key: value for key, value in options.items() if key != "change"},
                )
                _reference(
                    index, change, "changes-boundary-condition",
                    _key("boundary-condition", changed, None), source, line,
                )
        elif command.startswith("*solver"):
            if not records:
                continue
            values = _fields(records[0].text)
            if not values or not values[0].lstrip("+-").isdigit():
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E312", severity="error",
                    message="BOUNDARY solver schedule must be 1 or 2",
                    line=records[0].number, source=source,
                ))
                continue
            schedule = int(values[0])
            if not any(item.kind == "solver" for item in index.entities):
                _entity(
                    index, "solver", "1", source, command_line, None,
                    {"type": "pardiso", "syntax": "implicit-default"},
                )
            selector = _entity(
                index, "solver-schedule", f"line-{records[0].number}", source, records[0], None,
                {"schedule": schedule},
            )
            if schedule not in {1, 2}:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E312", severity="error",
                    message="BOUNDARY solver schedule must be 1 or 2",
                    line=records[0].number, source=source,
                ))
                continue
            for solver_id in range(1, schedule + 1):
                _reference(
                    index, selector, "uses-solver", _key("solver", str(solver_id), None),
                    source, records[0], {"iteration_policy": schedule},
                )

    clusters = [item for item in index.entities if item.kind == "cluster"]
    active_crack: SemanticEntity | None = None
    crack_ordinal = 0
    for line in _top_block_body(all_lines, "CRACK"):
        values = _fields(line.text)
        if values and values[0] in {"101", "201", "301"} and not line.text[:1].isspace():
            crack_ordinal += 1
            active_crack = _entity(
                index, "crack", str(crack_ordinal), source, line, None,
                {"type": int(values[0])},
            )
            continue
        if active_crack is None or "-approximation" not in line.text.casefold():
            continue
        values = _fields(line.text)
        if not values:
            continue
        selector = values[0]
        if selector.isdigit() and 1 <= int(selector) <= len(clusters):
            approximation = int(selector)
            _reference(
                index, active_crack, "targets-cluster", clusters[approximation - 1].key,
                source, line, {"approximation": approximation},
            )
        elif not selector.isdigit():
            _reference(
                index, active_crack, "targets-cluster",
                _key("cluster", selector, None), source, line,
                {"cluster": selector.casefold()},
            )
        else:
            approximation = int(selector)
            _reference(
                index, active_crack, "targets-cluster",
                _key("cluster", f"approximation-{approximation}", None), source, line,
                {"approximation": approximation},
            )
    augment_crack_capability_records(index, source, all_lines)


def build_semantic_index(
    sources: Iterable[tuple[Path, str, Iterable[SourceLine]]], *, resolve: bool = True
) -> SemanticIndex:
    """Index only explicit FE records whose grammar is documented in the registry."""
    source_entries = [
        (path, source, tuple(lines)) for path, source, lines in sources
    ]
    declared_cluster_names: list[str | None] = []
    active_declaration: int | None = None
    for _path, _source, lines in source_entries:
        for prescan_line, prescan_body in _command_spans(lines):
            prescan_command = prescan_line.text.lstrip().split(",", 1)[0].upper()[:5]
            prescan_records = [
                line for line in prescan_body
                if line.stripped and not line.stripped.startswith("**")
            ]
            if prescan_command == "*TYPE":
                declared_cluster_names.append(None)
                active_declaration = len(declared_cluster_names) - 1
            elif (
                prescan_command == "*NAME" and prescan_records
                and active_declaration is not None
            ):
                declared_cluster_names[active_declaration] = (
                    prescan_records[0].stripped.casefold()
                )
                active_declaration = None

    index = SemanticIndex()
    cluster: str | None = None
    cluster_open = False
    selection_capacity: int | None = None
    dimensions_seen = False
    cluster_population_started = False
    dimension_allocations: list[tuple[SemanticEntity, str, tuple[int, int, int, int]]] = []
    cluster_declaration_ordinal = 0
    pending_cluster_records: list[SemanticEntity] = []
    registered_cluster_commands = load_registry()["cluster_commands"]
    registered_occurrences: dict[str, int] = {}
    for _path, source, lines in source_entries:
        for command_line, body in _command_spans(lines):
            command = command_line.text.lstrip().split(",", 1)[0].upper()[:5]
            options = _options(command_line)
            records = [line for line in body if line.stripped and not line.stripped.startswith("**")]
            matched_commands = [
                item for item in registered_cluster_commands
                if command_line.text.lstrip().casefold().startswith(
                    str(item["dispatch_prefix"]).casefold()
                )
            ]
            if len(matched_commands) == 1:
                registered = matched_commands[0]
                capability_id = str(registered["id"])
                registered_occurrences[capability_id] = (
                    registered_occurrences.get(capability_id, 0) + 1
                )
                occurrence = registered_occurrences[capability_id]
                parameters = _registered_parameter_values(
                    registered, command_line, body, source,
                )
                defaults = {
                    str(item["name"]): item["default"]
                    for item in registered.get("parameters", []) if "default" in item
                }
                index.capability_records.append(RegisteredConstruct(
                    id=f"{capability_id}[{occurrence}]@{source}:{command_line.number}",
                    capability_id=capability_id,
                    canonical=str(registered["canonical"]),
                    occurrence=occurrence,
                    location=_location(source, command_line),
                    parameters=parameters,
                    defaults=defaults,
                    operations=operational_support(registered),
                ))
                _validate_registered_values(index, registered, parameters)

            if command == "*TYPE":
                if cluster_open:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="a new cluster TYPE requires the previous cluster to STOP",
                        line=command_line.number, source=source,
                    ))
                cluster_open = True
                cluster_declaration_ordinal += 1
                cluster = None
                selection_capacity = None
                dimensions_seen = False
                cluster_population_started = False
                if (
                    len(records) != 1
                    or not records[0].stripped.casefold().startswith("soli")
                ):
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="cluster TYPE requires exactly one solid record",
                        line=command_line.number, source=source,
                    ))
                representation = records[0].stripped.casefold() if records else ""
                declaration = _entity(
                    index, "cluster-declaration", str(cluster_declaration_ordinal),
                    source, command_line, None,
                    {"representation": representation},
                )
                if declared_cluster_names[cluster_declaration_ordinal - 1] is None:
                    cluster = f"noname{cluster_declaration_ordinal}"
                    implicit_cluster = _entity(
                        index, "cluster", cluster, source, command_line, None,
                        {
                            "declaration_ordinal": cluster_declaration_ordinal,
                            "implicit_name": True,
                        },
                    )
                    _reference(
                        index, declaration, "declares-cluster",
                        implicit_cluster.key, source, command_line,
                    )
                    pending_cluster_records = []
                else:
                    pending_cluster_records = [declaration]
                continue

            if not cluster_open and command != "*STOP":
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310", severity="error",
                    message="TYPE must be the first command of each cluster",
                    line=command_line.number, source=source,
                ))
                cluster_open = True

            if command == "*DIME":
                values = _fields(records[0].text) if records else []
                names = (
                    "node_capacity", "element_capacity",
                    "selection_count", "section_capacity",
                )
                owner = cluster or (
                    declared_cluster_names[cluster_declaration_ordinal - 1]
                    if cluster_declaration_ordinal else None
                ) or f"noname{cluster_declaration_ordinal}"
                dimensions = _entity(
                    index, "cluster-dimensions", f"{source}:{command_line.number}",
                    source, command_line, cluster,
                    {name: values[position] if position < len(values) else None
                     for position, name in enumerate(names)} | {"owner": owner},
                )
                if dimensions_seen:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="cluster may contain only one DIMENSIONS command",
                        line=command_line.number, source=source,
                    ))
                if cluster_population_started:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="DIMENSIONS must precede allocated cluster records",
                        line=command_line.number, source=source,
                    ))
                dimensions_seen = True
                parsed_dimensions: tuple[int, int, int, int] | None = None
                try:
                    parsed_values = tuple(int(value) for value in values)
                    if len(parsed_values) != 4 or any(value < 0 for value in parsed_values):
                        raise ValueError
                    parsed_dimensions = parsed_values  # type: ignore[assignment]
                except ValueError:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="DIMENSIONS requires exactly four nonnegative integers",
                        line=command_line.number, source=source,
                    ))
                    selection_capacity = None
                else:
                    selection_capacity = parsed_dimensions[2]
                    dimension_allocations.append((dimensions, owner, parsed_dimensions))
                if cluster:
                    _reference(
                        index, dimensions, "configures-cluster",
                        _key("cluster", cluster, None), source, command_line,
                    )
                else:
                    pending_cluster_records.append(dimensions)
                continue

            if command in {"*NODE", "*ELEM", "*NGEN", "*NCOP", "*ELGE", "*SELE", "*SECT"}:
                cluster_population_started = True

            if command == "*NAME":
                name_tokens = (
                    records[0].text.split("#", 1)[0].replace(",", " ").split()
                    if len(records) == 1 else []
                )
                reserved_names = {
                    "input", "solver", "moisture", "boundary", "constitutive",
                    "failure", "crack", "tables", "statistical", "ufunctions",
                    "user", "clusters", "materials",
                }
                if (
                    len(name_tokens) != 1 or len(name_tokens[0]) > 80
                    or name_tokens[0].casefold() in reserved_names
                ):
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message=(
                            "cluster NAME requires one non-reserved token of at most "
                            "80 characters"
                        ),
                        line=command_line.number, source=source,
                    ))
                    continue
                cluster = name_tokens[0].casefold()
                _entity(
                    index, "cluster", cluster, source, records[0], None,
                    {
                        "declaration_ordinal": cluster_declaration_ordinal,
                        "implicit_name": False,
                    },
                )
                for pending in pending_cluster_records:
                    _reference(
                        index, pending,
                        "declares-cluster" if pending.kind == "cluster-declaration"
                        else "configures-cluster",
                        _key("cluster", cluster, None), source, records[0],
                    )
                pending_cluster_records = []
                continue

            if command == "*INCL":
                include = _entity(
                    index, "include-operation", f"{source}:{command_line.number}",
                    source, command_line, cluster, {"file": options.get("FILE")},
                )
                if cluster:
                    _reference(
                        index, include, "targets-cluster",
                        _key("cluster", cluster, None), source, command_line,
                    )
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

            elif command in {"*NGEN", "*NCOP"} and cluster:
                operation_name = "ngen" if command == "*NGEN" else "ncopy"
                output_set = options.get("NSET")
                if command == "*NCOP":
                    ncopy_tokens = [token for token in re.split(
                        r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                    ) if token]
                    if not (
                        len(ncopy_tokens) == 1
                        or (
                            len(ncopy_tokens) == 3
                            and ncopy_tokens[1].casefold()[:3] == "nse"
                            and 0 < len(ncopy_tokens[2]) <= 20
                        )
                    ):
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message="NCOPY accepts only optional NSET=<name> targeting",
                            line=command_line.number, source=source,
                        ))
                if output_set:
                    _entity(
                        index, "node-set", output_set, source, command_line, cluster,
                        {"definition": "generated-command-membership", "generator": operation_name},
                    )
                generation = _entity(
                    index, "node-generation", f"{source}:{command_line.number}",
                    source, command_line, cluster,
                    {"operation": operation_name, "output_set": output_set},
                )
                generation_records = records[1:] if command == "*NGEN" and "ARC" in options else records
                for line in generation_records:
                    values = _fields(line.text)
                    if command == "*NCOP":
                        if not values:
                            continue
                        source_set_key = _key("node-set", values[0], cluster)
                        ncopy_error: str | None = None
                        if len(values) != 6:
                            ncopy_error = "NCOPY rows require source set, count, offset, dx, dy, and dz"
                        elif len(values[0]) > 20:
                            ncopy_error = "NCOPY source-set names may contain at most 20 characters"
                        else:
                            try:
                                copy_count = int(values[1])
                                label_offset = int(values[2])
                                translations = [_fortran_real(item) for item in values[3:6]]
                                if (
                                    not 1 <= copy_count <= 100_000 or label_offset == 0
                                    or not all(math.isfinite(item) for item in translations)
                                ):
                                    raise ValueError
                            except ValueError:
                                ncopy_error = (
                                    "NCOPY requires count 1..100000, nonzero integer offset, "
                                    "and finite translations"
                                )
                        source_members = _set_member_entities(index, source_set_key, "node")
                        if ncopy_error is None and not source_members:
                            ncopy_error = "NCOPY source set must already exist and contain nodes"
                        if ncopy_error is None and any(
                            int(member.name) + copy_index * label_offset <= 0
                            for member in source_members
                            for copy_index in range(1, copy_count + 1)
                        ):
                            ncopy_error = "NCOPY generated node labels must remain positive"
                        if ncopy_error is not None:
                            index.diagnostics.append(Diagnostic(
                                code="BSAM-E310", severity="error", message=ncopy_error,
                                line=line.number, source=source,
                            ))
                        _reference(
                            index, generation, "copies-node-set",
                            source_set_key, source, line,
                        )
                        if len(values) >= 3:
                            try:
                                copy_count, label_offset = int(values[1]), int(values[2])
                            except ValueError:
                                continue
                            if 0 < copy_count <= 100_000 and label_offset != 0:
                                for member in _set_member_entities(index, source_set_key, "node"):
                                    try:
                                        source_label = int(member.name)
                                    except ValueError:
                                        continue
                                    for copy_index in range(1, copy_count + 1):
                                        label = source_label + copy_index * label_offset
                                        if label <= 0:
                                            continue
                                        generated = _entity(
                                            index, "node", str(label), source, line, cluster,
                                            {"generated_by": "ncopy", "source_node": source_label},
                                        )
                                        if output_set:
                                            _reference(
                                                index, generated, "member-of",
                                                _key("node-set", output_set, cluster), source, line,
                                            )
                        continue
                    if len(values) < 2:
                        continue
                    if "ARC" in options:
                        targets = ((values[0], "node"), (values[1], "node"))
                    else:
                        first_key, first_kind = _cluster_nodal_target_key(
                            index, values[0], cluster,
                        )
                        first_target_kind = "node-set" if first_kind == "targets-node-set" else "node"
                        targets = ((values[0], first_target_kind), (values[1], first_target_kind))
                    for endpoint, target_kind in targets:
                        _reference(
                            index, generation, f"uses-{target_kind}-endpoint",
                            _key(target_kind, endpoint, cluster), source, line,
                        )
                    try:
                        increment = int(values[2])
                    except (IndexError, ValueError):
                        continue
                    endpoint_pairs: list[tuple[int, int]] = []
                    if targets[0][1] == "node":
                        try:
                            start_label, end_label = int(values[0]), int(values[1])
                        except ValueError:
                            continue
                        known_keys = {item.key for item in index.entities}
                        if (
                            _key("node", str(start_label), cluster) not in known_keys
                            or _key("node", str(end_label), cluster) not in known_keys
                        ):
                            continue
                        endpoint_pairs.append((start_label, end_label))
                    else:
                        first_members = _set_member_entities(
                            index, _key("node-set", values[0], cluster), "node",
                        )
                        second_members = _set_member_entities(
                            index, _key("node-set", values[1], cluster), "node",
                        )
                        if len(first_members) != len(second_members):
                            continue
                        try:
                            endpoint_pairs.extend(
                                (int(first.name), int(second.name))
                                for first, second in zip(first_members, second_members)
                            )
                        except ValueError:
                            continue
                    for start_label, end_label in endpoint_pairs:
                        if output_set:
                            output_set_key = _key("node-set", output_set, cluster)
                            endpoint_keys = {
                                _key("node", str(start_label), cluster),
                                _key("node", str(end_label), cluster),
                            }
                            for endpoint_entity in index.entities:
                                if endpoint_entity.key in endpoint_keys:
                                    _reference_once(
                                        index, endpoint_entity, "member-of",
                                        output_set_key, source, line,
                                    )
                        for label in _bounded_generated_labels(
                            start_label, end_label, increment,
                        ):
                            generated = _entity(
                                index, "node", str(label), source, line, cluster,
                                {
                                    "generated_by": "ngen", "start_node": start_label,
                                    "end_node": end_label,
                                },
                            )
                            if output_set:
                                _reference(
                                    index, generated, "member-of",
                                    _key("node-set", output_set, cluster), source, line,
                                )

            elif command == "*ELGE" and cluster:
                elgen_options = [
                    field.strip()
                    for field in command_line.text.split("#", 1)[0][:240].split(",")[1:]
                    if field.strip()
                ]
                requested_type = ""
                header_error: str | None = None
                if len(elgen_options) != 1 or "=" not in elgen_options[0]:
                    header_error = "ELGEN requires exactly one TYPE=<element-type> option"
                else:
                    option_name, option_value = elgen_options[0].split("=", 1)
                    requested_type = option_value.strip().upper()
                    if (
                        option_name.strip().upper() != "TYPE"
                        or requested_type not in {
                            "C3D8", "Y3D8", "X3D8", "LC3D8", "C3D4", "C3D10",
                        }
                    ):
                        header_error = (
                            "ELGEN TYPE must select C3D8, Y3D8, X3D8, LC3D8, "
                            "C3D4, or C3D10"
                        )
                if header_error is not None:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error", message=header_error,
                        line=command_line.number, source=source,
                    ))
                generation = _entity(
                    index, "element-generation", f"{source}:{command_line.number}",
                    source, command_line, cluster, {"element_type": requested_type},
                )
                for line in records:
                    values = _fields(line.text)
                    row_error: str | None = None
                    if len(values) != 7:
                        row_error = (
                            "ELGEN rows require seed, three counts, and three node offsets"
                        )
                    try:
                        seed_label = int(values[0])
                        rows, columns, layers = (int(item) for item in values[1:4])
                        row_offset, column_offset, layer_offset = (
                            int(item) for item in values[4:7]
                        )
                    except (IndexError, ValueError):
                        row_error = "ELGEN rows require exactly seven integers"
                    if row_error is None and (
                        seed_label <= 0 or rows < 1 or columns < 1 or layers < 1
                        or rows * columns * layers > 100_001
                    ):
                        row_error = (
                            "ELGEN requires a positive seed, positive counts, and at most "
                            "100001 grid positions per row"
                        )
                    if row_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=row_error,
                            line=line.number, source=source,
                        ))
                        continue
                    seed_key = _key("element", str(seed_label), cluster)
                    _reference(
                        index, generation, "uses-seed-element", seed_key, source, line,
                    )
                    seeds = [item for item in index.entities if item.key == seed_key]
                    if len(seeds) != 1:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message="ELGEN seed element must resolve uniquely before generation",
                            line=line.number, source=source,
                        ))
                        continue
                    seed = seeds[0]
                    if str(seed.attributes.get("element_type") or "").upper() != requested_type:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message="ELGEN TYPE must match the seed element topology",
                            line=line.number, source=source,
                        ))
                        continue
                    try:
                        seed_connectivity = [
                            int(item) for item in seed.attributes.get("connectivity", [])
                        ]
                    except (TypeError, ValueError):
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message="ELGEN seed connectivity must contain integer node labels",
                            line=line.number, source=source,
                        ))
                        continue
                    generated_offsets = [
                        layer * layer_offset + column * column_offset + row * row_offset
                        for layer in range(layers)
                        for column in range(columns)
                        for row in range(rows)
                        if layer * layer_offset + column * column_offset + row * row_offset != 0
                    ]
                    generated_labels = range(
                        seed_label + 1, seed_label + len(generated_offsets) + 1,
                    )
                    existing_element_keys = {
                        item.key for item in index.entities if item.kind == "element"
                    }
                    if any(
                        label <= 0
                        or _key("element", str(label), cluster) in existing_element_keys
                        for label in generated_labels
                    ):
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message="ELGEN generated element labels must be positive and unique",
                            line=line.number, source=source,
                        ))
                    known_node_keys = {
                        item.key for item in index.entities if item.kind == "node"
                    }
                    if any(
                        node_label + offset <= 0
                        or _key("node", str(node_label + offset), cluster) not in known_node_keys
                        for offset in generated_offsets
                        for node_label in seed_connectivity
                    ):
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message=(
                                "ELGEN shifted connectivity must contain positive existing nodes"
                            ),
                            line=line.number, source=source,
                        ))
                    generated_label = seed_label
                    for offset in generated_offsets:
                        generated_label += 1
                        connectivity = [label + offset for label in seed_connectivity]
                        element = _entity(
                            index, "element", str(generated_label), source, line,
                            cluster,
                            {
                                "element_type": requested_type,
                                "connectivity": [str(item) for item in connectivity],
                                "generated_by": "elgen", "seed_element": seed_label,
                            },
                        )
                        for position, node_label in enumerate(connectivity, start=1):
                            _reference(
                                index, element, "connectivity",
                                _key("node", str(node_label), cluster), source, line,
                                {"position": position},
                            )

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
                section_options = [
                    field.strip()
                    for field in command_line.text.split("#", 1)[0][:240].split(",")[1:]
                    if field.strip()
                ]
                parsed_section_options: dict[str, str | None] = {}
                section_error: str | None = None
                for field in section_options:
                    if "=" in field:
                        option_name, option_value = field.split("=", 1)
                        name = option_name.strip().upper()
                        value = option_value.strip()
                    else:
                        name, value = field.strip().upper(), None
                    if name not in {"ELSET", "LAYERS", "CONNECTION"}:
                        section_error = f"unknown SECTION option {name or field}"
                        break
                    if name in parsed_section_options:
                        section_error = f"duplicate SECTION option {name}"
                        break
                    if name == "CONNECTION" and value is not None:
                        section_error = "SECTION CONNECTION is a flag and takes no value"
                        break
                    if name != "CONNECTION" and not value:
                        section_error = f"SECTION {name} requires a value"
                        break
                    parsed_section_options[name] = value
                elset = parsed_section_options.get("ELSET")
                connection_form = "CONNECTION" in parsed_section_options
                try:
                    layer_count = int(str(parsed_section_options.get("LAYERS", "")))
                    if not 1 <= layer_count <= 99_999:
                        raise ValueError
                except ValueError:
                    layer_count = 0
                    section_error = section_error or (
                        "SECTION LAYERS must be an integer from 1 through 99999"
                    )
                if not elset:
                    section_error = section_error or "SECTION requires ELSET=<name>"
                elif len(elset) > 20:
                    section_error = section_error or (
                        "SECTION ELSET names may contain at most 20 characters"
                    )
                if section_error is not None:
                    _table_error(
                        index, "BSAM-E310", section_error, source, command_line,
                    )
                if elset and len(elset) <= 20 and layer_count > 0:
                    attributes: dict[str, Any] = {
                        "layers": layer_count,
                        "connection": connection_form,
                    }
                    layer_rows: list[tuple[int, float, SourceLine]] = []
                    try:
                        if len(records) != layer_count:
                            raise ValueError
                        for line in records:
                            fields = _record_fields(line)
                            if len(fields) != 2:
                                raise ValueError
                            thickness = _fortran_real(fields[0])
                            material_id = int(fields[1])
                            if (
                                not math.isfinite(thickness) or thickness <= 0
                                or material_id <= 0
                            ):
                                raise ValueError
                            layer_rows.append((material_id, thickness, line))
                        total_thickness = sum(item[1] for item in layer_rows)
                        if not math.isfinite(total_thickness) or total_thickness <= 0:
                            raise ValueError
                    except (IndexError, ValueError):
                        _table_error(
                            index, "BSAM-E310",
                            (
                                "SECTION requires exactly LAYERS two-field rows with finite "
                                "positive thickness and positive definition IDs"
                            ),
                            source, command_line,
                        )
                    else:
                        attributes.update({
                            "layers": layer_count,
                            "layer_thicknesses": [
                                item[1] / total_thickness for item in layer_rows
                            ],
                            (
                                "layer_constitutive_ids" if connection_form
                                else "layer_material_ids"
                            ): [item[0] for item in layer_rows],
                        })
                    section = _entity(
                        index, "section", elset, source, command_line, cluster, attributes,
                    )
                    _reference(index, section, "assigns-to", _key("element-set", elset, cluster), source, command_line)
                    for position, (material_id, _thickness, line) in enumerate(
                        layer_rows, start=1,
                    ):
                        _reference(
                            index, section,
                            "uses-constitutive" if connection_form else "uses-material",
                            _key(
                                "constitutive" if connection_form else "material",
                                str(material_id), None,
                            ),
                            source, line,
                            {"position": position},
                        )
            elif command == "*CONS" and cluster:
                value = _fields(records[0].text) if len(records) == 1 else []
                try:
                    constitutive_id = int(value[0])
                    if len(value) != 1 or constitutive_id <= 0:
                        raise ValueError
                except (IndexError, ValueError):
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message=(
                            "cluster CONSTITUTIVE requires exactly one positive "
                            "declaration-order ID"
                        ),
                        line=command_line.number, source=source,
                    ))
                else:
                    assignment = _entity(
                        index, "cluster-constitutive", "assignment", source,
                        command_line, cluster, {"constitutive": constitutive_id},
                    )
                    _reference(
                        index, assignment, "uses-constitutive",
                        _key("constitutive", str(constitutive_id), None), source, records[0],
                    )
            elif command == "*BOUN" and cluster:
                format_name = str(options.get("FORMAT") or "ABAQUS").upper()[:4]
                for line in records:
                    values = _fields(line.text)
                    if not values:
                        continue
                    target = values[0]
                    boundary = _entity(
                        index, "nodal-boundary", f"{source}:{line.number}", source,
                        line, cluster, {"format": format_name, "target": target},
                    )
                    target_key, reference_kind = _cluster_nodal_target_key(
                        index, target, cluster, node_only=format_name == "LIST",
                    )
                    _reference(
                        index, boundary, reference_kind, target_key, source, line,
                        {"format": format_name},
                    )
            elif command == "*LOAD" and cluster:
                load_tokens = [token for token in re.split(
                    r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                ) if token]
                if len(load_tokens) != 1:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="LOAD does not accept command-line options",
                        line=command_line.number, source=source,
                    ))
                for line in records:
                    values = _fields(line.text)
                    if not values:
                        continue
                    target = values[0]
                    load_error: str | None = None
                    if len(values) != 3:
                        load_error = "LOAD rows require exactly target, degree of freedom, and value"
                    elif len(target) > 20 and not target.lstrip("+").isdigit():
                        load_error = "LOAD node-set targets may contain at most 20 characters"
                    else:
                        try:
                            degree = int(values[1])
                            magnitude = _fortran_real(values[2])
                            if degree not in {1, 2, 3} or not math.isfinite(magnitude):
                                raise ValueError
                        except ValueError:
                            load_error = "LOAD requires degree of freedom 1..3 and a finite real value"
                    if load_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=load_error,
                            line=line.number, source=source,
                        ))
                    load = _entity(
                        index, "nodal-load", f"{source}:{line.number}", source,
                        line, cluster, {"target": target},
                    )
                    target_key, reference_kind = _cluster_nodal_target_key(
                        index, target, cluster,
                    )
                    _reference(index, load, reference_kind, target_key, source, line)
            elif command == "*FIEL" and cluster:
                variables = options.get("VARIABLES")
                field_tokens = [token for token in re.split(
                    r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                ) if token]
                field_error: str | None = None
                variable_count = 0
                if not (
                    len(field_tokens) == 3
                    and field_tokens[1].casefold()[:3] == "var"
                ):
                    field_error = "FIELD requires exactly VARIABLES=<integer(1..10)>"
                else:
                    try:
                        variable_count = int(field_tokens[2])
                        if not 1 <= variable_count <= 10:
                            raise ValueError
                    except ValueError:
                        field_error = "FIELD VARIABLES must be an integer from 1 through 10"
                if field_error is not None:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error", message=field_error,
                        line=command_line.number, source=source,
                    ))
                for line in records:
                    values = _fields(line.text)
                    if not values:
                        continue
                    target = values[0]
                    row_error: str | None = None
                    if field_error is None and len(values) != variable_count + 1:
                        row_error = f"FIELD rows require one target and {variable_count} values"
                    elif len(target) > 20 and not target.lstrip("+").isdigit():
                        row_error = "FIELD node-set targets may contain at most 20 characters"
                    elif field_error is None:
                        try:
                            field_values = [_fortran_real(item) for item in values[1:]]
                            if not all(math.isfinite(item) for item in field_values):
                                raise ValueError
                        except ValueError:
                            row_error = "FIELD values must be finite reals"
                    if row_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=row_error,
                            line=line.number, source=source,
                        ))
                    field_value = _entity(
                        index, "nodal-field", f"{source}:{line.number}", source,
                        line, cluster, {"target": target, "variables": variables},
                    )
                    target_key, reference_kind = _cluster_nodal_target_key(
                        index, target, cluster,
                    )
                    _reference(
                        index, field_value, reference_kind, target_key, source, line,
                        {"variables": variables},
                    )
            elif command == "*SELE" and cluster:
                raw_selection_id = options.get("ID")
                if not raw_selection_id:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="SELECTION requires an explicit positive ID",
                        line=command_line.number, source=source,
                    ))
                    continue
                try:
                    selection_number = int(raw_selection_id)
                    if selection_number <= 0:
                        raise ValueError
                except ValueError:
                    continue
                if (
                    selection_capacity is not None
                    and selection_number > selection_capacity
                ):
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message=(
                            f"SELECTION ID {selection_number} exceeds DIMENSIONS "
                            f"selection_count {selection_capacity}"
                        ),
                        line=command_line.number, source=source,
                    ))
                    continue
                raw_selection_type = str(options.get("TYPE") or "NODE")
                if raw_selection_type not in {"NODE", "ELEMENT"}:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="SELECTION TYPE must be uppercase NODE or ELEMENT",
                        line=command_line.number, source=source,
                    ))
                    continue
                if not records:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="SELECTION requires at least one member target",
                        line=command_line.number, source=source,
                    ))
                selection_id = str(selection_number)
                selection_type = raw_selection_type[:4]
                member_kind = "element" if selection_type == "ELEM" else "node"
                selection = _entity(
                    index, "selection", selection_id, source, command_line, cluster,
                    {"selection_type": member_kind},
                )
                set_kind = f"{member_kind}-set"
                known_keys = {item.key for item in index.entities}
                named_set_count = 0
                for line in records:
                    for target in _fields(line.text):
                        set_key = _key(set_kind, target, cluster)
                        if set_key in known_keys:
                            named_set_count += 1
                            target_key, reference_kind = set_key, f"selects-{set_kind}"
                        elif target.isdigit():
                            target_key = _key(member_kind, target, cluster)
                            reference_kind = f"selects-{member_kind}"
                        else:
                            target_key, reference_kind = set_key, f"selects-{set_kind}"
                        _reference(
                            index, selection, reference_kind, target_key, source, line,
                        )
                if named_set_count > 10:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="SELECTION may contain at most ten named sets",
                        line=command_line.number, source=source,
                    ))
            elif command == "*ORIE" and cluster:
                orientation_name = str(options.get("NAME") or "").upper()
                member_kind = "element" if orientation_name == "ORI-ELE" else "node"
                set_kind = f"{member_kind}-set"
                known_keys = {item.key for item in index.entities}
                orientation_tokens = [token for token in re.split(
                    r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                ) if token]
                orientation_error: str | None = None
                if not (
                    len(orientation_tokens) == 3
                    and orientation_tokens[1].casefold() == "name"
                    and orientation_tokens[2].upper() in {"ORI", "ORI-NODE", "ORI-ELE"}
                ):
                    orientation_error = "ORIENTATION requires exactly NAME=ORI|ORI-NODE|ORI-ELE"
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error", message=orientation_error,
                        line=command_line.number, source=source,
                    ))
                for line in records:
                    values = _fields(line.text)
                    if not values:
                        continue
                    target = values[0]
                    row_error: str | None = None
                    numeric_orientation: list[float] = []
                    if len(values) != 8:
                        row_error = "ORIENTATION rows require one target, six vector values, and fiber volume"
                    elif len(target) > 20 and not target.lstrip("+").isdigit():
                        row_error = "ORIENTATION set targets may contain at most 20 characters"
                    else:
                        try:
                            numeric_orientation = [_fortran_real(item) for item in values[1:]]
                            if not all(math.isfinite(item) for item in numeric_orientation):
                                raise ValueError
                        except ValueError:
                            row_error = "ORIENTATION values must be finite reals"
                    if row_error is None and member_kind == "element":
                        v1, v3 = numeric_orientation[:3], numeric_orientation[3:6]
                        if not any(v1) or not any(v3):
                            row_error = "element ORIENTATION V1 and V3 must be nonzero"
                        elif abs(sum(left * right for left, right in zip(v1, v3))) > 1.0e-8:
                            row_error = "element ORIENTATION V1 and V3 must be orthogonal within 1e-8"
                    if row_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=row_error,
                            line=line.number, source=source,
                        ))
                    orientation = _entity(
                        index, "orientation-record", f"{source}:{line.number}",
                        source, line, cluster,
                        {"target": target, "target_kind": member_kind, "name": orientation_name},
                    )
                    set_key = _key(set_kind, target, cluster)
                    if set_key in known_keys:
                        target_key, reference_kind = set_key, f"targets-{set_kind}"
                    elif target.isdigit():
                        target_key = _key(member_kind, target, cluster)
                        reference_kind = f"targets-{member_kind}"
                    else:
                        target_key, reference_kind = set_key, f"targets-{set_kind}"
                    _reference(
                        index, orientation, reference_kind, target_key, source, line,
                    )
            elif command in {"*SHIF", "*SCAL", "*FLIP", "*TRAN"} and cluster:
                operation_name = {
                    "*SHIF": "shift", "*SCAL": "scale",
                    "*FLIP": "flip", "*TRAN": "transform",
                }[command]
                nset = options.get("NSET") if command in {"*SHIF", "*SCAL"} else None
                attributes: dict[str, Any] = {
                    "operation": operation_name, "target": nset or "ALL",
                }
                if command in {"*SHIF", "*SCAL"}:
                    coordinate_tokens = [token for token in re.split(
                        r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                    ) if token][1:]
                    coordinate_error: str | None = None
                    if not coordinate_tokens:
                        pass
                    elif len(coordinate_tokens) == 1 and coordinate_tokens[0].casefold()[:3] == "all":
                        pass
                    elif (
                        len(coordinate_tokens) == 2
                        and coordinate_tokens[0].casefold()[:3] == "nse"
                        and 0 < len(coordinate_tokens[1]) <= 20
                    ):
                        pass
                    else:
                        coordinate_error = (
                            f"{operation_name.upper()} accepts only mutually exclusive "
                            "ALL or NSET=<name> command-line targeting"
                        )
                    vector: list[float] = []
                    if coordinate_error is None:
                        if len(records) != 1 or len(_fields(records[0].text)) != 3:
                            coordinate_error = f"{operation_name.upper()} requires exactly one three-real vector record"
                        else:
                            try:
                                vector = [_fortran_real(item) for item in _fields(records[0].text)]
                                if not all(math.isfinite(item) for item in vector):
                                    raise ValueError
                            except ValueError:
                                coordinate_error = f"{operation_name.upper()} vector values must be finite reals"
                    if coordinate_error is None and command == "*SCAL" and any(item == 0 for item in vector):
                        coordinate_error = "SCALE factors must be nonzero to avoid collapsing the mesh"
                    if coordinate_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=coordinate_error,
                            line=command_line.number, source=source,
                        ))
                if command == "*FLIP":
                    flip_tokens = [token for token in re.split(
                        r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                    ) if token]
                    valid_flip = (
                        len(flip_tokens) == 1
                        or (
                            len(flip_tokens) == 3
                            and flip_tokens[1].casefold() == "type"
                            and flip_tokens[2] in {"XY", "YX", "XZ", "ZX", "YZ", "ZY"}
                        )
                    )
                    if records or not valid_flip:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message=(
                                "FLIP accepts only an optional command-line "
                                "TYPE=XY|YX|XZ|ZX|YZ|ZY and no data records"
                            ),
                            line=command_line.number, source=source,
                        ))
                elif command == "*TRAN":
                    transform_tokens = [token for token in re.split(
                        r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                    ) if token][1:]
                    transform_error: str | None = None
                    inertia = False
                    position = 0
                    while transform_error is None and position < len(transform_tokens):
                        token = transform_tokens[position]
                        prefix = token.casefold()[:3]
                        if prefix == "ine":
                            inertia = True
                            position += 1
                        elif prefix == "fla":
                            if position + 1 >= len(transform_tokens):
                                transform_error = "TRANSFORM FLATTEN requires a finite real value"
                                break
                            try:
                                flatten = _fortran_real(transform_tokens[position + 1])
                                if not math.isfinite(flatten):
                                    raise ValueError
                            except ValueError:
                                transform_error = "TRANSFORM FLATTEN requires a finite real value"
                                break
                            position += 2
                        else:
                            transform_error = f"unknown TRANSFORM option {token}"
                    if transform_error is None and not inertia:
                        transform_error = "TRANSFORM requires the INERTIA option"
                    if transform_error is None and records:
                        transform_error = "TRANSFORM is command-line-only and cannot contain data records"
                    if transform_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=transform_error,
                            line=command_line.number, source=source,
                        ))
                if command in {"*SHIF", "*SCAL"} and records:
                    attributes["values"] = _fields(records[0].text)[:3]
                elif command == "*FLIP":
                    attributes["mapping"] = options.get("TYPE") or "XY"
                else:
                    attributes["inertia"] = "INERTIA" in options
                    if options.get("FLATTEN") is not None:
                        attributes["flatten"] = options["FLATTEN"]
                operation = _entity(
                    index, "coordinate-operation", f"{source}:{command_line.number}",
                    source, command_line, cluster, attributes,
                )
                if nset:
                    _reference(
                        index, operation, "targets-node-set",
                        _key("node-set", nset, cluster), source, command_line,
                    )
                else:
                    _reference(
                        index, operation, "targets-cluster",
                        _key("cluster", cluster, None), source, command_line,
                    )
            elif command == "*INTE" and cluster:
                integration_options = [
                    field.strip()
                    for field in command_line.text.split("#", 1)[0][:240].split(",")[1:]
                    if field.strip()
                ]
                if integration_options:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="INTEGRATION does not accept command-line options",
                        line=command_line.number, source=source,
                    ))
                cursor = 0
                replacement_counts: dict[str, int] = {}
                while cursor < len(body):
                    line = body[cursor]
                    if not line.stripped or line.stripped.startswith("**"):
                        cursor += 1
                        continue
                    values = _record_fields(line)
                    try:
                        element_label = int(values[0])
                        point_count = int(values[1])
                        if (
                            len(values) != 2 or element_label <= 0
                            or not 1 <= point_count <= 100_000
                        ):
                            raise ValueError
                    except (IndexError, ValueError):
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error",
                            message=(
                                "INTEGRATION headers require a positive element label and "
                                "point count from 1 through 100000"
                            ),
                            line=line.number, source=source,
                        ))
                        break
                    element_key = _key("element", str(element_label), cluster)
                    targets = [item for item in index.entities if item.key == element_key]
                    target_type = (
                        str(targets[0].attributes.get("element_type") or "").upper()
                        if len(targets) == 1 else ""
                    )
                    target_error: str | None = None
                    if len(targets) != 1:
                        target_error = (
                            "INTEGRATION target element must resolve uniquely before use"
                        )
                    elif target_type not in {"X3D8", "Y3D8"}:
                        target_error = "INTEGRATION is effective only for X3D8 and Y3D8 elements"
                    if target_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=target_error,
                            line=line.number, source=source,
                        ))
                    point_rows: list[list[float]] = []
                    point_error: str | None = None
                    for point_index in range(point_count):
                        point_cursor = cursor + point_index + 1
                        if point_cursor >= len(body):
                            point_error = (
                                "INTEGRATION header is not followed by its declared point rows"
                            )
                            break
                        point_line = body[point_cursor]
                        point_values = _record_fields(point_line)
                        try:
                            parsed_point = [_fortran_real(item) for item in point_values]
                            if (
                                not point_line.stripped
                                or point_line.stripped.startswith("**")
                                or len(parsed_point) != 4
                                or not all(math.isfinite(item) for item in parsed_point)
                            ):
                                raise ValueError
                        except ValueError:
                            point_error = (
                                "INTEGRATION point rows require four finite real values; "
                                "blank and comment rows cannot satisfy the declared count"
                            )
                            break
                        point_rows.append(parsed_point)
                    if point_error is not None:
                        index.diagnostics.append(Diagnostic(
                            code="BSAM-E310", severity="error", message=point_error,
                            line=line.number, source=source,
                        ))
                    replacement_counts[element_key] = (
                        replacement_counts.get(element_key, 0) + 1
                    )
                    integration = _entity(
                        index, "integration-scheme", f"{source}:{line.number}",
                        source, line, cluster,
                        {
                            "element": str(element_label),
                            "point_count": point_count,
                            "points": point_rows,
                            "replacement_order": replacement_counts[element_key],
                        },
                    )
                    _reference(
                        index, integration, "targets-element",
                        element_key, source, line,
                    )
                    if point_error is not None:
                        break
                    cursor += point_count + 1
            elif command in {"*BUIL", "*STOP"} and cluster:
                operation_name = "build" if command == "*BUIL" else "stop"
                stop_data = [
                    line for line in records
                    if line.stripped.casefold() not in {
                        "end clusters", "end approximation",
                    }
                ]
                if command == "*BUIL" and records:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="BUILD is command-only and cannot contain data records",
                        line=command_line.number, source=source,
                    ))
                elif command == "*STOP" and stop_data:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error",
                        message="STOP is command-only and cannot contain data records",
                        line=command_line.number, source=source,
                    ))
                topology = _entity(
                    index, "topology-operation", f"{source}:{command_line.number}",
                    source, command_line, cluster,
                    {
                        "operation": operation_name,
                        "effect": "update-elements-and-create-topology"
                        if command == "*BUIL" else "update-elements-and-finish-cluster",
                    },
                )
                _reference(
                    index, topology, "targets-cluster",
                    _key("cluster", cluster, None), source, command_line,
                )
                if command == "*STOP":
                    cluster_open = False
            elif command == "*TOLE" and cluster:
                tolerance_type = str(options.get("TYPE") or "PTOL").upper()
                value = _fields(records[0].text)[0] if records and _fields(records[0].text) else None
                tolerance_tokens = [token for token in re.split(
                    r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                ) if token]
                tolerance_error: str | None = None
                if not (
                    len(tolerance_tokens) == 1
                    or (
                        len(tolerance_tokens) == 3
                        and tolerance_tokens[1].casefold().startswith("ty")
                        and tolerance_tokens[2] in {"PTOL", "ITOL", "FTOL", "OTOL"}
                    )
                ):
                    tolerance_error = "TOLERANCE accepts only TYPE=PTOL|ITOL|FTOL|OTOL"
                elif len(records) != 1 or len(_fields(records[0].text)) != 1:
                    tolerance_error = "TOLERANCE requires exactly one real value record"
                else:
                    try:
                        numeric_tolerance = _fortran_real(value or "")
                        if not math.isfinite(numeric_tolerance) or numeric_tolerance < 0:
                            raise ValueError
                    except ValueError:
                        tolerance_error = "TOLERANCE value must be a nonnegative finite real"
                if tolerance_error is not None:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error", message=tolerance_error,
                        line=command_line.number, source=source,
                    ))
                setting = _entity(
                    index, "cluster-setting", f"{source}:{command_line.number}",
                    source, command_line, cluster,
                    {"setting": tolerance_type.casefold(), "value": value},
                )
                _reference(
                    index, setting, "targets-cluster",
                    _key("cluster", cluster, None), source, command_line,
                )
            elif (
                command == "*SPAC"
                or command == "*CRAC" and command_line.text.lstrip().upper().startswith("*CRACK SPACING")
            ) and cluster:
                spacing_tokens = [token for token in re.split(
                    r"[\s,=]+", command_line.text.split("#", 1)[0].strip(),
                ) if token][1:]
                if command == "*CRAC" and spacing_tokens and spacing_tokens[0].casefold().startswith("spac"):
                    spacing_tokens = spacing_tokens[1:]
                spacing_error: str | None = None
                prefixes = [token.casefold()[:3] for token in spacing_tokens]
                if records:
                    spacing_error = "SPACING is command-line-only and cannot contain data records"
                elif not spacing_tokens:
                    pass
                elif prefixes[0] in {"str", "rel"} and len(spacing_tokens) == 1:
                    pass
                elif prefixes[0] == "val" and len(spacing_tokens) == 2:
                    try:
                        spacing_value = _fortran_real(spacing_tokens[1])
                        if not math.isfinite(spacing_value) or spacing_value <= 0:
                            raise ValueError
                    except ValueError:
                        spacing_error = "SPACING VALUE requires a positive finite real"
                else:
                    spacing_error = "SPACING accepts exactly one of STRICT, RELAXED, or VALUE=<positive-real>"
                if spacing_error is not None:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error", message=spacing_error,
                        line=command_line.number, source=source,
                    ))
                mode = (
                    "relaxed" if "RELAXED" in options else
                    "value" if "VALUE" in options else
                    "strict"
                )
                setting = _entity(
                    index, "cluster-setting", f"{source}:{command_line.number}",
                    source, command_line, cluster,
                    {
                        "setting": "crack-spacing", "mode": mode,
                        "value": options.get("VALUE"),
                    },
                )
                _reference(
                    index, setting, "targets-cluster",
                    _key("cluster", cluster, None), source, command_line,
                )
            elif command == "*EXCL" and cluster:
                shape = (
                    "previous" if "PREVIOUS" in options else
                    "plane" if "PLANE" in options else "box"
                )
                side = "outside" if "OUTSIDE" in options else "inside"
                values = _fields(records[0].text) if records else []
                exclusion_tokens = [token.casefold()[:3] for token in re.split(
                    r"[\s,]+", command_line.text.split("#", 1)[0].strip(),
                ) if token][1:]
                shape_tokens = [token for token in exclusion_tokens if token in {"box", "pla", "pre"}]
                side_tokens = [token for token in exclusion_tokens if token in {"ins", "out"}]
                exclusion_error: str | None = None
                if (
                    any(token not in {"box", "pla", "pre", "ins", "out"} for token in exclusion_tokens)
                    or len(shape_tokens) > 1 or len(side_tokens) > 1
                    or "pre" in shape_tokens and side_tokens
                ):
                    exclusion_error = "EXCLUSION shape and side flags are type-valid and mutually exclusive"
                expected = 1 if shape == "previous" else 7 if shape == "plane" else 6
                numeric_values: list[float] = []
                if exclusion_error is None:
                    if len(records) != 1 or len(values) != expected:
                        exclusion_error = f"{shape.upper()} EXCLUSION requires exactly {expected} real values"
                    else:
                        try:
                            numeric_values = [_fortran_real(item) for item in values]
                            if not all(math.isfinite(item) for item in numeric_values):
                                raise ValueError
                        except ValueError:
                            exclusion_error = "EXCLUSION geometry values must be finite reals"
                if exclusion_error is None and shape == "box" and any(
                    numeric_values[index] > numeric_values[index + 3] for index in range(3)
                ):
                    exclusion_error = "BOX EXCLUSION minimum bounds must not exceed maximum bounds"
                if exclusion_error is None and shape == "plane":
                    if not any(numeric_values[index] != 0 for index in range(3, 6)):
                        exclusion_error = "PLANE EXCLUSION normal must be nonzero"
                    elif numeric_values[6] < 0:
                        exclusion_error = "PLANE EXCLUSION distance must be nonnegative"
                if exclusion_error is None and shape == "previous" and numeric_values[0] <= 0:
                    exclusion_error = "PREVIOUS EXCLUSION diameter must be positive"
                if exclusion_error is not None:
                    index.diagnostics.append(Diagnostic(
                        code="BSAM-E310", severity="error", message=exclusion_error,
                        line=command_line.number, source=source,
                    ))
                exclusion = _entity(
                    index, "exclusion-region", f"{source}:{command_line.number}",
                    source, command_line, cluster,
                    {"shape": shape, "side": side, "values": values},
                )
                _reference(
                    index, exclusion, "targets-cluster",
                    _key("cluster", cluster, None), source, command_line,
                )
            elif command == "*CRAC" and cluster and command_line.text.lstrip().upper().startswith(
                "*CRACK REGION"
            ):
                elset = options.get("ELSET")
                action = (
                    "ADD" if "ADD" in options else
                    "REMOVE" if "REMOVE" in options else "REPLACE"
                )
                if elset:
                    region = _entity(
                        index, "crack-region", f"{source}:{command_line.number}",
                        source, command_line, cluster,
                        {"action": action, "selector": "element-set", "element_set": elset},
                    )
                    _reference(
                        index, region, "targets-element-set",
                        _key("element-set", elset, cluster), source, command_line,
                    )
                else:
                    selector = (
                        "sphere" if "SPHERE" in options else
                        "cylinder" if "CYLINDER" in options else
                        "box" if "BOX" in options or "COORDINATES" in options else None
                    )
                    if selector is not None:
                        values = _fields(records[0].text) if records else []
                        region = _entity(
                            index, "crack-region", f"{source}:{command_line.number}",
                            source, command_line, cluster,
                            {"action": action, "selector": selector, "values": values},
                        )
                        _reference(
                            index, region, "targets-cluster",
                            _key("cluster", cluster, None), source, command_line,
                        )
    if cluster_open:
        last_source = source_entries[-1][1] if source_entries else "<root>"
        last_lines = source_entries[-1][2] if source_entries else ()
        last_line = last_lines[-1].number if last_lines else 1
        index.diagnostics.append(Diagnostic(
            code="BSAM-E310", severity="error",
            message="cluster is missing its final STOP command",
            line=last_line, source=last_source,
        ))
    for dimensions, owner, capacities in dimension_allocations:
        owner_key = owner.casefold()
        owned = [
            item for item in index.entities
            if str(item.attributes.get("cluster") or "").casefold() == owner_key
        ]
        counts = (
            sum(item.kind == "node" for item in owned),
            sum(item.kind == "element" for item in owned),
            max(
                (int(item.name) for item in owned if item.kind == "selection"),
                default=0,
            ),
            sum(item.kind == "section" for item in owned),
        )
        labels = ("node", "element", "selection", "section")
        for label, capacity, required in zip(labels, capacities, counts):
            if required > capacity:
                index.diagnostics.append(Diagnostic(
                    code="BSAM-E310", severity="error",
                    message=(
                        f"DIMENSIONS {label} capacity {capacity} is smaller than "
                        f"required count or ID {required}"
                    ),
                    line=dimensions.location.line,
                    source=dimensions.location.source,
                ))
    if resolve:
        index.resolve()
    return index
