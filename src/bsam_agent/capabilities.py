"""Machine-consumable operational views of the curated capability registry."""

from __future__ import annotations

from typing import Any, Iterable

from .registry import load_registry


OPERATION_NAMES = (
    "parse",
    "semantic",
    "inspect",
    "modify",
    "create",
    "delete",
    "rename",
    "reorder",
    "generate",
    "static_validation",
    "execute",
)
OPERATION_STATUSES = frozenset({"unassessed", "unsupported", "implemented", "verified"})

INTENT_OPERATIONS = {
    "inspect": "inspect",
    "query": "semantic",
    "create": "create",
    "modify": "modify",
    "delete": "delete",
    "rename": "rename",
    "reorder": "reorder",
    "validate": "static_validation",
    "run": "execute",
}


def operational_support(record: dict[str, Any]) -> dict[str, str]:
    """Return a complete support map; absence is explicit, never inferred from grammar coverage."""
    declared = record.get("operations", {})
    return {name: str(declared.get(name, "unassessed")) for name in OPERATION_NAMES}


def intent_support(record: dict[str, Any]) -> dict[str, str]:
    """Translate parser/editor operation maturity into user-facing intent maturity."""
    operations = operational_support(record)
    return {
        intent: operations[operation]
        for intent, operation in INTENT_OPERATIONS.items()
    }


def dependency_class(
    reference_kind: str, registry: dict[str, Any] | None = None,
) -> str:
    """Return the single registry class for an emitted semantic-reference kind."""
    registry = registry or load_registry()
    matches = [
        str(item["id"])
        for item in registry["dependency_contract"]["classes"]
        if reference_kind in item["reference_kinds"]
    ]
    if len(matches) != 1:
        raise ValueError(
            f"semantic reference kind {reference_kind!r} must have one dependency class"
        )
    return matches[0]


def capability_manifest(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build the compact contract consumed by API queries and agent routing."""
    registry = registry or load_registry()
    parents = {
        item["id"]: item["canonical"] for item in registry["top_level_blocks"]
    }
    result: list[dict[str, Any]] = []
    groups = (
        ("top-level-block", registry["top_level_blocks"]),
        ("cluster-command", registry["cluster_commands"]),
        ("nested-construct", registry["nested_constructs"]),
    )
    for kind, records in groups:
        for record in records:
            item = {
                "id": record["id"],
                "kind": kind,
                "canonical": record["canonical"],
                "specification_maturity": record["coverage"],
                "operations": operational_support(record),
                "intents": intent_support(record),
            }
            parent = parents.get(record.get("parent_block_id"))
            if parent:
                item["parent"] = parent
            if record.get("entity_kind"):
                item["entity_kind"] = str(record["entity_kind"])
            if record.get("routing_terms"):
                item["routing_terms"] = list(record["routing_terms"])
            parameter_edits = [
                {
                    "name": str(parameter["name"]),
                    "cardinality": str(parameter.get("cardinality", "single")),
                    "operations": dict(parameter["edit_operations"]),
                }
                for parameter in record.get("parameters", [])
                if isinstance(parameter, dict) and parameter.get("edit_operations")
            ]
            if parameter_edits:
                item["parameter_edits"] = parameter_edits
            result.append(item)
    return result


def find_capabilities(
    identifier: str, records: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Resolve an ID or canonical spelling without guessing across multiple matches."""
    needle = identifier.strip().casefold().lstrip("*")
    candidates = records if records is not None else capability_manifest()
    return [
        item for item in candidates
        if str(item["id"]).casefold() == identifier.strip().casefold()
        or str(item["canonical"]).casefold().lstrip("*") == needle
    ]


def nested_constructs(parent_block_id: str = "block.boundary") -> list[dict[str, Any]]:
    return [
        item for item in load_registry()["nested_constructs"]
        if item["parent_block_id"] == parent_block_id
    ]


def match_nested_construct(
    command_text: str, constructs: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    stripped = command_text.lstrip().casefold()
    matches = [
        item for item in constructs if stripped.startswith(str(item["match_prefix"]).casefold())
    ]
    return matches[0] if len(matches) == 1 else None


def canonical_parameter(record: dict[str, Any], spelling: str) -> dict[str, Any] | None:
    """Resolve exact names or the documented four-character BOUNDARY dispatch spelling."""
    needle = spelling.strip().casefold()
    parameters = [item for item in record.get("parameters", []) if isinstance(item, dict)]
    exact = [item for item in parameters if str(item.get("name", "")).casefold() == needle]
    if len(exact) == 1:
        return exact[0]
    if len(needle) < 4:
        return None
    prefix = needle[:4]
    matches = [
        item for item in parameters
        if str(item.get("name", "")).casefold()[:4] == prefix
    ]
    return matches[0] if len(matches) == 1 else None
