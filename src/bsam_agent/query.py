"""Focused deterministic queries over the loss-preserving semantic model."""

from __future__ import annotations

from typing import Any

from .capabilities import find_capabilities
from .registry import load_registry
from .source_set import SourceSet


def query_model(
    source_set: SourceSet,
    query: str,
    *,
    capability: str | None = None,
    parameter: str | None = None,
    entity_id: str | None = None,
    entity_kind: str | None = None,
    entity_name: str | None = None,
    occurrence: int | None = None,
) -> dict[str, Any]:
    semantic = source_set.semantic_index().as_dict()
    records = semantic["capability_records"]
    entities = semantic["entities"]
    references = semantic["references"]
    normalized = query.strip().casefold().replace("_", "-")
    registry = load_registry()
    definitions_by_capability = {
        item["id"]: {parameter["name"].casefold(): parameter for parameter in item["parameters"]}
        for item in [*registry["top_level_blocks"], *registry["nested_constructs"]]
    }
    matches: list[dict[str, Any]]
    ambiguous = False

    if normalized in {"list-constructs", "list-capabilities"}:
        matches = list(records)
    elif normalized in {"inspect-construct", "inspect-capability"}:
        if not capability:
            raise ValueError("inspect-capability requires capability")
        resolved = find_capabilities(capability)
        identifiers = {item["id"] for item in resolved}
        matches = [item for item in records if item["capability_id"] in identifiers]
        if occurrence is not None:
            matches = [item for item in matches if item["occurrence"] == occurrence]
        ambiguous = len(identifiers) > 1
    elif normalized in {"get-parameter", "parameter"}:
        if not parameter:
            raise ValueError("get-parameter requires parameter")
        selected = records
        if capability:
            resolved = find_capabilities(capability)
            identifiers = {item["id"] for item in resolved}
            selected = [item for item in selected if item["capability_id"] in identifiers]
            ambiguous = False
        folded = parameter.casefold()
        matches = []
        for record in selected:
            definition = definitions_by_capability.get(record["capability_id"], {}).get(folded)
            if definition is None:
                continue
            canonical = definition["name"]
            explicit = canonical in record["parameters"]
            has_default = canonical in record["defaults"]
            matches.append({
                "record_id": record["id"],
                "capability_id": record["capability_id"],
                "canonical": record["canonical"],
                "occurrence": record["occurrence"],
                "parameter": canonical,
                "values": record["parameters"].get(canonical, []),
                "default": record["defaults"].get(canonical),
                "effective_source": (
                    "explicit" if explicit else "registered-default" if has_default else "missing"
                ),
                "operations": record["operations"],
            })
        ambiguous = ambiguous or len({item["capability_id"] for item in matches}) > 1
    elif normalized in {"list-editable-parameters", "editable-parameters"}:
        matches = []
        for record in records:
            if record.get("operations", {}).get("modify") not in {"implemented", "verified"}:
                continue
            definitions = definitions_by_capability.get(record["capability_id"], {})
            for canonical, values in record.get("parameters", {}).items():
                definition = definitions.get(str(canonical).casefold())
                if definition is None:
                    continue
                matches.append({
                    "record_id": record["id"],
                    "capability_id": record["capability_id"],
                    "canonical": record["canonical"],
                    "occurrence": record["occurrence"],
                    "parameter": definition["name"],
                    "value_type": definition.get("value_type"),
                    "allowed_values": definition.get("allowed_values"),
                    "values": values,
                    "default": record.get("defaults", {}).get(definition["name"]),
                    "operations": record["operations"],
                })
    elif normalized == "list-entities":
        matches = list(entities)
        if entity_kind:
            matches = [
                item for item in matches
                if str(item.get("kind", "")).casefold() == entity_kind.casefold()
            ]
        if entity_name:
            matches = [
                item for item in matches
                if str(item.get("name", "")).casefold() == entity_name.casefold()
            ]
    elif normalized in {"references-to", "references-from"}:
        if entity_id:
            selected_entities = [item for item in entities if item["id"] == entity_id]
        elif entity_kind and entity_name:
            selected_entities = [
                item for item in entities
                if str(item.get("kind", "")).casefold() == entity_kind.casefold()
                and str(item.get("name", "")).casefold() == entity_name.casefold()
            ]
        else:
            raise ValueError(
                f"{normalized} requires entity_id or both entity_kind and entity_name"
            )
        if not selected_entities:
            selector = entity_id or f"{entity_kind}:{entity_name}"
            raise ValueError(f"semantic entity was not found: {selector}")
        if len(selected_entities) != 1:
            matches = []
            ambiguous = True
        elif normalized == "references-from":
            matches = [
                item for item in references
                if item["source_entity_id"] == selected_entities[0]["id"]
            ]
        else:
            matches = [
                item for item in references
                if selected_entities[0]["id"] in item["target_entity_ids"]
            ]
    else:
        raise ValueError(f"unknown model query: {query}")

    return {
        "source_set_sha256": source_set.sha256,
        "query": normalized,
        "matches": matches,
        "summary": {"matches": len(matches), "ambiguous": ambiguous},
    }
