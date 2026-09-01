# BSAM Agent

BSAM Agent will create, understand, modify, validate, and run current-syntax BSAM input files on Windows. This repository is intentionally separate from the BSAM source tree and will not modify BSAM itself.

Status: G1 coverage and G3 deterministic capability expansion remain in progress. The runnable core now includes lossless inspection, semantic validation, reviewed typed edits, mesh-template assembly, the approved notch 2-to-8-ply transformation, and supervised BSAM execution.

## Version 1 target

- BSAM 2.4 current syntax only
- Serial Windows execution through the existing `bsam20.exe`
- Manually prepared Abaqus-style `.ele` mesh/cluster data as the first mesh input
- Gmsh-backed generation for scoped geometry families after the `.ele` import slice
- Loss-preserving import and modification of existing current-syntax input files
- Dependency-aware structural transformations, including changing a model's ply count
- Complete coverage of active, documented BSAM input capabilities
- Reviewable change plans and diffs before a modified deck is written
- Deterministic validation and rendering before execution
- Optional CPU-local or hosted language-model assistance
- No MPI or result-reporting subsystem yet

## Documentation map

- [Project charter](docs/PROJECT_CHARTER.md)
- [Verification and trust model](docs/VERIFICATION.md)
- [System architecture](docs/architecture/SYSTEM_ARCHITECTURE.md)
- [Existing-model editing architecture](docs/architecture/MODEL_EDITING.md)
- [Abaqus-style mesh import and template assembly](docs/architecture/MESH_IMPORT.md)
- [Agent API documentation](docs/api/README.md)
- [Draft OpenAPI contract](docs/api/openapi.yaml)
- [Model tool contracts](docs/api/MODEL_TOOL_CONTRACTS.md)
- [Model-provider adapters](docs/api/PROVIDER_ADAPTERS.md)
- [BSAM syntax coverage ledger](docs/bsam/CURRENT_SYNTAX_COVERAGE.md)
- [Generated BSAM 2.4 input API reference](docs/bsam/reference/BSAM_2_4_INPUT_API.md)
- [Machine-readable BSAM 2.4 registry](specs/bsam-2.4/capabilities.json)
- [Specification extraction method](docs/bsam/SPECIFICATION_METHOD.md)
- [Roadmap](docs/roadmap/MILESTONES.md)
- [Local-data policy](docs/security/LOCAL_DATA_POLICY.md)
- [Development environment](docs/DEVELOPMENT_ENVIRONMENT.md)
- [Open inputs and assumptions](docs/OPEN_INPUTS.md)

## Authority and privacy

BSAM-specific behavior is derived only from local source, local documentation, local examples, and controlled runs of the local executable. BSAM source, real decks, mesh interchange files, and generated artifacts must not be sent to an external model provider. See the [local-data policy](docs/security/LOCAL_DATA_POLICY.md).

## Active pinned baseline

- Executable: `D:\Partha\BSAM\projects\bsam20.exe`
- Reported product version: BSAM 2.4, Windows Intel, unlocked build dated 2026-08-27 20:34:14
- Source commit observed locally: `9954027f1c325c63d58aeb836e8fec41a4b363af`
- Executable SHA-256: `7AE34D9821C6FE017897B020D615BFFA8A33F33F6D3734EBA3FD5A435788FB2A`

The source worktree contains four modified first-party SHEFF submodules, so the executable hash is required to identify the compiled artifact. See the [baseline audit](docs/bsam/BASELINE_AUDIT_2026-08-31.md).

## Run the first deterministic slice

The current CLI fingerprints a deck and its finite-element include source set, proves a byte-identical no-op round trip for every file, indexes recognized top-level blocks and cluster commands, and reports conservative current-syntax and include-graph diagnostics. It can also create, review, and apply a revision-bound minimal plan for an existing registered key/value parameter in the root deck. Applying a plan never overwrites the source deck and creates a digest-bound audit JSON sidecar without overwriting an existing audit.

From PowerShell in this repository:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m bsam_agent baseline
python -m bsam_agent inspect "..\projects\notch_v1\notch_v1.in"
python -m bsam_agent validate "..\projects\notch_v1\notch_v1.in"
python -m bsam_agent import-mesh "path\to\manually-prepared-mesh.ele"
python -m bsam_agent plan-change "..\projects\notch_v1\notch_v1.in" `
  --block BOUNDARY --construct CONVERGENCE `
  --parameter d_reduction --value 0.30 --out change.json
python -m bsam_agent diff change.json
python -m bsam_agent apply-change change.json --out notch_v1.changed.in
python -m bsam_agent plan-expand-notch-plies "..\projects\notch_v1\notch_v1.in" `
  --out "..\projects\notch_v1\notch_v1_8ply.plan.json"
python -m bsam_agent apply-change "..\projects\notch_v1\notch_v1_8ply.plan.json" `
  --out "..\projects\notch_v1\notch_v1_8ply.in"
python -m bsam_agent run notch_v1.changed.in `
  --output-dir runs\notch-v1-run --timeout 3600
python -m bsam_agent serve --workspace-root ".." --port 8765
# While run is active, from another terminal:
python -m bsam_agent status runs\notch-v1-run
python -m bsam_agent stop runs\notch-v1-run
```

Alternatively, `python -m pip install -e .` installs the local `bsam-agent` command. `validate` returns status 2 when it finds a blocking error. Typed edits remain deliberately bounded; structural support currently covers template-based mesh assembly and the applicability-checked notch 2-to-8-ply transformation.

`inspect`, `validate`, `plan-change`, and `run` recursively load `*INCLUDE, FILE=...` commands from CLUSTERS and included FE fragments. Nested targets follow BSAM behavior and resolve from the original deck's input directory, not from the including file. Missing files, malformed or quoted paths, include cycles, and targets outside the configured workspace are blocking diagnostics. The default workspace is the deck directory; `--workspace-root` can explicitly select a broader local boundary. Every imported file retains its own digest, bytes, line endings, and file boundary. New change plans are bound to the complete source-set digest and become stale if any included file changes. Because source-set copying is not implemented, applying a root-deck edit with includes currently requires the new deck to remain in the original input directory.

`diff` revalidates the plan digest and source revision before returning the semantic target, proposed output digest, validation result, and unified source diff. `apply-change` writes `<output>.audit.json` by default; `--audit-out` selects another new path. The audit binds the plan and output digests, changed model paths, validation result, source diff, and registered BSAM baseline. Its null run directory explicitly means the edit has not yet been linked to an execution.

`run` verifies the executable SHA-256, validates the deck, requires a new output directory, uses separate `-I`/`-O` arguments, captures process streams, and atomically updates `run-manifest.json`. While that command remains active, `status` can read its durable state and OS process liveness from another terminal. `stop` writes an immutable `stop-request.json` and requests BSAM's controlled `.exit` stop; it does not directly terminate the process. Repeated stop requests are idempotent. Success still requires the BSAM end-of-program sentinel, no classified fatal marker, and process exit code zero. If controlled stopping does not finish within the supervisor's grace period, only the owning `run` command escalates process termination.
