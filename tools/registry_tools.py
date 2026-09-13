"""Validate the BSAM capability registry and generate its Markdown reference.

This tool intentionally uses only the Python standard library. It never reads or
copies BSAM source; evidence locators in the curated registry are metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "specs" / "bsam-2.4" / "capabilities.json"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "bsam" / "reference" / "BSAM_2_4_INPUT_API.md"
VALID_COVERAGE = {
    "identified",
    "partially-documented",
    "documented",
    "runtime-verified",
}
VALID_OPERATIONS = {
    "parse", "semantic", "inspect", "modify", "create", "delete", "rename",
    "reorder", "generate", "static_validation", "execute",
}
VALID_OPERATION_STATUS = {"unassessed", "unsupported", "implemented", "verified"}


class RegistryError(ValueError):
    """Raised when curated registry invariants are violated."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_registry(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream, object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(data, dict):
        raise RegistryError("registry root must be an object")
    return data


def _require_keys(value: dict[str, Any], keys: set[str], context: str) -> None:
    missing = sorted(keys - set(value))
    if missing:
        raise RegistryError(f"{context} missing keys: {', '.join(missing)}")


def _unique(values: list[str], context: str) -> None:
    duplicates = sorted(item for item, count in Counter(values).items() if count > 1)
    if duplicates:
        raise RegistryError(f"duplicate {context}: {', '.join(duplicates)}")


def validate_registry(data: dict[str, Any]) -> dict[str, int]:
    _require_keys(
        data,
        {
            "schema_version",
            "registry_version",
            "target",
            "policy",
            "evidence",
            "top_level_blocks",
            "cluster_commands",
            "nested_constructs",
            "generation_profiles",
            "transformations",
            "obsolete_tokens",
            "execution_contract",
            "dependency_contract",
            "entity_contract",
            "consumer_contract",
            "repository_check_contract",
            "change_contract",
        },
        "registry",
    )
    if data["schema_version"] != "2.2.0":
        raise RegistryError("unsupported schema_version")

    dependency = data["dependency_contract"]
    _require_keys(
        dependency,
        {
            "schema_version", "classes", "reference_contracts", "decision_sources",
            "clarification_triggers",
        },
        "dependency_contract",
    )
    if dependency["schema_version"] != "1.2.0":
        raise RegistryError("unsupported dependency_contract schema_version")
    dependency_classes = dependency["classes"]
    for item in dependency_classes:
        _require_keys(
            item,
            {"id", "representation", "summary", "reference_kinds", "change_policy"},
            "dependency class",
        )
    _unique([item["id"] for item in dependency_classes], "dependency class")
    if {item["id"] for item in dependency_classes} != {
        "structural-reference", "bsam-semantic-constraint", "engineering-decision",
    }:
        raise RegistryError("dependency_contract must define the three dependency classes")
    reference_kinds = [
        kind for item in dependency_classes for kind in item["reference_kinds"]
    ]
    _unique(reference_kinds, "classified semantic reference kind")
    engineering = next(
        item for item in dependency_classes if item["id"] == "engineering-decision"
    )
    if engineering["reference_kinds"]:
        raise RegistryError("engineering decisions cannot be semantic references")
    if any(
        not item["reference_kinds"]
        for item in dependency_classes if item["id"] != "engineering-decision"
    ):
        raise RegistryError("semantic dependency classes require reference kinds")
    decision_sources = dependency["decision_sources"]
    for item in decision_sources:
        _require_keys(
            item, {"id", "requires_user_input", "summary"},
            "engineering decision source",
        )
    _unique([item["id"] for item in decision_sources], "engineering decision source")
    source_policy = {
        item["id"]: item["requires_user_input"] for item in decision_sources
    }
    if source_policy != {"user-approved": True, "source-derived": False}:
        raise RegistryError("dependency_contract has invalid engineering decision sources")

    target = data["target"]
    _require_keys(
        target,
        {
            "product",
            "product_version",
            "source_commit",
            "executable_sha256",
            "platform",
            "execution_mode",
        },
        "target",
    )
    if len(target["source_commit"]) != 40:
        raise RegistryError("target.source_commit must contain 40 hexadecimal characters")
    if len(target["executable_sha256"]) != 64:
        raise RegistryError("target.executable_sha256 must contain 64 hexadecimal characters")
    for field in ("source_commit", "executable_sha256"):
        try:
            int(target[field], 16)
        except ValueError as exc:
            raise RegistryError(f"target.{field} is not hexadecimal") from exc

    evidence = data["evidence"]
    evidence_ids = [item["id"] for item in evidence]
    _unique(evidence_ids, "evidence id")
    evidence_by_id = {item["id"]: item for item in evidence}
    for item in evidence:
        _require_keys(item, {"id", "kind", "locator", "claim"}, item["id"])
        locator = item["locator"]
        if item["kind"] == "source":
            source_roots = ("source/", "sheff_modules/first_party/")
            if not locator.startswith(source_roots):
                raise RegistryError(
                    f"{item['id']} source locator must identify BSAM source or a pinned first-party submodule"
                )
            if ".." in Path(locator).parts or Path(locator).is_absolute():
                raise RegistryError(f"{item['id']} source locator must be relative and contained")
        if "line_end" in item and "line_start" not in item:
            raise RegistryError(f"{item['id']} has line_end without line_start")
        if item.get("line_end", item.get("line_start", 1)) < item.get("line_start", 1):
            raise RegistryError(f"{item['id']} has an inverted line range")

    blocks = data["top_level_blocks"]
    block_ids = [item["id"] for item in blocks]
    _unique(block_ids, "block id")
    _unique([item["canonical"].upper() for item in blocks], "canonical block token")

    commands = data["cluster_commands"]
    command_ids = [item["id"] for item in commands]
    _unique(command_ids, "command id")
    _unique([item["canonical"].upper() for item in commands], "canonical command token")
    _unique([item["dispatch_prefix"].upper() for item in commands], "command dispatch prefix")

    constructs = data["nested_constructs"]
    construct_ids = [item["id"] for item in constructs]
    _unique(construct_ids, "nested construct id")
    _unique(
        [f"{item['parent_block_id']}:{item['match_prefix'].lower()}" for item in constructs],
        "nested construct match prefix",
    )

    records = [("block", item) for item in blocks] + [
        ("command", item) for item in commands
    ] + [("construct", item) for item in constructs]
    for kind, item in records:
        _require_keys(
            item,
            {
                "id",
                "canonical",
                "summary",
                "coverage",
                "parameters",
                "evidence_ids",
                "remaining_work",
            },
            item["id"],
        )
        if kind == "block":
            _require_keys(
                item,
                {"lookup_token", "match_rule", "required", "parser", "termination"},
                item["id"],
            )
        elif kind == "command":
            _require_keys(item, {"parent_block_id", "dispatch_prefix"}, item["id"])
        else:
            _require_keys(
                item,
                {"parent_block_id", "match_prefix", "kind"},
                item["id"],
            )
        if item["coverage"] not in VALID_COVERAGE:
            raise RegistryError(f"{item['id']} has invalid coverage {item['coverage']}")
        operations = item.get("operations", {})
        unknown_operations = sorted(set(operations) - VALID_OPERATIONS)
        if unknown_operations:
            raise RegistryError(
                f"{item['id']} has unknown operations: {', '.join(unknown_operations)}"
            )
        invalid_statuses = sorted({
            str(status) for status in operations.values()
            if status not in VALID_OPERATION_STATUS
        })
        if invalid_statuses:
            raise RegistryError(
                f"{item['id']} has invalid operation status: {', '.join(invalid_statuses)}"
            )
        if not item["summary"].strip():
            raise RegistryError(f"{item['id']} has an empty summary")
        missing_evidence = sorted(set(item["evidence_ids"]) - set(evidence_by_id))
        if missing_evidence:
            raise RegistryError(
                f"{item['id']} references missing evidence: {', '.join(missing_evidence)}"
            )
        parameter_names = [parameter["name"].lower() for parameter in item["parameters"]]
        _unique(parameter_names, f"parameter in {item['id']}")
        for parameter in item["parameters"]:
            _require_keys(
                parameter,
                {"name", "value_type", "required", "summary"},
                f"parameter in {item['id']}",
            )
            cardinality = parameter.get("cardinality", "single")
            if cardinality not in {"single", "repeated-last-wins"}:
                raise RegistryError(
                    f"parameter {parameter['name']} in {item['id']} has invalid cardinality"
                )
        if kind in {"command", "construct"} and item["parent_block_id"] not in block_ids:
            raise RegistryError(f"{item['id']} references missing parent block")
        body = item.get("body")
        if body:
            _require_keys(
                body,
                {"style", "termination", "variants", "dependencies"},
                f"body in {item['id']}",
            )
            variant_names = [variant["name"].lower() for variant in body["variants"]]
            _unique(variant_names, f"body variant in {item['id']}")
            for variant in body["variants"]:
                _require_keys(
                    variant,
                    {"name", "when", "rows", "constraints"},
                    f"body variant in {item['id']}",
                )
                row_names = [row["name"].lower() for row in variant["rows"]]
                _unique(row_names, f"body row in {item['id']}/{variant['name']}")
                for row in variant["rows"]:
                    _require_keys(
                        row,
                        {"name", "repetition", "fields"},
                        f"body row in {item['id']}/{variant['name']}",
                    )
                    field_names = [field["name"].lower() for field in row["fields"]]
                    _unique(field_names, f"body field in {item['id']}/{variant['name']}/{row['name']}")
                    for field in row["fields"]:
                        _require_keys(
                            field,
                            {"name", "value_type", "required", "summary"},
                            f"body field in {item['id']}/{variant['name']}/{row['name']}",
                        )

    capability_ids = set(block_ids) | set(command_ids) | {
        item["id"] for item in constructs
    }
    consumer_contract = data["consumer_contract"]
    _require_keys(
        consumer_contract,
        {"schema_version", "read_routes", "mutation_routes"},
        "consumer_contract",
    )
    if consumer_contract["schema_version"] != "1.0.0":
        raise RegistryError("unsupported consumer_contract schema_version")
    read_operations: list[str] = []
    for item in consumer_contract["read_routes"]:
        _require_keys(
            item, {"operations", "scope", "consumers", "policy"},
            "consumer read route",
        )
        if item["scope"] != "all-active-capabilities":
            raise RegistryError("consumer read routes must cover all active capabilities")
        read_operations.extend(item["operations"])
    _unique(read_operations, "consumer read operation")
    required_read_operations = {"parse", "semantic", "inspect", "static_validation"}
    if set(read_operations) != required_read_operations:
        raise RegistryError("consumer read routes must exactly cover required read operations")
    if any(
        item.get("operations", {}).get(operation) not in {"implemented", "verified"}
        for _, item in records for operation in required_read_operations
    ):
        raise RegistryError("consumer read routes require supported operations on every capability")

    known_mutation_tools = {
        "preview_parameter_change", "preview_parameter_removal",
        "preview_modify_entity", "preview_create_entity",
        "preview_delete_entity", "preview_rename_entity",
    }
    mutation_pairs: list[str] = []
    for item in consumer_contract["mutation_routes"]:
        _require_keys(
            item,
            {"operation", "capability_ids", "tools", "adapter_kind", "policy"},
            "consumer mutation route",
        )
        missing_capabilities = sorted(set(item["capability_ids"]) - capability_ids)
        if missing_capabilities:
            raise RegistryError(
                "consumer mutation route references missing capabilities: "
                + ", ".join(missing_capabilities)
            )
        unknown_tools = sorted(set(item["tools"]) - known_mutation_tools)
        if unknown_tools:
            raise RegistryError(
                "consumer mutation route references unknown tools: "
                + ", ".join(unknown_tools)
            )
        mutation_pairs.extend(
            f"{item['operation']}:{capability_id}"
            for capability_id in item["capability_ids"]
        )
    _unique(mutation_pairs, "consumer mutation route")
    expected_mutation_pairs = {
        f"{operation}:{item['id']}"
        for _, item in records
        for operation in ("modify", "create", "delete", "rename")
        if item.get("operations", {}).get(operation) in {"implemented", "verified"}
    }
    if set(mutation_pairs) != expected_mutation_pairs:
        raise RegistryError(
            "consumer mutation routes must exactly cover supported capability operations"
        )
    repository_check = data["repository_check_contract"]
    _require_keys(
        repository_check,
        {
            "schema_version", "repository_command", "test_command", "ci_workflow",
            "required_checks", "optional_checks", "generated_artifacts", "ledger_policy",
        },
        "repository_check_contract",
    )
    if repository_check["schema_version"] != "1.0.0":
        raise RegistryError("unsupported repository_check_contract schema_version")
    if repository_check["repository_command"] != "python tools/repository_checks.py":
        raise RegistryError("repository check command must use the checked-in aggregator")
    if repository_check["test_command"] != "python -m pytest -q":
        raise RegistryError("repository test command must run the complete suite")
    expected_checks = {
        "registry-invariants", "schema-version-binding", "generated-reference",
        "committed-dispatch-coverage", "ci-command-binding",
    }
    _unique(repository_check["required_checks"], "required repository check")
    if set(repository_check["required_checks"]) != expected_checks:
        raise RegistryError("repository checks must exactly cover generated-contract drift")
    optional_check_ids: list[str] = []
    for item in repository_check["optional_checks"]:
        _require_keys(item, {"id", "condition", "command"}, "optional repository check")
        optional_check_ids.append(item["id"])
    _unique(optional_check_ids, "optional repository check")
    if optional_check_ids != ["live-source-dispatch"]:
        raise RegistryError("live source dispatch must be the sole optional repository check")
    generated_paths: list[str] = []
    for item in repository_check["generated_artifacts"]:
        _require_keys(
            item, {"path", "producer", "repository_check"},
            "generated artifact",
        )
        path = (REPO_ROOT / item["path"]).resolve()
        if not path.is_relative_to(REPO_ROOT) or Path(item["path"]).is_absolute():
            raise RegistryError("generated artifact path must be repository-relative and contained")
        generated_paths.append(item["path"])
    _unique(generated_paths, "generated artifact path")
    if set(generated_paths) != {
        "docs/bsam/reference/BSAM_2_4_INPUT_API.md",
        "docs/bsam/DISPATCH_AUDIT.md",
    }:
        raise RegistryError("repository checks must cover every generated specification artifact")
    entity_contract = data["entity_contract"]
    _require_keys(
        entity_contract,
        {
            "schema_version", "capability_record_policy", "primary_entity_field",
            "no_primary_entity_capabilities", "additional_entity_outputs",
        },
        "entity_contract",
    )
    if entity_contract["schema_version"] != "1.0.0":
        raise RegistryError("unsupported entity_contract schema_version")
    if entity_contract["primary_entity_field"] != "entity_kind":
        raise RegistryError("entity_contract primary field must be entity_kind")
    no_primary = entity_contract["no_primary_entity_capabilities"]
    _unique(no_primary, "capability without a primary entity")
    actual_no_primary = {
        item["id"] for _, item in records if not item.get("entity_kind")
    }
    if set(no_primary) != actual_no_primary:
        raise RegistryError(
            "entity_contract no-primary list must exactly cover capabilities without entity_kind"
        )
    additional_outputs = entity_contract["additional_entity_outputs"]
    output_keys: list[str] = []
    for item in additional_outputs:
        _require_keys(
            item, {"capability_ids", "entity_kind", "cardinality", "condition"},
            "additional entity output",
        )
        missing_capabilities = sorted(set(item["capability_ids"]) - capability_ids)
        if missing_capabilities:
            raise RegistryError(
                "additional entity output references missing capabilities: "
                + ", ".join(missing_capabilities)
            )
        output_keys.extend(
            f"{capability_id}:{item['entity_kind']}"
            for capability_id in item["capability_ids"]
        )
    _unique(output_keys, "additional entity output")
    declared_entity_kinds = {
        str(item["entity_kind"]) for _, item in records if item.get("entity_kind")
    } | {str(item["entity_kind"]) for item in additional_outputs}
    reference_contracts = dependency["reference_contracts"]
    contracted_reference_kinds: list[str] = []
    classification_by_kind = {
        kind: str(item["id"])
        for item in dependency_classes
        for kind in item["reference_kinds"]
    }
    for item in reference_contracts:
        _require_keys(
            item,
            {
                "kinds", "classification", "source_entity_kinds",
                "target_entity_kinds", "forward_policy", "reverse_policy",
            },
            "reference contract",
        )
        contracted_reference_kinds.extend(item["kinds"])
        if any(
            classification_by_kind.get(kind) != item["classification"]
            for kind in item["kinds"]
        ):
            raise RegistryError("reference contract classification disagrees with dependency class")
        unknown_entities = sorted(
            (set(item["source_entity_kinds"]) | set(item["target_entity_kinds"]))
            - declared_entity_kinds
        )
        if unknown_entities:
            raise RegistryError(
                "reference contract uses undeclared entity kinds: "
                + ", ".join(unknown_entities)
            )
    _unique(contracted_reference_kinds, "reference contract kind")
    if set(contracted_reference_kinds) != set(reference_kinds):
        raise RegistryError("reference contracts must exactly cover classified reference kinds")
    generation_profiles = data["generation_profiles"]
    _unique([item["id"] for item in generation_profiles], "generation profile id")
    _unique(
        [f"{item['id']}@{item['profile_version']}" for item in generation_profiles],
        "generation profile version",
    )
    for item in generation_profiles:
        _require_keys(
            item,
            {
                "id", "profile_version", "status", "summary", "tool", "analysis",
                "mesh_format", "required_choices", "capabilities", "constraints",
                "evidence_ids",
            },
            item["id"],
        )
        if item["status"] not in {"implemented", "verified"}:
            raise RegistryError(f"{item['id']} has invalid generation status {item['status']}")
        _unique(item["required_choices"], f"required choice in {item['id']}")
        _unique(item["capabilities"], f"capability in {item['id']}")
        missing_capabilities = sorted(set(item["capabilities"]) - capability_ids)
        if missing_capabilities:
            raise RegistryError(
                f"{item['id']} references missing capabilities: {', '.join(missing_capabilities)}"
            )
        missing_evidence = sorted(set(item["evidence_ids"]) - set(evidence_by_id))
        if missing_evidence:
            raise RegistryError(
                f"{item['id']} references missing evidence: {', '.join(missing_evidence)}"
            )

    transformations = data["transformations"]
    _unique([item["id"] for item in transformations], "transformation id")
    _unique(
        [f"{item['id']}@{item['algorithm_version']}" for item in transformations],
        "transformation version",
    )
    for item in transformations:
        _require_keys(
            item,
            {
                "id", "algorithm_version", "summary", "coverage", "tool", "operation",
                "applicability", "parameters", "decisions", "impacts", "dependencies",
                "evidence_ids",
            },
            item["id"],
        )
        if item["coverage"] not in VALID_COVERAGE:
            raise RegistryError(f"{item['id']} has invalid coverage {item['coverage']}")
        _unique([rule["path"] for rule in item["applicability"]], f"applicability path in {item['id']}")
        for rule in item["applicability"]:
            _require_keys(rule, {"path", "operator", "value", "failure"}, f"rule in {item['id']}")
        _unique([parameter["name"].lower() for parameter in item["parameters"]], f"parameter in {item['id']}")
        for parameter in item["parameters"]:
            _require_keys(
                parameter,
                {"name", "value_type", "required", "summary"},
                f"parameter in {item['id']}",
            )
        _unique([decision["name"].lower() for decision in item["decisions"]], f"decision in {item['id']}")
        for decision in item["decisions"]:
            _require_keys(decision, {"name", "value", "source"}, f"decision in {item['id']}")
        missing_evidence = sorted(set(item["evidence_ids"]) - set(evidence_by_id))
        if missing_evidence:
            raise RegistryError(
                f"{item['id']} references missing evidence: {', '.join(missing_evidence)}"
            )

    change_contract = data["change_contract"]
    _require_keys(
        change_contract,
        {
            "schema_version", "operation_impacts", "transformation_ids",
            "transformation_policy",
        },
        "change_contract",
    )
    if change_contract["schema_version"] != "1.0.0":
        raise RegistryError("unsupported change_contract schema_version")
    impact_pairs: list[str] = []
    for item in change_contract["operation_impacts"]:
        _require_keys(
            item,
            {
                "operation", "capability_ids", "adapter", "direct_impacts",
                "dependent_checks",
            },
            "operation impact",
        )
        missing_capabilities = sorted(set(item["capability_ids"]) - capability_ids)
        if missing_capabilities:
            raise RegistryError(
                "operation impact references missing capabilities: "
                + ", ".join(missing_capabilities)
            )
        impact_pairs.extend(
            f"{item['operation']}:{capability_id}"
            for capability_id in item["capability_ids"]
        )
    _unique(impact_pairs, "operation impact")
    expected_impact_pairs = {
        f"{operation}:{item['id']}"
        for _, item in records
        for operation in ("create", "delete", "rename")
        if item.get("operations", {}).get(operation) in {"implemented", "verified"}
    }
    if set(impact_pairs) != expected_impact_pairs:
        raise RegistryError(
            "change_contract operation impacts must exactly cover supported changes"
        )
    transformation_ids = change_contract["transformation_ids"]
    _unique(transformation_ids, "change-contract transformation")
    if set(transformation_ids) != {item["id"] for item in transformations}:
        raise RegistryError("change_contract must reference every registered transformation")

    clarification_triggers = dependency["clarification_triggers"]
    for item in clarification_triggers:
        _require_keys(
            item,
            {
                "id", "scope_ids", "operations", "condition", "required_choices",
                "decision_source",
            },
            "clarification trigger",
        )
        _unique(item["scope_ids"], f"scope in {item['id']}")
        _unique(item["operations"], f"operation in {item['id']}")
        _unique(item["required_choices"], f"required choice in {item['id']}")
        if item["decision_source"] != "user-approved":
            raise RegistryError(f"{item['id']} must require user-approved decisions")
    _unique([item["id"] for item in clarification_triggers], "clarification trigger")
    known_scopes = capability_ids | {
        item["id"] for item in generation_profiles
    } | {item["id"] for item in transformations}
    unknown_scopes = sorted({
        scope for item in clarification_triggers for scope in item["scope_ids"]
        if scope not in known_scopes
    })
    if unknown_scopes:
        raise RegistryError(
            "clarification triggers reference missing scopes: "
            + ", ".join(unknown_scopes)
        )
    for profile in generation_profiles:
        profile_triggers = [
            item for item in clarification_triggers
            if profile["id"] in item["scope_ids"] and "generate" in item["operations"]
        ]
        choices = {
            choice for item in profile_triggers for choice in item["required_choices"]
        }
        if choices != set(profile["required_choices"]):
            raise RegistryError(
                f"clarification triggers must exactly cover {profile['id']} required choices"
            )
    for transformation in transformations:
        approved = {
            item["name"] for item in transformation["decisions"]
            if item["source"] == "user-approved"
        }
        triggers = [
            item for item in clarification_triggers
            if transformation["id"] in item["scope_ids"]
            and "transform" in item["operations"]
        ]
        choices = {choice for item in triggers for choice in item["required_choices"]}
        if choices != approved:
            raise RegistryError(
                f"clarification triggers must exactly cover {transformation['id']} user decisions"
            )

    obsolete_tokens = data["obsolete_tokens"]
    _unique([item["token"] for item in obsolete_tokens], "obsolete token")
    for item in obsolete_tokens:
        _require_keys(
            item,
            {"token", "replacement", "context", "behavior", "diagnostic", "evidence_ids"},
            f"obsolete token {item['token']}",
        )
        missing_evidence = sorted(set(item["evidence_ids"]) - set(evidence_by_id))
        if missing_evidence:
            raise RegistryError(
                f"obsolete token {item['token']} references missing evidence: "
                + ", ".join(missing_evidence)
            )

    execution = data["execution_contract"]
    _require_keys(
        execution,
        {
            "invocation",
            "input_extension",
            "success_policy",
            "control_files",
            "evidence_ids",
        },
        "execution_contract",
    )
    missing_execution_evidence = sorted(set(execution["evidence_ids"]) - set(evidence_by_id))
    if missing_execution_evidence:
        raise RegistryError(
            "execution_contract references missing evidence: "
            + ", ".join(missing_execution_evidence)
        )

    return {
        "evidence": len(evidence),
        "blocks": len(blocks),
        "commands": len(commands),
        "constructs": len(constructs),
        "generation_profiles": len(generation_profiles),
        "transformations": len(transformations),
        "dependency_classes": len(dependency_classes),
        "primary_entity_capabilities": len(records) - len(no_primary),
        "additional_entity_outputs": len(output_keys),
        "reference_contracts": len(reference_contracts),
        "read_routes": len(read_operations),
        "mutation_routes": len(mutation_pairs),
        "repository_checks": len(repository_check["required_checks"]),
        "generated_artifacts": len(generated_paths),
        "operation_impacts": len(impact_pairs),
        "clarification_triggers": len(clarification_triggers),
        "obsolete_tokens": len(obsolete_tokens),
        "documented_records": sum(
            item["coverage"] in {"documented", "runtime-verified"}
            for _, item in records
        ),
    }


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _evidence_links(data: dict[str, Any]) -> dict[str, str]:
    return {item["id"]: f"[{item['id']}](#{item['id'].replace('.', '')})" for item in data["evidence"]}


def _render_parameter(parameter: dict[str, Any]) -> str:
    required = "required" if parameter["required"] else "optional"
    details: list[str] = []
    if "allowed_values" in parameter:
        details.append(
            "allowed: " + ", ".join(f"`{value}`" for value in parameter["allowed_values"])
        )
    if "default" in parameter:
        details.append(f"default: `{json.dumps(parameter['default'], ensure_ascii=False)}`")
    if parameter.get("cardinality", "single") != "single":
        details.append(f"cardinality: {parameter['cardinality']}")
    if parameter.get("edit_operations"):
        details.append(
            "edit: " + ", ".join(
                f"{name}={status}"
                for name, status in parameter["edit_operations"].items()
            )
        )
    suffix = f" ({'; '.join(details)})" if details else ""
    return (
        f"- `{parameter['name']}` ({parameter['value_type']}, {required}){suffix}: "
        f"{parameter['summary']}"
    )


def _render_operations(lines: list[str], record: dict[str, Any]) -> None:
    if record.get("operations"):
        lines.append(
            "- Operational support: " + ", ".join(
                f"`{name}`={status}" for name, status in record["operations"].items()
            )
        )


def _render_body(lines: list[str], title: str, body: dict[str, Any]) -> None:
    lines.extend([
        f"#### `{title}` body",
        "",
        f"Termination: {body['termination']}. Dependencies: "
        + ("; ".join(body["dependencies"]) or "none"),
        "",
    ])
    for variant in body["variants"]:
        lines.append(f"- **{variant['name']}** ({variant['when']}):")
        for row in variant["rows"]:
            fields = ", ".join(
                f"`{field['name']}`:{field['value_type']}" for field in row["fields"]
            )
            lines.append(f"  - `{row['name']}` [{row['repetition']}]: {fields}")
        lines.extend(f"  - Constraint: {item}" for item in variant["constraints"])
    lines.append("")


def render_reference(data: dict[str, Any], registry_path: Path) -> str:
    counts = validate_registry(data)
    target = data["target"]
    evidence_links = _evidence_links(data)
    registry_digest = hashlib.sha256(registry_path.read_bytes()).hexdigest().upper()
    lines: list[str] = [
        "# BSAM 2.4 current input API",
        "",
        "> Generated by `python tools/registry_tools.py generate`. Do not edit this file directly.",
        "",
        "## Baseline",
        "",
        f"- Product: {target['product']} {target['product_version']}",
        f"- Source commit: `{target['source_commit']}`",
        f"- Executable SHA-256: `{target['executable_sha256']}`",
        f"- Platform/mode: {target['platform']} {target['execution_mode']}",
        f"- Registry version: `{data['registry_version']}`",
        f"- Registry SHA-256: `{registry_digest}`",
        f"- Current inventory: {counts['blocks']} top-level blocks, {counts['commands']} cluster commands, {counts['constructs']} nested constructs, {counts['generation_profiles']} generation profiles, {counts['transformations']} registered transformations, {counts['dependency_classes']} dependency classes, {counts['reference_contracts']} forward/reverse reference contracts, {counts['read_routes']} read consumer routes, {counts['mutation_routes']} mutation consumer routes, {counts['repository_checks']} repository drift checks, {counts['operation_impacts']} supported change impacts, {counts['clarification_triggers']} engineering-clarification triggers, and {counts['primary_entity_capabilities']} capabilities with primary entity output",
        "",
        "Coverage labels describe specification work, not parser availability. `identified` means an active dispatch path is known but its full data grammar is not yet documented. Operational support is tracked separately; omitted operations are unassessed, not implicitly supported.",
        "",
        "## Top-level blocks",
        "",
        "| Token | Required | Match rule | Parser | Coverage | Purpose |",
        "|---|---:|---|---|---|---|",
    ]
    for block in data["top_level_blocks"]:
        lines.append(
            "| `{}` | {} | {} | `{}` | {} | {} |".format(
                _escape_cell(block["canonical"]),
                "yes" if block["required"] else "no",
                _escape_cell(block["match_rule"]),
                _escape_cell(block["parser"]),
                _escape_cell(block["coverage"]),
                _escape_cell(block["summary"]),
            )
        )

    lines.extend(["", "## Block details", ""])
    for block in data["top_level_blocks"]:
        evidence = ", ".join(evidence_links[item] for item in block["evidence_ids"])
        tokens = ", ".join(f"`{token}`" for token in block["termination"]["tokens"])
        lines.extend(
            [
                f"### `{block['canonical']}`",
                "",
                block["summary"],
                "",
                f"- Registry ID: `{block['id']}`",
                f"- Lookup token/matcher: `{block['lookup_token']}` / {block['match_rule']}",
                f"- Required: {'yes' if block['required'] else 'no'}",
                f"- Termination: {tokens} ({block['termination']['certainty']})",
                f"- Coverage: {block['coverage']}",
                f"- Evidence: {evidence}",
            ]
        )
        _render_operations(lines, block)
        if block["parameters"]:
            lines.extend(["", "Known parameters:", ""])
            for parameter in block["parameters"]:
                lines.append(_render_parameter(parameter))
        if block["remaining_work"]:
            lines.extend(["", "Remaining specification work:", ""])
            lines.extend(f"- {item}" for item in block["remaining_work"])
        lines.append("")
        if block.get("body"):
            _render_body(lines, block["canonical"], block["body"])

    lines.extend(
        [
            "## Finite-element cluster commands",
            "",
            "The parser dispatches on the first five characters (the leading `*` plus four letters). Canonical spellings below are generation targets; parameter completeness varies with the coverage label.",
            "",
            "| Command | Dispatch | Coverage | Known line parameters | Purpose |",
            "|---|---|---|---|---|",
        ]
    )
    for command in data["cluster_commands"]:
        parameters = ", ".join(f"`{item['name']}`" for item in command["parameters"]) or "—"
        lines.append(
            "| `{}` | `{}` | {} | {} | {} |".format(
                _escape_cell(command["canonical"]),
                _escape_cell(command["dispatch_prefix"]),
                _escape_cell(command["coverage"]),
                parameters,
                _escape_cell(command["summary"]),
            )
        )

    lines.extend(["", "## Cluster command details", ""])
    for command in data["cluster_commands"]:
        evidence = ", ".join(evidence_links[item] for item in command["evidence_ids"])
        lines.extend([
            f"### `{command['canonical']}`",
            "",
            command["summary"],
            "",
            f"- Registry ID: `{command['id']}`",
            f"- Dispatch prefix: `{command['dispatch_prefix']}`",
            f"- Coverage: {command['coverage']}",
            f"- Evidence: {evidence}",
        ])
        _render_operations(lines, command)
        if command["parameters"]:
            lines.extend(["", "Known parameters:", ""])
            for parameter in command["parameters"]:
                lines.append(_render_parameter(parameter))
        if command["remaining_work"]:
            lines.extend(["", "Remaining specification work:", ""])
            lines.extend(f"- {item}" for item in command["remaining_work"])
        lines.append("")
        body = command.get("body")
        if body:
            _render_body(lines, command["canonical"], body)

    lines.extend([
        "## Nested block constructs",
        "",
        "| Parent | Construct | Match prefix | Kind | Coverage | Purpose |",
        "|---|---|---|---|---|---|",
    ])
    for construct in data["nested_constructs"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} |".format(
                _escape_cell(construct["parent_block_id"]),
                _escape_cell(construct["canonical"]),
                _escape_cell(construct["match_prefix"]),
                _escape_cell(construct["kind"]),
                _escape_cell(construct["coverage"]),
                _escape_cell(construct["summary"]),
            )
        )

    lines.extend(["", "## Nested construct details", ""])
    for construct in data["nested_constructs"]:
        evidence = ", ".join(evidence_links[item] for item in construct["evidence_ids"])
        lines.extend([
            f"### `{construct['canonical']}`",
            "",
            construct["summary"],
            "",
            f"- Registry ID: `{construct['id']}`",
            f"- Match prefix: `{construct['match_prefix']}`",
            f"- Coverage: {construct['coverage']}",
            f"- Evidence: {evidence}",
        ])
        _render_operations(lines, construct)
        if construct["parameters"]:
            lines.extend(["", "Known parameters:", ""])
            for parameter in construct["parameters"]:
                lines.append(_render_parameter(parameter))
        if construct["remaining_work"]:
            lines.extend(["", "Remaining specification work:", ""])
            lines.extend(f"- {item}" for item in construct["remaining_work"])
        lines.append("")
        if construct.get("body"):
            _render_body(lines, construct["canonical"], construct["body"])

    entity_contract = data["entity_contract"]
    lines.extend([
        "", "## Entity output contract", "",
        entity_contract["capability_record_policy"], "",
        "| Capability | Primary semantic output |",
        "|---|---|",
    ])
    for item in [
        *data["top_level_blocks"], *data["cluster_commands"],
        *data["nested_constructs"],
    ]:
        output = (
            f"`{item['entity_kind']}`"
            if item.get("entity_kind") else "capability record only"
        )
        lines.append(f"| `{item['id']}` | {output} |")
    lines.extend(["", "Additional conditional outputs:", ""])
    for item in entity_contract["additional_entity_outputs"]:
        capabilities = ", ".join(f"`{value}`" for value in item["capability_ids"])
        lines.append(
            f"- {capabilities} -> `{item['entity_kind']}` ({item['cardinality']}): "
            f"{item['condition']}"
        )

    dependency = data["dependency_contract"]
    lines.extend(["", "## Dependency and decision contract", ""])
    for item in dependency["classes"]:
        kinds = ", ".join(f"`{value}`" for value in item["reference_kinds"]) or "none"
        lines.extend([
            f"### `{item['id']}`",
            "",
            item["summary"],
            "",
            f"- Representation: `{item['representation']}`",
            f"- Semantic reference kinds: {kinds}",
            f"- Change policy: {item['change_policy']}",
            "",
        ])
    lines.extend([
        "Reference matrix:", "",
        "| Kinds | Class | Source entities | Target entities | Forward policy | Reverse/change policy |",
        "|---|---|---|---|---|---|",
    ])
    for item in dependency["reference_contracts"]:
        kinds = ", ".join(f"`{value}`" for value in item["kinds"])
        sources = ", ".join(f"`{value}`" for value in item["source_entity_kinds"])
        targets = ", ".join(f"`{value}`" for value in item["target_entity_kinds"])
        lines.append(
            f"| {kinds} | `{item['classification']}` | {sources} | {targets} | "
            f"{_escape_cell(item['forward_policy'])} | {_escape_cell(item['reverse_policy'])} |"
        )
    lines.append("")
    lines.extend(["Decision provenance:", ""])
    lines.extend(
        f"- `{item['id']}` (user input {'required' if item['requires_user_input'] else 'not required'}): {item['summary']}"
        for item in dependency["decision_sources"]
    )
    lines.extend(["", "Engineering clarification triggers:", ""])
    for item in dependency["clarification_triggers"]:
        scopes = ", ".join(f"`{value}`" for value in item["scope_ids"])
        operations = ", ".join(f"`{value}`" for value in item["operations"])
        choices = ", ".join(f"`{value}`" for value in item["required_choices"])
        lines.extend([
            f"- **{item['id']}** ({operations}; {scopes}): {item['condition']}",
            f"  - Required user-approved choices: {choices}",
        ])

    change_contract = data["change_contract"]
    lines.extend(["", "## Change impact contract", ""])
    for item in change_contract["operation_impacts"]:
        capabilities = ", ".join(f"`{value}`" for value in item["capability_ids"])
        lines.extend([
            f"### `{item['operation']}` via `{item['adapter']}`",
            "",
            f"- Capabilities: {capabilities}",
            "- Direct impacts:",
        ])
        lines.extend(f"  - {value}" for value in item["direct_impacts"])
        lines.append("- Required dependent checks:")
        lines.extend(f"  - {value}" for value in item["dependent_checks"])
        lines.append("")
    transformations = ", ".join(
        f"`{value}`" for value in change_contract["transformation_ids"]
    )
    lines.extend([
        f"- Registered transformation impacts: {transformations}",
        f"- Transformation policy: {change_contract['transformation_policy']}",
        "",
    ])

    consumer_contract = data["consumer_contract"]
    lines.extend(["", "## Consumer route contract", "", "Read routes:", ""])
    for item in consumer_contract["read_routes"]:
        operations = ", ".join(f"`{value}`" for value in item["operations"])
        consumers = ", ".join(f"`{value}`" for value in item["consumers"])
        lines.append(
            f"- {operations} ({item['scope']}) via {consumers}: {item['policy']}"
        )
    lines.extend([
        "", "Mutation routes:", "",
        "| Operation | Capabilities | Tools | Adapter | Policy |",
        "|---|---|---|---|---|",
    ])
    for item in consumer_contract["mutation_routes"]:
        capabilities = ", ".join(f"`{value}`" for value in item["capability_ids"])
        tools = ", ".join(f"`{value}`" for value in item["tools"])
        lines.append(
            f"| `{item['operation']}` | {capabilities} | {tools} | "
            f"`{item['adapter_kind']}` | {_escape_cell(item['policy'])} |"
        )

    repository_check = data["repository_check_contract"]
    lines.extend([
        "", "## Repository drift checks", "",
        f"- Repository command: `{repository_check['repository_command']}`",
        f"- Complete test command: `{repository_check['test_command']}`",
        f"- CI workflow: `{repository_check['ci_workflow']}`",
        "- Required checks: "
        + ", ".join(f"`{value}`" for value in repository_check["required_checks"]),
        f"- Coverage-ledger policy: {repository_check['ledger_policy']}",
        "", "Generated artifacts:", "",
    ])
    for item in repository_check["generated_artifacts"]:
        lines.append(
            f"- `{item['path']}` via `{item['producer']}`: {item['repository_check']}"
        )
    lines.extend(["", "Conditional checks:", ""])
    for item in repository_check["optional_checks"]:
        lines.append(
            f"- `{item['id']}` via `{item['command']}` when {item['condition']}"
        )

    lines.extend(["", "## Registered generation profiles", ""])
    for item in data["generation_profiles"]:
        evidence = ", ".join(evidence_links[value] for value in item["evidence_ids"])
        lines.extend([
            f"### `{item['id']}@{item['profile_version']}`",
            "",
            item["summary"],
            "",
            f"- Status: {item['status']}",
            f"- Tool: `{item['tool']}`",
            f"- Analysis: {item['analysis']}",
            f"- Mesh format: `{item['mesh_format']}`",
            f"- Evidence: {evidence}",
            "- Required engineering choices:",
        ])
        lines.extend(f"  - `{value}`" for value in item["required_choices"])
        lines.append("- Capability dependencies:")
        lines.extend(f"  - `{value}`" for value in item["capabilities"])
        lines.append("- Constraints:")
        lines.extend(f"  - {value}" for value in item["constraints"])
        lines.append("")

    lines.extend(["", "## Registered transformations", ""])
    for item in data["transformations"]:
        evidence = ", ".join(evidence_links[value] for value in item["evidence_ids"])
        lines.extend([
            f"### `{item['id']}@{item['algorithm_version']}`",
            "",
            item["summary"],
            "",
            f"- Coverage: {item['coverage']}",
            f"- Tool/operation: `{item['tool']}` / `{item['operation']}`",
            f"- Evidence: {evidence}",
            "- Applicability:",
        ])
        lines.extend(
            f"  - `{rule['path']}` {rule['operator']} `{json.dumps(rule['value'], ensure_ascii=False)}`; otherwise: {rule['failure']}"
            for rule in item["applicability"]
        )
        lines.append("- Approved/source-derived decisions:")
        lines.extend(
            f"  - `{decision['name']}` = `{json.dumps(decision['value'], ensure_ascii=False)}` ({decision['source']})"
            for decision in item["decisions"]
        )
        lines.append("- Impacts:")
        lines.extend(f"  - {value}" for value in item["impacts"])
        lines.append("- Dependencies:")
        lines.extend(f"  - {value}" for value in item["dependencies"])
        lines.append("")

    lines.extend([
        "", "## Obsolete and compatibility tokens", "",
        "| Token | Current replacement | Context | Behavior | Diagnostic |",
        "|---|---|---|---|---|",
    ])
    for item in data["obsolete_tokens"]:
        lines.append(
            "| `{}` | `{}` | {} | {} | `{}` |".format(
                _escape_cell(item["token"]),
                _escape_cell(item["replacement"]),
                _escape_cell(item["context"]),
                _escape_cell(item["behavior"]),
                _escape_cell(item["diagnostic"]),
            )
        )

    lines.extend(["", "## Execution contract", ""])
    execution = data["execution_contract"]
    lines.extend(
        [
            f"- Invocation: `{execution['invocation']}`",
            f"- Input extension: `{execution['input_extension']}`",
            f"- Success policy: {execution['success_policy']}",
            "- Known run/control artifacts:",
        ]
    )
    lines.extend(
        f"  - `{item['suffix']}`: {item['role']}" for item in execution["control_files"]
    )

    lines.extend(["", "## Evidence index", ""])
    for item in data["evidence"]:
        anchor = item["id"].replace(".", "")
        line_info = ""
        if "line_start" in item:
            line_info = f":{item['line_start']}"
            if item.get("line_end") != item["line_start"]:
                line_info += f"-{item.get('line_end', item['line_start'])}"
        lines.extend(
            [
                f"<a id=\"{anchor}\"></a>",
                f"- `{item['id']}` — {item['kind']}: `{item['locator']}{line_info}` — {item['claim']}",
            ]
        )

    lines.extend(
        [
            "",
            "## Coverage warning",
            "",
            "This is an initial active-dispatch inventory. It is not yet the complete parameter/type reference required by G1, and it must not be used to claim full generation support.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate", "generate", "check"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        data = load_registry(args.registry)
        counts = validate_registry(data)
        rendered = render_reference(data, args.registry)
    except (OSError, json.JSONDecodeError, RegistryError) as exc:
        print(f"registry error: {exc}", file=sys.stderr)
        return 1

    if args.action == "validate":
        print(
            "valid registry: "
            f"{counts['blocks']} blocks, {counts['commands']} cluster commands, "
            f"{counts['constructs']} nested constructs, "
            f"{counts['generation_profiles']} generation profiles, "
            f"{counts['transformations']} transformations, "
            f"{counts['obsolete_tokens']} obsolete/compatibility tokens, "
            f"{counts['evidence']} evidence records"
        )
        return 0
    if args.action == "generate":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"generated {args.output.relative_to(REPO_ROOT)}")
        return 0

    try:
        existing = args.output.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"generated reference missing: {exc}", file=sys.stderr)
        return 1
    if existing != rendered:
        print("generated reference is stale; run the generate action", file=sys.stderr)
        return 1
    print("generated reference is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
