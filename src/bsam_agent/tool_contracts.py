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


TOOL_CONTRACTS: dict[str, ToolContract] = {
    "get_capabilities": ToolContract({}, ("api_version", "registry_version", "bsam", "tools")),
    "inspect_model": ToolContract({"source": S}, ("source_set_sha256", "semantic_model", "summary")),
    "validate_model": ToolContract({"source": S}, ("source_set_sha256", "diagnostics", "summary")),
    "import_mesh": ToolContract({"source": S}, ("format", "provenance", "summary")),
    "preview_parameter_change": ToolContract({
        "source": S, "block": S, "construct": S, "parameter": S, "value": S,
        "plan_path": S, "occurrence": Field("integer", required=False),
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
