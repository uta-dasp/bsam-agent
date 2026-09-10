"""Deterministic construction of bounded current-syntax BSAM decks."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .mesh import MeshModel, import_ele, render_bsam_commands
from .registry import load_registry
from .source_set import SourceSet


GENERATION_SCHEMA_VERSION = "0.1.0"
GENERATOR_VERSION = "1.2.0"
PROFILE_ID = "generation.mechanical-isotropic-solid-v1"


class GenerationError(ValueError):
    """Raised when generation intent is incomplete, invalid, or unsafe."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _object(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GenerationError("invalid_intent", f"{name} must be an object")
    missing = sorted(keys - value.keys())
    extra = sorted(value.keys() - keys)
    if missing:
        raise GenerationError("missing_engineering_choice", f"{name} is missing: {', '.join(missing)}")
    if extra:
        raise GenerationError("invalid_intent", f"{name} has unknown fields: {', '.join(extra)}")
    return value


def _real(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenerationError("invalid_intent", f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise GenerationError("invalid_intent", f"{name} must be finite")
    if positive and result <= 0:
        raise GenerationError("invalid_intent", f"{name} must be positive")
    return result


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GenerationError("invalid_intent", f"{name} must be a positive integer")
    return value


def _token(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(char.isspace() for char in value):
        raise GenerationError("invalid_intent", f"{name} must be one nonblank token")
    if any(char in value for char in ",=*"):
        raise GenerationError("invalid_intent", f"{name} contains a reserved delimiter")
    return value.strip().lower()


def _number(value: float) -> str:
    return format(value, ".17g")


def _canonical_json(value: Any) -> bytes:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise GenerationError("invalid_intent", "intent must contain JSON-compatible finite values") from exc
    return text.encode("utf-8")


def _registered_profile() -> tuple[dict[str, Any], dict[str, Any]]:
    registry = load_registry()
    profiles = [item for item in registry.get("generation_profiles", []) if item.get("id") == PROFILE_ID]
    if len(profiles) != 1 or profiles[0].get("status") != "verified":
        raise GenerationError("unsupported_generation", f"registry does not authorize {PROFILE_ID}")
    return registry, profiles[0]


def _target(value: Any, name: str, mesh: MeshModel) -> str:
    node_sets = {item.name.casefold(): item.name for item in mesh.sets if item.kind == "node"}
    if isinstance(value, str) and value.casefold() in node_sets:
        return node_sets[value.casefold()]
    raise GenerationError("invalid_intent", f"{name} must name an existing mesh node set")


def _validate_intent(intent: Any, mesh: MeshModel) -> dict[str, Any]:
    if mesh.surfaces:
        raise GenerationError(
            "unsupported_generation",
            "this profile does not accept mesh SURFACE records because BSAM has no active cluster dispatch",
        )
    root = _object(intent, "intent", {
        "profile", "unit_system", "analysis", "cluster", "solver", "convergence",
        "loading", "material", "constitutive", "constraints", "loads",
    })
    if root["profile"] != PROFILE_ID:
        raise GenerationError("unsupported_generation", f"profile must be {PROFILE_ID}")
    if not isinstance(root["unit_system"], str) or not root["unit_system"].strip():
        raise GenerationError("missing_engineering_choice", "unit_system must be stated explicitly")

    analysis = _object(root["analysis"], "analysis", {"type", "kinematics", "name", "status"})
    if analysis["type"] != "mechanical" or analysis["kinematics"] != "linear":
        raise GenerationError("unsupported_generation", "this profile supports only linear mechanical analysis")
    analysis_name = _token(analysis["name"], "analysis.name")
    if analysis["status"] not in {"new", "no restart"}:
        raise GenerationError("invalid_intent", "analysis.status must be new or no restart")

    cluster = _object(root["cluster"], "cluster", {"name"})
    cluster_name = _token(cluster["name"], "cluster.name")
    reserved = {
        "input", "solver", "moisture", "boundary", "constitutive", "failure",
        "crack", "tables", "statistical", "ufunctions", "user", "clusters", "materials",
    }
    if cluster_name in reserved:
        raise GenerationError("invalid_intent", "cluster.name is a reserved top-level token")

    solver = _object(root["solver"], "solver", {"type", "n_threads", "matrix_type"})
    if solver["type"] != "pardiso":
        raise GenerationError("unsupported_generation", "this profile supports only the serial PARDISO solver")
    n_threads = _positive_integer(solver["n_threads"], "solver.n_threads")
    if solver["matrix_type"] not in {"indefinite", "unsymmetric"}:
        raise GenerationError("invalid_intent", "solver.matrix_type is not registered")

    convergence = _object(
        root["convergence"], "convergence",
        {"relative_tolerance", "absolute_tolerance", "divergence_tolerance", "max_iterations"},
    )
    relative_tolerance = _real(
        convergence["relative_tolerance"], "convergence.relative_tolerance", positive=True,
    )
    absolute_tolerance = _real(
        convergence["absolute_tolerance"], "convergence.absolute_tolerance", positive=True,
    )
    divergence_tolerance = _real(
        convergence["divergence_tolerance"], "convergence.divergence_tolerance", positive=True,
    )
    max_iterations = _positive_integer(
        convergence["max_iterations"], "convergence.max_iterations",
    )

    loading = _object(root["loading"], "loading", {"name", "step_count", "increment"})
    loading_name = _token(loading["name"], "loading.name")
    step_count = _positive_integer(loading["step_count"], "loading.step_count")
    load_increment = _real(loading["increment"], "loading.increment")

    material = _object(root["material"], "material", {
        "youngs_modulus", "poisson_ratio", "thermal_expansion", "tensile_strength",
        "compressive_strength", "shear_strength",
    })
    youngs_modulus = _real(material["youngs_modulus"], "material.youngs_modulus", positive=True)
    poisson_ratio = _real(material["poisson_ratio"], "material.poisson_ratio")
    if not -1.0 < poisson_ratio < 0.5:
        raise GenerationError("invalid_intent", "material.poisson_ratio must be between -1 and 0.5")
    thermal_expansion = _real(material["thermal_expansion"], "material.thermal_expansion")
    tensile_strength = _real(material["tensile_strength"], "material.tensile_strength", positive=True)
    compressive_strength = _real(material["compressive_strength"], "material.compressive_strength", positive=True)
    shear_strength = _real(material["shear_strength"], "material.shear_strength", positive=True)

    constitutive = _object(root["constitutive"], "constitutive", {"failure_type", "z_rotation_degrees"})
    failure_type = constitutive["failure_type"]
    allowed_failures = {4, 5, 6, 7, 10, 11, 12, 13, 19, 20, 21, 27, 45}
    if isinstance(failure_type, bool) or failure_type not in allowed_failures:
        raise GenerationError("invalid_intent", "constitutive.failure_type is not a supported no-data bulk criterion")
    rotation = _real(constitutive["z_rotation_degrees"], "constitutive.z_rotation_degrees")

    if not isinstance(root["constraints"], list) or not root["constraints"]:
        raise GenerationError("missing_engineering_choice", "constraints must contain at least one explicit constraint")
    constraints: list[dict[str, Any]] = []
    for index, raw in enumerate(root["constraints"], start=1):
        item = _object(raw, f"constraints[{index}]", {"target", "first_dof", "last_dof", "value"})
        first = _positive_integer(item["first_dof"], f"constraints[{index}].first_dof")
        last = _positive_integer(item["last_dof"], f"constraints[{index}].last_dof")
        if first > 3 or last > 3 or first > last:
            raise GenerationError("invalid_intent", f"constraints[{index}] has an invalid degree-of-freedom range")
        constraints.append({
            "target": _target(item["target"], f"constraints[{index}].target", mesh),
            "first_dof": first, "last_dof": last,
            "value": _real(item["value"], f"constraints[{index}].value"),
        })

    if not isinstance(root["loads"], list) or not root["loads"]:
        raise GenerationError("missing_engineering_choice", "loads must contain at least one explicit load")
    loads: list[dict[str, Any]] = []
    for index, raw in enumerate(root["loads"], start=1):
        item = _object(raw, f"loads[{index}]", {"target", "dof", "value"})
        dof = _positive_integer(item["dof"], f"loads[{index}].dof")
        if dof > 3:
            raise GenerationError("invalid_intent", f"loads[{index}].dof must be 1, 2, or 3")
        loads.append({
            "target": _target(item["target"], f"loads[{index}].target", mesh),
            "dof": dof, "value": _real(item["value"], f"loads[{index}].value"),
        })

    return {
        "profile": PROFILE_ID,
        "unit_system": root["unit_system"].strip(),
        "analysis": {
            "type": "mechanical", "kinematics": "linear",
            "name": analysis_name, "status": analysis["status"],
        },
        "cluster": {"name": cluster_name},
        "solver": {"type": "pardiso", "n_threads": n_threads, "matrix_type": solver["matrix_type"]},
        "convergence": {
            "relative_tolerance": relative_tolerance,
            "absolute_tolerance": absolute_tolerance,
            "divergence_tolerance": divergence_tolerance,
            "max_iterations": max_iterations,
        },
        "loading": {"name": loading_name, "step_count": step_count, "increment": load_increment},
        "material": {
            "youngs_modulus": youngs_modulus, "poisson_ratio": poisson_ratio,
            "thermal_expansion": thermal_expansion, "tensile_strength": tensile_strength,
            "compressive_strength": compressive_strength, "shear_strength": shear_strength,
        },
        "constitutive": {"failure_type": failure_type, "z_rotation_degrees": rotation},
        "constraints": constraints,
        "loads": loads,
    }


def render_generated_deck(mesh_path: Path, intent: Any) -> tuple[bytes, dict[str, Any]]:
    """Validate explicit intent and return canonical deck bytes plus stable provenance."""
    registry, profile = _registered_profile()
    mesh = import_ele(mesh_path)
    normalized = _validate_intent(intent, mesh)
    intent_sha256 = hashlib.sha256(_canonical_json(normalized)).hexdigest()
    generation_id = hashlib.sha256(
        f"{GENERATOR_VERSION}\n{registry['registry_version']}\n{mesh.sha256}\n{intent_sha256}".encode("ascii")
    ).hexdigest()
    material = normalized["material"]
    solver = normalized["solver"]
    constitutive = normalized["constitutive"]
    convergence = normalized["convergence"]
    loading = normalized["loading"]
    cluster = normalized["cluster"]
    lines = [
        f"** BSAM-AGENT GENERATION-ID {generation_id}",
        f"** REGISTRY {registry['registry_version']} PROFILE {PROFILE_ID}",
        f"** MESH-SHA256 {mesh.sha256}",
        f"** INTENT-SHA256 {intent_sha256}",
        "INPUT", "3", "END INPUT",
        "SOLVER", "*type=pardiso", f"n_threads={solver['n_threads']}",
        f"matrix_type={solver['matrix_type']}", "end solver", "END SOLVER",
        "BOUNDARY", "*type", "mechanical", "*solver", "1",
        "*status", normalized["analysis"]["status"],
        "*name", normalized["analysis"]["name"],
        "*clusters", cluster["name"],
        "*boundary condition",
    ]
    components = {
        (1, 1): "x", (2, 2): "y", (3, 3): "z",
        (1, 2): "xy", (2, 3): "yz", (1, 3): "xyz",
    }
    for index, item in enumerate(normalized["constraints"], start=1):
        component = components[(item["first_dof"], item["last_dof"])]
        lines.append(
            f"type=disp,comp={component},name=constraint{index},"
            f"value={_number(item['value'])},nset={cluster['name']}.{item['target']}"
        )
    for index, item in enumerate(normalized["loads"], start=1):
        component = components[(item["dof"], item["dof"])]
        lines.append(
            f"type=force,comp={component},name=load{index},"
            f"value={_number(item['value'])},nset={cluster['name']}.{item['target']}"
        )
    lines.extend([
        "*loading sequence",
        f"type=Static,name={loading['name']},nstep={loading['step_count']},"
        f"incr={_number(loading['increment'])}",
        "*convergence",
        f"relative={_number(convergence['relative_tolerance'])},"
        f"absolute={_number(convergence['absolute_tolerance'])},"
        f"divergence={_number(convergence['divergence_tolerance'])}",
        f"maxiterations={convergence['max_iterations']}",
        "END BOUNDARY",
        "CONSTITUTIVE", "1", f"1 1 {_number(constitutive['z_rotation_degrees'])}",
        "END CONSTITUTIVE",
        "FAILURE", str(constitutive["failure_type"]), "END FAILURE",
        "MATERIALS", "10",
        " ".join(_number(material[name]) for name in (
            "youngs_modulus", "poisson_ratio", "thermal_expansion",
        )),
        " ".join(_number(material[name]) for name in (
            "tensile_strength", "compressive_strength", "shear_strength",
        )),
        "END MATERIALS", "CLUSTERS", "*TYPE", "solid", "*NAME", cluster["name"],
    ])
    deck = "\n".join(lines).encode("latin-1") + b"\n"
    deck += render_bsam_commands(mesh)
    for selection_id, mesh_set in enumerate(
        (item for item in mesh.sets if item.kind == "node"), start=1,
    ):
        deck += (
            f"*SELECTION,ID={selection_id},TYPE=NODE\n{mesh_set.name}\n"
        ).encode("latin-1")
    deck += b"*CONSTITUTIVE\n1\n*STOP\nEND CLUSTERS\n"
    provenance = {
        "schema_version": GENERATION_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generation_id": generation_id,
        "registry_version": registry["registry_version"],
        "profile": {"id": PROFILE_ID, "version": profile["profile_version"]},
        "mesh": {"source": str(mesh_path.resolve()), "sha256": mesh.sha256},
        "intent": normalized,
        "intent_sha256": intent_sha256,
        "output_sha256": hashlib.sha256(deck).hexdigest(),
    }
    return deck, provenance


def generate_deck(
    mesh_path: Path, intent: Any, destination: Path, manifest_path: Path,
    workspace_root: Path, *, confirm: bool,
) -> dict[str, Any]:
    """Write a new deck and provenance manifest, refusing overwrite and rolling back partial output."""
    if not confirm:
        raise GenerationError("confirmation_required", "generation requires confirm=true")
    workspace = workspace_root.resolve()
    destination = destination.resolve()
    manifest_path = manifest_path.resolve()
    for path, role in ((mesh_path.resolve(), "mesh"), (destination, "destination"), (manifest_path, "manifest")):
        if not path.is_relative_to(workspace):
            raise GenerationError("path_not_allowed", f"{role} escapes the workspace")
    if destination == manifest_path:
        raise GenerationError("invalid_arguments", "destination and manifest must differ")
    if destination.exists() or manifest_path.exists():
        raise GenerationError("output_exists", "destination and manifest must both be new paths")
    if not destination.parent.is_dir() or not manifest_path.parent.is_dir():
        raise GenerationError("invalid_arguments", "destination and manifest parent directories must exist")

    deck, provenance = render_generated_deck(mesh_path, intent)
    created: list[Path] = []
    try:
        with destination.open("xb") as stream:
            stream.write(deck)
        created.append(destination)
        inspection = SourceSet.read(destination, workspace).inspection()
        if inspection["summary"]["errors"]:
            raise GenerationError("generated_validation_failed", "generated deck failed static validation")
        manifest = {
            **provenance,
            "mesh": {
                "source": mesh_path.resolve().relative_to(workspace).as_posix(),
                "sha256": provenance["mesh"]["sha256"],
            },
            "destination": destination.relative_to(workspace).as_posix(),
            "validation": inspection["summary"],
        }
        with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
            created.append(manifest_path)
            json.dump(manifest, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return manifest
