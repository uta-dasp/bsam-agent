# Milestones to a usable BSAM chat agent

This is the execution order. A checkbox means implemented and verified in this repository, not merely designed.

## Current product checkpoint

The project is currently building the deterministic BSAM engine underneath the chat experience. It can inspect and validate a losslessly loaded source set, preview and apply a narrow class of revision-bound parameter edits, show diffs and audit records, and supervise isolated serial BSAM runs. It does **not** yet understand all model entities and references, create a complete model, import VTMS, expose the full tool API, or run a chat loop.

The language model will be an optional planner and conversational interface. It will never be the BSAM parser, validator, renderer, or process supervisor.

## When the Meta model is needed

Do not download model weights during G0-G3. The first model file is acquired at **G4.3**, after all of these gates pass:

- the deterministic engine can inspect, modify, validate, render, and run the supported vertical slice;
- the local Agent tool schemas and authorization rules are executable;
- synthetic evaluation conversations and expected tool calls are checked in;
- local-model storage, licensing, checksum, loopback-only networking, and resource limits are configured.

At G4.3, the user accepts Meta's applicable license and obtains an approved quantized model. Weights stay outside Git and outside project data directories. A local configuration records only the model path, model identifier, checksum, runtime endpoint, and limits. The first benchmark should use a small interactive model before spending time on a much larger model. Model selection is an evaluation result, not an architectural dependency.

## G0 - Groundwork

Status: complete.

- [x] Create the independent Git repository and repository boundary.
- [x] Record product scope, deterministic-core architecture, and current-syntax policy.
- [x] Draft the local API lifecycle and OpenAPI contract.
- [x] Define the source-derived specification and coverage method.
- [x] Record local-data and provider policy.
- [x] Inventory the Windows development host and unresolved inputs.

Exit: documents agree on scope and no implementation decision depends on a missing manual.

## G1 - Current BSAM input specification

Status: in progress. Registry `0.3.1` is pinned to source commit `9954027f1c325c63d58aeb836e8fec41a4b363af` and the locally probed 2026-08-27 executable.

- [x] Inventory top-level blocks, FE cluster commands, core mesh/section records, and active BOUNDARY constructs.
- [x] Record executable invocation and completion classification.
- [x] Define lossless source-set and include-graph behavior.
- [x] Generate and validate the human-readable API reference.
- [ ] Account for every reachable active parser dispatch path.
- [ ] Complete parameter grammars, units, defaults, ranges, and repeatability.
- [ ] Record entity definitions and references for every supported construct.
- [ ] Complete obsolete-token diagnostics and current replacements.
- [ ] Register transformation applicability and dependency rules.
- [ ] Regenerate the coverage ledger and reference after every registry increment.

Exit: every active parser dispatch path is supported or explicitly blocked with a reason.

## G2 - Deterministic core vertical slice

Status: in progress.

### G2.1 Lossless source foundation

- [x] Implement the Python package and CLI.
- [x] Preserve original bytes and line endings.
- [x] Load recursively reachable FE include files with cycle and workspace-boundary checks.
- [x] Bind the complete source set to a stable digest.
- [x] Index top-level blocks and registered cluster commands.

### G2.2 Semantic model and reference graph - next

- [x] Define stable semantic entity and reference records with source locations.
- [x] Index explicit node, element, node-set, element-set, and section records across root and included files.
- [ ] Resolve references without discarding unresolved or ambiguous references.
- [ ] Emit deterministic duplicate, unresolved, and type-mismatch diagnostics.
- [x] Expose the semantic records and summary through `inspect`.
- [x] Add synthetic semantic-index unit tests.
- [ ] Add representative-project semantic regression fixtures and tests.

### G2.3 Validation and safe editing

- [x] Validate structural and include-graph errors.
- [x] Plan, diff, and apply narrow registered nested key/value edits.
- [x] Reject stale plans and prohibit in-place writes.
- [x] Persist digest-bound, non-overwriting audit records.
- [ ] Validate semantic dependencies before applying a change.
- [ ] Add typed creation, deletion, rename, list, table, and reference edits.
- [ ] Support minimal patches in included files and multi-file reviewed changes.
- [ ] Guarantee byte-identical no-op output for the complete source set.

### G2.4 Import, assembly, and rendering

- [ ] Obtain a real non-sensitive VTMS `.ele`/`.mtl` sample or approve a synthetic interchange fixture.
- [ ] Import VTMS nodes, elements, sets, orientations, and provenance into the canonical model.
- [ ] Define typed analysis data needed to turn the mesh into a runnable model.
- [ ] Assemble a complete canonical model without a language model.
- [ ] Render deterministic current BSAM syntax.
- [ ] Provide source and semantic render previews.
- [ ] Round-trip and executable-test the representative model.

### G2.5 Run supervision

- [x] Fingerprint and preflight the executable and full source set.
- [x] Run serial BSAM in an isolated artifact directory.
- [x] Capture streams and atomically publish state.
- [x] Classify sentinel, diagnostics, timeout, and stop outcomes.
- [x] Provide concurrent `status` and idempotent controlled `stop`.
- [ ] Add end-to-end modified-deck and imported-model acceptance runs.

### G2.6 Local Agent API

- [ ] Implement the versioned loopback-only API service.
- [ ] Expose capabilities, inspection, semantic summary, preview/apply/diff, validation, render, and run tools.
- [ ] Enforce workspace roots, revision tokens, confirmation requirements, and run policy at the API boundary.
- [ ] Generate strict request/response schemas from one source of truth.
- [ ] Add API contract, concurrency, cancellation, and error-normalization tests.

Exit: without an LLM, a client can safely inspect, modify, validate, render, and run the supported model, and combine the accepted VTMS fixture with explicit analysis data.

## G3 - Complete deterministic capability layer

- [ ] Implement typed support for every capability admitted by G1.
- [ ] Close all unexplained current-syntax coverage gaps.
- [ ] Add golden no-op and minimal-patch tests for each syntax family.
- [ ] Complete dependency-aware rename/delete/transform behavior.
- [ ] Implement and verify the supported two-ply-to-eight-ply transformation fixture.
- [ ] Add representative executable probes and regression cases.
- [ ] Expose the versioned capability manifest through the API.
- [ ] Ensure unsupported or ambiguous requests fail with actionable diagnostics.

Exit: supported edits cannot leave unresolved dependent references, and the API is sufficient authority for a model-assisted client.

## G4 - Local model and first chat agent

### G4.1 Provider-neutral boundary

- [ ] Implement provider-independent message, structured-output, tool-call, usage, cancellation, and error types.
- [ ] Implement local configuration without embedding credentials or model weights.
- [ ] Keep provider responses out of deterministic domain models and audit records.

### G4.2 Evaluation and policy gate

- [ ] Create synthetic conversations for inspection, explanation, editing, validation, rendering, running, status, and stop.
- [ ] Specify expected tools, arguments, confirmations, refusals, and final answers.
- [ ] Test prompt injection, path escape, raw-deck generation, unsupported capability invention, stale revisions, and unauthorized runs.
- [ ] Define pass thresholds for schema validity, tool accuracy, refusal behavior, latency, and memory.

### G4.3 Acquire and benchmark the Meta model

- [ ] Select a llama.cpp-compatible Windows CPU runtime and pin its version/checksum.
- [ ] Create an ignored external model directory and local configuration template.
- [ ] Have the user accept the Meta license and download the approved quantized model weights.
- [ ] Record model identity, quantization, file checksum, context limit, and provenance outside the capability registry.
- [ ] Bind the runtime to loopback only and disable telemetry/network model fetching.
- [ ] Benchmark the small interactive candidate against the checked-in evaluation suite.
- [ ] Benchmark larger candidates only if the small model misses accuracy thresholds.
- [ ] Select the smallest model meeting safety, accuracy, and latency thresholds.

### G4.4 Local adapter and orchestrator

- [ ] Implement the loopback model adapter with bounded context and structured tool calls.
- [ ] Validate every model response and tool argument before dispatch.
- [ ] Implement the conversation state machine: understand, inspect, propose, confirm, execute, verify, explain.
- [ ] Require explicit confirmation for mutations and runs according to policy.
- [ ] Summarize tool results without treating model text as authoritative state.
- [ ] Persist privacy-safe conversation and tool audit metadata with opt-out controls.

### G4.5 First usable chat client

- [ ] Add a local `bsam-agent chat` terminal client.
- [ ] Support new/resume conversation, model selection, project binding, and cancellation.
- [ ] Display proposed semantic/source diffs and confirmation prompts.
- [ ] Display validation and run progress with links/paths to artifacts.
- [ ] Add end-to-end scripted conversation tests with a fake provider.
- [ ] Run local-model acceptance conversations on synthetic and approved project fixtures.
- [ ] Document installation, model placement, configuration, startup, limitations, and recovery.

Exit: a user can converse locally with BSAM Agent to inspect a project, request a supported change, review and confirm it, validate it, and run BSAM; all authoritative work is performed by deterministic tools.

## G5 - Optional hosted providers

- [ ] Add Gemini and OpenAI adapters behind the same contract.
- [ ] Enforce payload classification and explicit provider enablement.
- [ ] Use only synthetic/sanitized data until the configured data policy permits otherwise.
- [ ] Run the same provider conformance and tool-policy suite.

## G6 - Gmsh-backed embedded mesh generation

- [ ] Pin a local Gmsh executable/library with no network dependency.
- [ ] Add typed geometry and meshing recipes, deterministic import/conversion, physical-group mapping, and quality validation.
- [ ] Generate current-syntax clusters with provenance and trusted equivalence tests.

## G7 - VS Code client

- [ ] Build a thin TypeScript client of the local API.
- [ ] Add schema-aware diagnostics, model forms, chat, reviewed diffs, run controls, and status.
- [ ] Package it with Windows setup documentation while retaining CLI parity.

## Later

- MPI supervision
- result interpretation and reporting
- broader mesh generation
- controlled obsolete-input migration
