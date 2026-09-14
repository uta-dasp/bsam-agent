"""Focused deterministic queries over the loss-preserving semantic model."""

from __future__ import annotations

from typing import Any

from .capabilities import capability_manifest, find_capabilities
from .registry import load_registry
from .source_set import SourceSet


CANONICAL_QUERIES = (
    "list_entities",
    "list_boundary_conditions",
    "list_materials",
    "list_constitutives",
    "list_sets",
    "list_editable_parameters",
    "describe_parameter",
    "inspect_entity",
    "inspect_cluster",
    "references_to",
    "references_from",
    "describe_capability",
    "list_supported_operations",
)

_QUERY_ALIASES = {
    "list-constructs": "list-capabilities",
    "list-capabilities": "list-capabilities",
    "inspect-construct": "inspect-capability",
    "inspect-capability": "inspect-capability",
    "get-parameter": "describe-parameter",
    "parameter": "describe-parameter",
    "editable-parameters": "list-editable-parameters",
    "list-editable-parameters": "list-editable-parameters",
    **{name.replace("_", "-"): name.replace("_", "-") for name in CANONICAL_QUERIES},
}


def canonical_query_name(query: str) -> str:
    """Return the bounded deterministic query name; never forward free-form prose."""
    normalized = query.strip().casefold().replace("_", "-")
    try:
        return _QUERY_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported canonical model query: {query}") from exc


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
    normalized = canonical_query_name(query)
    registry = load_registry()
    definitions_by_capability = {
        item["id"]: {parameter["name"].casefold(): parameter for parameter in item["parameters"]}
        for item in [*registry["top_level_blocks"], *registry["nested_constructs"]]
    }
    matches: list[dict[str, Any]]
    ambiguous = False

    if normalized == "list-capabilities":
        matches = list(records)
    elif normalized in {"describe-capability", "list-supported-operations"}:
        if normalized == "list-supported-operations":
            matches = capability_manifest(registry)
        else:
            if not capability:
                raise ValueError("describe-capability requires capability")
            resolved = find_capabilities(capability)
            identifiers = {item["id"] for item in resolved}
            matches = [item for item in capability_manifest(registry) if item["id"] in identifiers]
            ambiguous = len(identifiers) > 1
    elif normalized == "inspect-capability":
        if not capability:
            raise ValueError("inspect-capability requires capability")
        resolved = find_capabilities(capability)
        identifiers = {item["id"] for item in resolved}
        matches = [item for item in records if item["capability_id"] in identifiers]
        if occurrence is not None:
            matches = [item for item in matches if item["occurrence"] == occurrence]
        ambiguous = len(identifiers) > 1
    elif normalized == "describe-parameter":
        if not parameter:
            raise ValueError("describe-parameter requires parameter")
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
    elif normalized == "list-editable-parameters":
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
    elif normalized in {
        "list-entities", "list-boundary-conditions", "list-materials",
        "list-constitutives", "list-sets", "inspect-entity", "inspect-cluster",
    }:
        matches = list(entities)
        fixed_kinds: dict[str, set[str]] = {
            "list-boundary-conditions": {"boundary-condition"},
            "list-materials": {"material", "structured-material", "material-parameter"},
            "list-constitutives": {"constitutive"},
            "list-sets": {"node-set", "element-set"},
            "inspect-cluster": {"cluster"},
        }
        if normalized in fixed_kinds:
            matches = [item for item in matches if item.get("kind") in fixed_kinds[normalized]]
        if entity_kind:
            matches = [
                item for item in matches
                if str(item.get("kind", "")).casefold() == entity_kind.casefold()
            ]
        if entity_name:
            if normalized == "list-boundary-conditions":
                cluster_prefix = f"cluster:{entity_name.casefold()}/"
                source_ids = {
                    str(reference.get("source_entity_id"))
                    for reference in references
                    if str(reference.get("target_key", "")).casefold().startswith(cluster_prefix)
                }
                matches = [item for item in matches if item.get("id") in source_ids]
            else:
                matches = [
                    item for item in matches
                    if str(item.get("name", "")).casefold() == entity_name.casefold()
                ]
        if normalized in {"inspect-entity", "inspect-cluster"}:
            if not entity_id and not entity_name:
                raise ValueError(f"{normalized} requires entity_id or entity_name")
            if entity_id:
                matches = [item for item in matches if item.get("id") == entity_id]
            ambiguous = len(matches) > 1
        if normalized == "list-boundary-conditions":
            outgoing = {
                str(item.get("id")): [
                    reference for reference in references
                    if reference.get("source_entity_id") == item.get("id")
                ]
                for item in matches
            }
            matches = [{**item, "references_from": outgoing[str(item.get("id"))]} for item in matches]
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
    else:  # canonical_query_name makes this unreachable and keeps prose out of this layer
        raise ValueError(f"unsupported canonical model query: {query}")

    return {
        "source_set_sha256": source_set.sha256,
        "query": normalized,
        "matches": matches,
        "summary": {"matches": len(matches), "ambiguous": ambiguous},
    }
