# BSAM Agent development roadmap

This is the single authoritative implementation roadmap. A checked item is implemented and verified. BSAM-specific behavior must come from the pinned local BSAM source, controlled executable probes, or trusted local documentation.

## Product objective

Build a dependable, general BSAM 2.4 agent that can inspect, create, modify, validate, render, and run models across the active current-syntax capability set. The language model interprets intent and conducts clarification; deterministic code owns BSAM syntax, semantics, changes, validation, and execution.

The notch project is one laminate regression fixture. It does not define the architecture or limit supported capabilities.

## Current checkpoint

The repository has a loss-preserving source-set loader, an initial semantic/reference model, bounded editing operations, `.ele` import, isolated serial execution, a loopback Agent API, and a guarded local chat client. These establish the infrastructure but do not constitute broad BSAM capability coverage.

Current focus: complete the BSAM specification and build registry-driven deterministic behavior. Chat-specific polishing is frozen except where required to expose or test generic capabilities.

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

Status: in progress. Registry `0.15.0` currently inventories 13 top-level blocks, 29 cluster commands, 12 nested BOUNDARY constructs, and two transformations.

### M1.1 Reachable-dispatch audit

- [x] Enumerate every active top-level, BOUNDARY, and finite-element command dispatch.
- [x] Link every primary dispatch to a pinned local source location and calling path.
- [x] Classify active dispatches plus commented and deprecated initialization paths.
- [x] Reconcile the primary audit with `capabilities.json` and produce a zero-omission report.

### M1.2 Grammar completion

- [x] Enumerate all 28 active MATERIALS types and document structured types 50, 998, and 999.
- [ ] Record exact command matching, record layouts, termination, and repetition.
- [ ] Complete parameter types, defaults, allowed values, ranges, and units.
- [ ] Record conditional variants and cross-parameter constraints.
- [ ] Mark unsupported ambiguity explicitly; never infer grammar from examples alone.

### M1.3 Entity and dependency specification

- [ ] Define entities created by every active construct.
- [ ] Define forward and reverse references across analysis controls, clusters, mesh, sets, sections, orientations, materials, constitutives, failures, cracks, boundary conditions, loads, connections, tables, statistics, moisture, and user functions.
- [ ] Record rename, deletion, creation, and transformation impacts.
- [ ] Identify decisions that require engineering clarification.

### M1.4 Generated contracts

- [ ] Generate the human BSAM input reference and coverage ledger from the registry.
- [ ] Generate capability schemas consumed by the parser, editor, validator, and agent.
- [ ] Fail repository checks when generated outputs or coverage counts drift.

Exit: every reachable active input path is fully specified or explicitly blocked with evidence.

## M2 — Registry-driven deterministic engine

### M2.1 Generic parsing and semantic model

- [ ] Parse completed registry constructs into typed records while preserving concrete syntax.
- [ ] Preserve unknown or not-yet-supported records losslessly.
- [ ] Populate consistent entity identities and cross-file references.
- [ ] Replace feature-specific semantic extraction where registry metadata is sufficient.

### M2.2 Generic parameter editing

- [ ] Select parameters by canonical capability identity rather than handwritten functions.
- [ ] Support typed scalar, integer, Boolean, enum, string, optional, and repeated values.
- [ ] Produce minimal source patches with deterministic defaults and validation.
- [ ] Return actionable missing, unknown, ambiguous, and invalid-value diagnostics.

### M2.3 Generic structural editing

- [ ] Create, delete, rename, reorder, and list supported entities and records.
- [ ] Edit tables, repeated records, member lists, and referenced names.
- [ ] Support minimal reviewed changes in include files and across multiple files.
- [ ] Compute dependent updates and block destructive changes with unresolved dependents.
- [ ] Keep specialized transformations only for genuine engineering operations, not ordinary syntax edits.

### M2.4 Deterministic generation

- [ ] Build new current-syntax decks from typed analysis and mesh intent.
- [ ] Require all essential engineering choices rather than inventing them.
- [ ] Render canonical current syntax with provenance and stable digests.

Exit: ordinary supported BSAM operations are driven by registry metadata, not prompt-specific or fixture-specific code.

## M3 — Comprehensive validation and evidence

- [ ] Validate structure, types, ranges, cardinality, and required records for every supported construct.
- [ ] Validate references, dependency rules, mesh connectivity, sets, topology, and cross-feature constraints.
- [ ] Add golden no-op and minimal-patch tests for every syntax family.
- [ ] Add invalid, ambiguous, and dependency-breaking test cases.
- [ ] Add small representative fixtures across capability families; keep notch as one regression fixture.
- [ ] Add controlled executable probes where static source evidence is insufficient.
- [ ] Round-trip and executable-test a representative imported `.ele` model after an appropriate analysis template is available.

Exit: capability support is measurable, reproducible, and protected against regression.

## M4 — General agent workflow

- [ ] Generate high-level inspect, query, create, modify, validate, and run intents from the capability registry.
- [ ] Map varied language to capability identities without exposing low-level parser details.
- [ ] Persist clarification state for missing engineering inputs.
- [ ] Compose multiple deterministic operations into one reviewed plan.
- [ ] Evaluate paraphrases, ambiguity, unsupported requests, prompt injection, confirmation, and stale state across capability families.
- [ ] Re-benchmark the local model after the generic capability surface is stable.
- [ ] Complete live acceptance on representative non-notch projects.

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

1. Complete remaining M1.2 grammar gaps by parser family.
2. Complete M1.3 entity/dependency metadata.
3. Generate and verify M1.4 contracts.
4. Begin M2.1 with the first registry-driven parser family.

No user input is required until source behavior is genuinely ambiguous, an executable probe needs approval, or the M5 geometry-family gate is reached.
