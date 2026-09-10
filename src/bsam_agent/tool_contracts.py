"""Canonical request contracts for the local deterministic tool surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Field:
    kind: str
    required: bool = True
    items: str | None = None
    nullable: bool = False

    def schema(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": [self.kind, "null"] if self.nullable else self.kind}
        if self.items:
            result["items"] = {"type": self.items}
        return result


@dataclass(frozen=True)
class ToolContract:
    fields: dict[str, Field]
    response_required: tuple[str, ...]

    def request_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(name for name, field in self.fields.items() if field.required),
            "properties": {name: field.schema() for name, field in self.fields.items()},
        }

    def response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": list(self.response_required),
            "properties": {name: {} for name in self.response_required},
            "additionalProperties": True,
        }


S = Field("string")
I = Field("integer")
B = Field("boolean")
N = Field("number")
AI = Field("array", items="integer")
AS = Field("array", items="string")
O = Field("object")


TOOL_CONTRACTS: dict[str, ToolContract] = {
    "get_capabilities": ToolContract({}, ("api_version", "registry_version", "bsam", "tools")),
    "inspect_model": ToolContract({"source": S}, ("source_set_sha256", "semantic_model", "summary")),
    "query_model": ToolContract({
        "source": S,
        "query": S,
        "capability": Field("string", required=False),
        "parameter": Field("string", required=False),
        "entity_id": Field("string", required=False),
        "entity_kind": Field("string", required=False),
        "entity_name": Field("string", required=False),
        "occurrence": Field("integer", required=False),
    }, ("source_set_sha256", "query", "matches", "summary")),
    "validate_model": ToolContract({"source": S}, ("source_set_sha256", "diagnostics", "summary")),
    "import_mesh": ToolContract({"source": S}, ("format", "provenance", "summary")),
    "preview_parameter_change": ToolContract({
        "source": S, "block": S, "construct": S, "parameter": S, "value": S,
        "plan_path": S, "occurrence": Field("integer", required=False),
        "parameter_occurrence": Field("integer", required=False),
        "insert_repeated": Field("boolean", required=False),
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_parameter_removal": ToolContract({
        "source": S, "block": S, "construct": S, "parameter": S,
        "plan_path": S, "occurrence": Field("integer", required=False),
        "parameter_occurrence": Field("integer", required=False),
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_compose_changes": ToolContract({
        "source": S, "plan_paths": AS, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_add_node": ToolContract({
        "source": S, "cluster": S, "label": I, "x": S, "y": S, "z": S, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_add_element": ToolContract({
        "source": S, "cluster": S, "label": I, "element_type": S, "node_labels": AI,
        "plan_path": S, "elset": Field("string", required=False, nullable=True),
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_delete_node": ToolContract({
        "source": S, "cluster": S, "label": I, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_create_set": ToolContract({
        "source": S, "cluster": S, "member_kind": S, "name": S, "members": AI, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_add_set_members": ToolContract({
        "source": S, "cluster": S, "member_kind": S, "name": S, "members": AI, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_import_mesh": ToolContract({
        "template": S, "mesh": S, "cluster": S, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_expand_notch_plies": ToolContract({
        "source": S, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_migrate_legacy_solver": ToolContract({
        "source": S, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_rename_boundary_condition": ToolContract({
        "source": S, "old_name": S, "new_name": S, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_rename_entity": ToolContract({
        "source": S, "capability": S, "entity_name": S, "new_name": S, "plan_path": S,
        "context": Field("object", required=False),
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_create_entity": ToolContract({
        "source": S, "capability": S, "attributes": O, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_modify_entity": ToolContract({
        "source": S, "capability": S, "entity_name": S, "changes": O, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_delete_entity": ToolContract({
        "source": S, "capability": S, "entity_name": S, "context": O, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "preview_refresh_change": ToolContract({
        "source": S, "stale_plan_path": S, "plan_path": S,
    }, ("plan_id", "plan_digest", "source_diff", "validation")),
    "review_change": ToolContract({"plan_path": S}, ("plan_id", "plan_digest", "source_diff", "validation")),
    "apply_change": ToolContract({
        "plan_path": S, "destination": S, "confirm": B,
        "audit_path": Field("string", required=False),
    }, ("plan_id", "destination", "output_sha256", "validation", "audit")),
    "run_bsam": ToolContract({
        "source": S, "output_dir": S, "executable": S, "confirm": B,
        "timeout": Field("number", required=False), "stop_grace": Field("number", required=False),
    }, ("classification", "output_directory", "source_set_sha256")),
    "get_run_status": ToolContract({"output_dir": S}, ("classification", "output_directory", "state")),
    "stop_run": ToolContract({"output_dir": S, "confirm": B}, ("output_directory",)),
}


TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_capabilities": "List supported BSAM capabilities and tool contracts before handling an unknown feature.",
    "inspect_model": "Inspect an existing BSAM deck and return its structure, semantic entities, diagnostics, and summary.",
    "query_model": "Run a focused semantic query for registered constructs, parameters, entities, or references.",
    "validate_model": "Validate an existing BSAM deck without changing or running it.",
    "import_mesh": "Inspect and validate a manually prepared Abaqus-style .ele mesh without modifying a deck.",
    "preview_parameter_change": "Create a review plan to replace or insert one registered parameter value, with explicit occurrence selection for repeated-last-wins values.",
    "preview_parameter_removal": "Create a review plan to remove one isolated optional parameter value, with explicit occurrence selection for repeated-last-wins values.",
    "preview_compose_changes": "Compose 2 to 8 independent same-revision typed plans into one validated review and confirmation boundary.",
    "preview_add_node": "Create a review plan to add one finite-element node.",
    "preview_add_element": "Create a review plan to add one finite element with existing node labels.",
    "preview_delete_node": "Create a review plan to delete one unreferenced node.",
    "preview_create_set": "Create a review plan for a new node or element set.",
    "preview_add_set_members": "Create a review plan to add members to an existing node or element set.",
    "preview_import_mesh": "Create a review plan to place a validated .ele mesh into an empty template cluster.",
    "preview_expand_notch_plies": "Create the approved notch_v1 review plan that expands two plies to eight plies.",
    "preview_migrate_legacy_solver": "Create a review plan that migrates a legacy type-9 solver body to current PARDISO syntax.",
    "preview_rename_boundary_condition": "Create a review plan that renames a boundary condition and updates its loading references.",
    "preview_rename_entity": "Create a dependency-aware rename plan through a verified capability; scoped entities require explicit context.",
    "preview_create_entity": "Create a structural entity through a capability whose create operation is verified; attributes are capability-specific.",
    "preview_modify_entity": "Modify a structural entity through a capability whose modify operation is verified; changes are capability-specific.",
    "preview_delete_entity": "Delete a structural entity through a capability whose delete operation is verified and dependency checks permit it.",
    "preview_refresh_change": "Re-preview a digest-valid stale plan against the changed source by replaying its typed selector and requested values.",
    "review_change": "Recheck an existing revision-bound change plan and return its exact source and semantic diff.",
    "apply_change": "Apply one reviewed change plan to a new deck; confirm must be true or policy refuses execution.",
    "run_bsam": "Run one validated deck in an isolated output directory; confirm must be true or policy refuses execution.",
    "get_run_status": "Read the status of one existing isolated BSAM run.",
    "stop_run": "Request a controlled stop for one existing run; confirm must be true or policy refuses execution.",
}


def contract_manifest() -> dict[str, Any]:
    return {
        name: {
            "request_schema": contract.request_schema(),
            "response_schema": contract.response_schema(),
        }
        for name, contract in TOOL_CONTRACTS.items()
    }


def validate_arguments(tool: str, value: Any) -> dict[str, Any]:
    contract = TOOL_CONTRACTS[tool]
    if not isinstance(value, dict):
        raise ValueError("tool arguments must be a JSON object")
    missing = sorted(
        name for name, field in contract.fields.items() if field.required and name not in value
    )
    extra = sorted(value.keys() - contract.fields.keys())
    if missing:
        raise ValueError(f"missing arguments: {', '.join(missing)}")
    if extra:
        raise ValueError(f"unknown arguments: {', '.join(extra)}")
    kinds = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    for name, item in value.items():
        field = contract.fields[name]
        if item is None and field.nullable:
            continue
        if not kinds[field.kind](item):
            raise ValueError(f"argument {name} must have type {field.kind}")
        if field.items and any(not kinds[field.items](member) for member in item):
            raise ValueError(f"argument {name} items must have type {field.items}")
    return value


def validate_response(tool: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"tool {tool} returned a non-object response")
    missing = sorted(set(TOOL_CONTRACTS[tool].response_required) - value.keys())
    if missing:
        raise ValueError(f"tool {tool} response is missing: {', '.join(missing)}")
    return value
