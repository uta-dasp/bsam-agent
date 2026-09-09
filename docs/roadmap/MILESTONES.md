# BSAM Agent development roadmap

This is the single authoritative implementation roadmap. A checked item is implemented and verified. BSAM-specific behavior must come from the pinned local BSAM source, controlled executable probes, or trusted local documentation.

## Product objective

Build a dependable, general BSAM 2.4 agent that can inspect, create, modify, validate, render, and run models across the active current-syntax capability set. The language model interprets intent and conducts clarification; deterministic code owns BSAM syntax, semantics, changes, validation, and execution.

The notch project is one laminate regression fixture. It does not define the architecture or limit supported capabilities.

## Current checkpoint

The repository has a loss-preserving source-set loader, an initial semantic/reference model, bounded editing operations, `.ele` import, isolated serial execution, a loopback Agent API, and a guarded local chat client. These establish the infrastructure but do not constitute broad BSAM capability coverage.

Current focus: develop one capability family at a time through authoritative grammar, loss-preserving semantics, dependencies, focused query, safe generic editing, validation, agent exposure, and natural-language evaluation. Cross-cutting specification work continues when a selected vertical slice requires it; horizontal registry coverage is not an execution gate for M2 or M4 work.

Specification maturity and operational maturity are separate. Registry `coverage` records how well grammar is documented. Per-capability `operations` records whether parse, semantic, inspect, modify, create, delete, rename, generate, static-validation, and execution behavior is unassessed, unsupported, implemented, or verified. A documented grammar must never be presented as editable merely because it is documented.

## M0 — Foundation and vertical slice

Status: complete.

- [x] Establish the independent repository, scope, security boundary, and architecture.
- [x] Pin the BSAM 2.4 source/executable baseline and evidence method.
- [x] Implement lossless root/include loading and byte-identical no-op rendering.
- [x] Implement initial semantic entities and reference diagnostics.
- [x] Implement revision-bound plans, diffs, non-overwriting apply, and audit records.
- [x] Implement selected node, element, set, boundary, parameter, and transformation edits.
- [x] Import manually prepared Abaqus-style `.ele` mesh data into a neutral model.
- [x] Implement isolated serial run, status, timeout, and controlled stop.
- [x] Expose deterministic tools through a loopback-only API.
- [x] Establish provider-neutral and CPU-local guarded chat infrastructure.
- [x] Verify the notch two-to-eight-ply transformation as one regression scenario.

Exit: the full architecture works for a bounded vertical slice without trusting an LLM.

## M1 — Complete active BSAM 2.4 specification

Status: in progress. Registry `0.66.0` currently inventories 13 top-level blocks, 29 cluster commands, 12 nested BOUNDARY constructs, and two transformations.

### M1.1 Reachable-dispatch audit

- [x] Enumerate every active top-level, BOUNDARY, and finite-element command dispatch.
- [x] Link every primary dispatch to a pinned local source location and calling path.
- [x] Classify active dispatches plus commented and deprecated initialization paths.
- [x] Reconcile the primary audit with `capabilities.json` and produce a zero-omission report.

### M1.2 Grammar completion

- [x] Enumerate all 28 active MATERIALS types and document structured types 50, 998, and 999.
- [x] Document exact positional grammars for all 25 legacy MATERIALS types and block unsafe external/fragile paths.
- [x] Document all 29 finite-element CLUSTERS command grammars, explicitly blocking unsafe source paths.
- [x] Document all 12 nested BOUNDARY construct grammars, defaults, dependencies, and unsafe source paths.
- [ ] Record exact command matching, record layouts, termination, and repetition.
- [ ] Complete parameter types, defaults, allowed values, ranges, and units.
- [ ] Record conditional variants and cross-parameter constraints.
- [ ] Mark unsupported ambiguity explicitly; never infer grammar from examples alone.

### M1.3 Entity and dependency specification

- [ ] Separate deterministic structural references from BSAM semantic constraints and from engineering decisions that require user intent.
- [ ] Define entities created by every active construct.
- [ ] Define forward and reverse references across analysis controls, clusters, mesh, sets, sections, orientations, materials, constitutives, failures, cracks, boundary conditions, loads, connections, tables, statistics, moisture, and user functions.
- [ ] Record rename, deletion, creation, and transformation impacts.
- [ ] Identify decisions that require engineering clarification.

### M1.4 Generated contracts

- [x] Validate registry invariants and evidence links with `tools/registry_tools.py`.
- [x] Generate the human BSAM input reference from the registry.
- [x] Detect stale generated input-reference output in repository checks.
- [x] Expose a machine-consumable operational manifest and strict tool contracts consumed by parser/editor/query/agent paths for the verified subset.
- [ ] Complete shared machine-consumable capability contracts for the remaining parser, editor, and validator paths.
- [x] Expose registry-derived operational-support and intent metadata through `get_capabilities` for the agent consumer.
- [ ] Generate additional coverage ledgers only when a concrete repository or CI consumer requires them.
- [ ] Enforce all generated-contract and coverage drift in CI/repository checks.

Exit: every reachable active input path is fully specified or explicitly blocked with evidence.

## M2 — Registry-driven deterministic engine

Status: partially implemented. Loss-preserving parsing, selected semantic entities/references, registered parameter edits, node/element/set edits, boundary-condition rename, solver migration, notch laminate transformation, and mesh-template assembly exist. M2 generalizes these mechanisms where registry metadata is sufficient; it does not restart them.

### M2.1 Generic parsing and semantic model

- [x] Parse registry-matched BOUNDARY/control occurrences and registered values into source-located capability records without changing concrete syntax.
- [x] Parse current and legacy SOLVER definitions, effective defaults, and BOUNDARY solver-schedule references without rewriting source.
- [x] Parse named TABLES grids, source-located values, and structured material `table_<name>` references without assigning guessed material ordinals.
- [x] Parse named UFUNCTIONS point data and structured material `ufunc_<name>` references with exact entry-boundary and monotonicity checks.
- [x] Parse named STATISTICAL type-3 distributions, dynamic seed dimensions, cluster/section dependencies, and structured material `stat_<name>` references.
- [x] Attribute named-data references to source-bounded 998/999 structured MATERIALS declarations while preserving legacy bodies without inferred identities.
- [x] Parse every CONSTITUTIVE and FAILURE variant by exact declaration-order record consumption, including modifiers, wrappers, degradation rows, and dynamic subrecords.
- [x] Populate direct constitutive material/failure references only when complete declaration-order scans prove the corresponding target identities; preserve unproven legacy MATERIALS bodies without guessed ordinals.
- [x] Parse cluster-local BOUNDARY and LOAD rows into source-located semantic records with source-defined set-first or LIST node-only target references.
- [x] Parse cluster-local FIELD and SELECTION records into source-located node, element, and set dependencies while keeping source-defective generation paths blocked.
- [x] Parse explicit and ALL BOUNDARY cluster selectors into source-located cluster dependencies with missing-name diagnostics.
- [x] Resolve BOUNDARY data-file, force/traction, volume-average, and CFV output selectors to active clusters and qualified node/element sets, including ALL/list expansion and scope diagnostics.
- [x] Index source-defined `*CRACK REGION,ELSET=...` dependencies so element-set deletion cannot orphan crack-region selection.
- [x] Index EXCLUSION and geometric CRACK REGION box/plane/sphere/cylinder selectors as source-located, inspection-only cluster operations.
- [x] Index BUILD and STOP as source-located, inspection-only topology barriers targeting the active cluster.
- [x] Index TOLERANCE plus standalone and CRACK SPACING forms as source-located, inspection-only cluster settings.
- [x] Bind source-located TYPE declarations and DIMENSIONS capacities to the following normalized cluster NAME without changing unnamed legacy entity scope.
- [x] Expose cluster CONSTITUTIVE assignments as typed, source-located dependencies on declaration-order constitutive definitions.
- [x] Parse nodal and elemental ORIENTATION rows into source-located node, element, and set dependencies so structural deletion remains fail-closed.
- [x] Parse SHIFT/SCALE NSET and INTEGRATION element dependencies, and retarget exact SHIFT/SCALE NSET values through the generic modify surface.
- [x] Index ALL/default SHIFT/SCALE plus FLIP and inertial TRANSFORM as source-located cluster coordinate operations; keep coordinate mutation unavailable.
- [x] Index NGEN endpoint, NCOPY source-set, and generated output-set relationships without overclaiming generated-node identities.
- [x] Derive bounded NGEN/NCOPY generated-node identities for direct, arc, paired-set, and explicit-source copy rows so downstream connectivity resolves deterministically.
- [x] Preserve source-defined generated-set membership: NGEN output sets contain both endpoints and generated nodes, while NCOPY output sets contain generated copies only.
- [x] Derive bounded ELGEN element identities and shifted connectivity, while blocking generated entities from unsafe single-record deletion.
- [x] Traverse FE includes inline for semantic indexing so nested fragments inherit active cluster state and included `*NAME` changes persist when the parent stream resumes.
- [x] Index each reachable INCLUDE occurrence as a typed, source-located operation targeting the cluster active at that point in the inline stream.
- [x] Emit uniform source-located capability records and registered parameter/default/operation views for every reachable cluster-command occurrence.
- [x] Declare verified typed read paths for all 12 registered BOUNDARY constructs and expose solver schedules and connections through entity queries.
- [x] Expose the active INPUT format as a source-located registered block record with registry-driven value validation.
- [x] Parse canonical MOISTURE settings into a typed workflow record while keeping external execution explicitly unsupported.
- [x] Expose CLUSTERS and BOUNDARY as source-located container records backed by their typed command/construct children.
- [x] Type the fixed leading records of global CRACK declarations and resolve name-or-ordinal cluster selectors without claiming optional geometry edits.
- [x] Cursor-parse numeric USER types 1-5, 101, and 201 into declaration-order entities while retaining types 100 and 301 as explicit preservation-only boundaries.
- [x] Parse completed registry constructs into typed records while preserving concrete syntax; enforce implemented-or-verified read contracts across all 54 active constructs.
- [x] Preserve unknown or not-yet-supported records losslessly.
- [x] Represent loaded source files with workspace-stable identities and link resolved INCLUDE operations to their target files.
- [x] Resolve CONSTITUTIVE type-3/type-4 curve and twist selectors to declaration-order numeric USER function identities.
- [x] Give repeated cross-file semantic occurrences unique entity IDs while retaining shared keys for duplicate-definition validation.
- [x] Derive reference IDs from their source, target, kind, and location so unrelated edges cannot renumber cross-file links.
- [ ] Populate consistent entity identities and cross-file references.
- [ ] Replace feature-specific semantic extraction where registry metadata is sufficient.

### M2.2 Generic parameter editing

- [x] Select existing key/value parameters by canonical registered capability identity for the currently supported subset.
- [x] Query explicit and registered-default BOUNDARY/control values with deterministic ambiguity reporting.
- [x] Query and minimally patch existing current-syntax SOLVER options by canonical capability identity; legacy positional edits remain blocked behind the verified migration.
- [x] Validate and minimally replace existing real, integer, enum, and string values for the verified editable subset, including finite and signed-range checks encoded by registered value types.
- [x] Insert an absent optional `*CONVERGENCE` `maxiterations` record only when parameter-level registry policy marks insertion verified.
- [x] Remove an isolated explicit `*CONVERGENCE` `maxiterations` record to restore its registered default only when parameter-level policy marks removal verified.
- [x] Enable or disable the optional Boolean `*G-CONTROL` `DAMP` flag through exact command-line tokens and parameter-level registry policy.
- [x] Insert or remove the optional SHEFF `relative_tolerance` row within a repeated solver option group, restoring the source-defined default on removal.
- [ ] Support insertion/removal of repeated values where source evidence and edit policy permit them.
- [ ] Produce minimal source patches with deterministic defaults and validation.
- [ ] Return actionable missing, unknown, ambiguous, and invalid-value diagnostics.

### M2.3 Generic structural editing

- [x] Dispatch boundary-condition rename through a capability-identified generic rename surface while retaining the specialized regression tool.
- [x] Dispatch verified node create/delete, element create, and node/element-set create/extend operations through capability-gated generic structural surfaces while retaining compatibility tools.
- [x] Remove one exact explicit node/element-set member through the generic modify surface, including path-bound include edits, while blocking ambiguous or empty-set results.
- [x] Retarget one exact cluster-local BOUNDARY or LOAD record through the generic modify surface, preserving its source file and blocking ambiguous, missing, LIST-invalid, or POLYNOMIAL-unsafe targets.
- [x] Delete one isolated, unreferenced explicit node/element set through the generic delete surface while blocking implicit, generated, commented, or multiply-defined sets.
- [x] Delete one unreferenced explicit element through the generic delete surface, including path-bound include edits, while blocking set, selection, and implicit-membership dependencies.
- [x] Retarget one exact SECTION assignment to an existing element set through the generic modify surface, including path-bound include edits and ambiguity blocking.
- [ ] Create, delete, rename, reorder, and list supported entities and records.
- [ ] Edit tables, repeated records, member lists, and referenced names.
- [x] Generalize path-bound reviewed include-file edits across verified node, element, set, and empty-cluster mesh insertion operations.
- [x] Copy a reviewed root edit plus unchanged relative include files to a separate source-set directory with preflight conflict checks, digest verification, and partial-write rollback.
- [x] Delete an unreferenced node from an included FE fragment through a path-bound patch, and compose root/include changes into one reviewed source-set plan without touching originals.
- [ ] Compute dependent updates and block destructive changes with unresolved dependents.
- [ ] Keep specialized transformations only for genuine engineering operations, not ordinary syntax edits.

### M2.4 Deterministic generation

- [ ] Build new current-syntax decks from typed analysis and mesh intent.
- [ ] Require all essential engineering choices rather than inventing them.
- [ ] Render canonical current syntax with provenance and stable digests.

Exit: ordinary supported BSAM operations are driven by registry metadata, not prompt-specific or fixture-specific code.

## M3 — Comprehensive validation and evidence

- [x] Add end-to-end parser, semantic, query, edit, invalid-value, no-op, and natural-language tests for the initial BOUNDARY/CONVERGENCE operational slice.
- [x] Add SOLVER parser, schedule-reference, missing-second-solver, safe-option, legacy-preservation, edit, and natural-language trajectory tests.
- [x] Add TABLES grid, monotonicity, duplicate/missing-reference, query, no-op, and natural-language tests.
- [x] Add UFUNCTIONS width, point-count, monotonicity, duplicate/missing-reference, query, no-op, and natural-language tests.
- [x] Add STATISTICAL required-key, dynamic-order, type/range, duplicate/missing-reference, cluster, query, no-op, and natural-language tests.
- [x] Add structured MATERIALS boundary, partial-support, declaration-attribution, legacy-preservation, query, and natural-language tests.
- [x] Classify every emitted diagnostic by validation level and evidence provenance, reject unclassified new codes, and summarize diagnostics by both dimensions.
- [ ] Validate structure, types, ranges, cardinality, and required records for every supported construct.
- [ ] Validate references, dependency rules, mesh connectivity, sets, topology, and cross-feature constraints.
- [ ] Add golden no-op and minimal-patch tests for every syntax family.
- [ ] Add invalid, ambiguous, and dependency-breaking test cases.
- [ ] Add small representative fixtures across capability families; keep notch as one regression fixture.
- [ ] Add controlled executable probes where static source evidence is insufficient.
- [ ] Round-trip and executable-test a representative imported `.ele` model after an appropriate analysis template is available.

Exit: capability support is measurable, reproducible, and protected against regression.

## M4 — General agent workflow

Status: partially implemented. Provider-neutral messaging, the local provider and Scout runtime, conversation persistence, phases, confirmation, tool schemas, response repair, audit metadata, deterministic parameter recognition, a guarded terminal client, bounded engineering-task state, and the first inspect/preview/confirm/apply/validate trajectory exist. The remaining objective is to generalize this guarded trajectory across supported engineering tasks, not to build chat again.

- [x] Expose operational support and focused BOUNDARY/control queries through deterministic tools and capability-derived routing.
- [x] Expose current SOLVER inspection and modification through the same generic query/change trajectory while reporting legacy instances as inspectable but not generically modifiable.
- [x] Expose verified FE node, element, and set planners through generic capability-identified create, modify, and delete tools.
- [x] Query entity listings and inbound/outbound references by stable kind/name selectors without requiring opaque source-location IDs.
- [x] Persist bounded task state, focused ambiguity decisions, ordered tool evidence, failure classifications, and attempt fingerprints separately from message history.
- [x] Chain safe source inspection and post-apply validation around a confirmed registered change without weakening the confirmation boundary.
- [x] Add deterministic trajectory cases for parameter modification, ambiguity, dependent rename, unsupported creation, stale revision, and failed execution.
- [x] Re-preview digest-valid stale plans by replaying typed selectors and requested values, with bounded recovery attempts and a fresh confirmation boundary.
- [x] Generate high-level inspect, query, create, modify, validate, and run intent maturity from the capability registry and use it for prompt applicability.
- [x] Map varied language and parameter phrases to capability identities without exposing low-level parser details; registry-derived routes now precede compatibility branches where equivalent tests pass.
- [x] Persist typed clarification choices and pending arguments for ambiguous parameter context, including save/resume and focused continuation.
- [x] Compose 2–8 independent same-revision deterministic operations into one reviewed plan, rejecting overlap and revalidating every typed component plus the combined result.
- [x] Evaluate paraphrases, ambiguity, unsupported requests, prompt injection, confirmation, and stale state across the current capability families with the 33 decision cases and 15 trajectory specifications.
- [x] Re-benchmark the local model after the generic capability surface is stable; Scout still fails the autonomous-routing gate on the expanded 33-case suite.
- [x] Complete lossless inspect/review/apply/validate acceptance on the available trusted non-notch `TriC_v311` project without changing its engineering behavior.
- [ ] Complete guarded live-model and executable acceptance on additional trusted non-notch projects when suitable inputs are available.

The target bounded workflow is UNDERSTAND -> INSPECT -> RESOLVE CAPABILITIES -> CLARIFY -> PLAN -> VALIDATE PLAN -> REVIEW -> CONFIRM -> APPLY -> VALIDATE RESULT -> RUN -> VERIFY -> DIAGNOSE/RECOVER -> REPORT. Model output selects the next permitted action; deterministic policy remains authoritative. Safe read-only steps may chain automatically, while mutation and run boundaries retain explicit confirmation. Initial task state is distinct from message history and retains the objective, source, resolved capabilities, assumptions, missing engineering decisions, plan, validation/run state, failure evidence, attempt fingerprints, and bounded step/recovery counts.

`relevant_tools()` remains a transitional prompt-size optimization, not an authorization boundary. Characterize it with regression tests, introduce capability-derived applicability and routing, retain backward-compatible fallback, and remove prompt-specific keyword branches only after equivalent trajectory evaluations pass.

Exit: adding a registered deterministic capability makes it available to chat without adding prompt-specific routing code.

## M5 — Scoped embedded mesh generation

- [ ] Select initial geometry families, element mappings, physical-group conventions, ply/orientation rules, and quality tolerances.
- [ ] Pin a local Gmsh runtime with no network dependency.
- [ ] Implement typed geometry/meshing recipes and deterministic neutral-mesh conversion.
- [ ] Validate quality and equivalence against trusted target meshes.

Input gate: user selection of the first geometry families and trusted acceptance meshes after M1 completes.

## M6 — Product clients and optional providers

- [ ] Add hosted providers only behind explicit data policy and the same conformance suite.
- [ ] Build a thin VS Code client over the stable local API.
- [ ] Add schema-aware diagnostics, forms, reviewed diffs, chat, and run controls.

## Deferred

- MPI execution.
- Automated results interpretation and report generation.
- General-purpose arbitrary CAD repair and unrestricted meshing.
- Modification of BSAM source code.

## Next execution sessions

1. Continue dependency indexing for source-backed cluster transformations and selection consumers; keep engineering-significant coordinate mutations non-editable.
2. Continue non-notch live acceptance when another trusted representative project is available; do not fabricate engineering fixtures.

No user input is required until source behavior is genuinely ambiguous, an executable probe needs approval, or the M5 geometry-family gate is reached.
