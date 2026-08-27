# BSAM Agent

BSAM Agent will create, understand, modify, validate, and run current-syntax BSAM input files on Windows. This repository is intentionally separate from the BSAM source tree and will not modify BSAM itself.

Status: groundwork only. The repository currently contains architecture, API contracts, scope decisions, and a staged roadmap. It contains no application implementation or model runtime.

## Version 1 target

- BSAM 2.4 current syntax only
- Serial Windows execution through the existing `bsam20.exe`
- VTMS mesh/cluster data as the first mesh input
- Gmsh-backed generation for scoped geometry families after the VTMS import slice
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

BSAM-specific behavior is derived only from local source, local documentation, local examples, and controlled runs of the local executable. BSAM source, real decks, VTMS files, and generated artifacts must not be sent to an external model provider. See the [local-data policy](docs/security/LOCAL_DATA_POLICY.md).

## Pinned starting baseline

- Executable: `D:\Partha\BSAM\projects\bsam20.exe`
- Reported product version: BSAM 2.4, Windows Intel, serial build
- Source commit observed locally: `7e414be55abae10e2a648bd39bcc07b4904e9edc`
- Executable SHA-256: `580B7AF434BF4F453B8137802246FEB292DD89A04FDB3DD54000EC9A225E146F`

These values are evidence for the first specification snapshot, not permanent configuration defaults.
