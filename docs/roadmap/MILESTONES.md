# Milestones

## G0 — Groundwork

Deliverables:

- independent Git repository;
- scope and architecture;
- API lifecycle and draft OpenAPI contract;
- source-derived specification method and coverage ledger;
- privacy/provider policy;
- environment inventory and recorded unknowns.

Exit: documents agree on scope and no implementation decision depends on a missing manual.

## G1 — Current BSAM input API specification

Status: in progress. Registry `0.2.0` establishes the pinned baseline, top-level and FE command inventories, active BOUNDARY construct inventory, structured bodies for eight core mesh/section commands, execution contract, validation tool, and generated reference.

Deliverables:

- machine-readable capability registry;
- current block/command/parameter documentation;
- lossless concrete-syntax and include-graph requirements;
- entity/reference dependency map for safe modifications;
- registered transformation contract and applicability rules;
- provenance links to pinned local source and examples;
- obsolete-token diagnostic registry;
- executable invocation and run-classification contract;
- generated human-readable API reference.

Exit: every active parser dispatch path is accounted for or explicitly blocked.

## G2 — Deterministic core vertical slice

Deliverables:

- Python package and CLI;
- canonical model schema;
- lossless import of a representative current `.in` source set;
- preview/apply/diff support for direct parameter edits;
- import of one real VTMS `.ele` sample or agreed cluster interchange format;
- validation and deterministic rendering;
- isolated Windows serial run supervision;
- contract and integration tests.

Initial commands: `inspect`, `import`, `plan-change`, `apply-change`, `diff`, `validate`, `render`, `run`, `status`, and `stop`.

Exit: an existing deck can be safely modified and run, and a supplied VTMS mesh can be combined with explicit analysis data, rendered, and run without a language model.

## G3 — Full current-capability implementation

Deliverables:

- typed support for all G1 capabilities;
- byte-identical no-op round-trip and minimal-patch golden tests;
- dependency-aware transformation framework;
- supported two-ply-to-eight-ply transformation acceptance fixture;
- representative executable tests;
- versioned capability manifest exposed by the API.

Exit: the coverage ledger has no unexplained current-syntax gaps, and supported edits cannot leave unresolved dependent references.

## G4 — Model-assisted authoring

Deliverables:

- provider-neutral structured-output/tool interface;
- CPU-local benchmark and selected allowed local model;
- Gemini adapter for sanitized or synthetic payloads;
- OpenAI adapter under an explicit data policy;
- prompt-injection, schema, and tool-policy tests.

Exit: the model improves authoring while invalid or unauthorized calls remain blocked by the deterministic core.

## G5 — Gmsh-backed embedded mesh generation

Deliverables:

- pinned local Gmsh executable/library adapter with no network dependency;
- typed, explicitly scoped geometry and meshing recipes exposed through Agent tools;
- deterministic `.msh` import into an intermediate mesh model;
- mapping of Gmsh physical groups to BSAM clusters, node sets, and element sets;
- supported-element conversion, label allocation, orientation, ply, and interface rules;
- deterministic node/element/set/orientation generation and BSAM cluster insertion;
- topology and quality validation;
- previewable geometry/mesh parameters and provenance manifests;
- equivalence tests against trusted small models and pinned-executable probes.

The optional language model may translate user intent into the typed geometry tools, but it will not generate authoritative node/connectivity text or invoke Gmsh directly. The deterministic Gmsh adapter owns geometry construction, meshing, import, validation, and conversion.

Exit: the initial supported geometry families generate validated, executable current-syntax clusters without VTMS, while unsupported element/topology requests fail with explicit diagnostics.

## G6 — VS Code extension

Deliverables:

- thin TypeScript client of the local API;
- schema-aware editor assistance and diagnostics;
- model form/preview, render diff, run controls, and status display;
- packaging and Windows setup documentation.

Exit: core behavior remains usable and testable without VS Code.

## Later

- MPI support
- result interpretation and reporting
- broader mesh generation
- controlled obsolete-input migration
