# Milestones to a usable BSAM chat agent

This is the execution order. A checkbox means implemented and verified in this repository, not merely designed.

## Current product checkpoint

The project is currently expanding the deterministic BSAM engine underneath a runnable local terminal chat. It can inspect and validate a losslessly loaded source set, preview and apply bounded revision-bound edits, assemble a manually prepared Abaqus-style `.ele` mesh into an explicit template, perform the approved notch 2-to-8-ply transformation, expose those operations through the local API, show diffs and audits, and supervise isolated serial BSAM runs. The chat remains limited to registered deterministic operations and is undergoing live usability acceptance.

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

Status: in progress. Registry `0.14.0` is pinned to source commit `9954027f1c325c63d58aeb836e8fec41a4b363af` and the locally probed 2026-08-27 executable.

- [x] Inventory top-level blocks, FE cluster commands, core mesh/section records, and active BOUNDARY constructs.
- [x] Record executable invocation and completion classification.
- [x] Define lossless source-set and include-graph behavior.
- [x] Generate and validate the human-readable API reference.
- [ ] Account for every reachable active parser dispatch path.
- [ ] Complete parameter grammars, units, defaults, ranges, and repeatability.
- [ ] Record entity definitions and references for every supported construct.
- [x] Register obsolete/compatibility tokens and generate current replacements used by diagnostics.
- [x] Register the supported notch transformation's applicability, approved decisions, impacts, dependencies, tool binding, version, and runtime evidence.
- [x] Regenerate and deterministically check the coverage ledger/reference after every registry increment.

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
- [x] Resolve references while retaining unresolved, ambiguous, and type-mismatched records.
- [x] Emit deterministic duplicate, unresolved, ambiguous, and type-mismatch diagnostics.
- [x] Expose the semantic records and summary through `inspect`.
- [x] Add synthetic semantic-index unit tests.
- [x] Add a non-sensitive representative two-cluster semantic regression fixture and test.
- [x] Resolve documented cluster, constitutive assignment, boundary-condition, loading, connection, and crack dependencies used by the notch acceptance profile.

### G2.3 Validation and safe editing

- [x] Validate structural and include-graph errors.
- [x] Plan, diff, and apply narrow registered nested key/value edits.
- [x] Reject stale plans and prohibit in-place writes.
- [x] Persist digest-bound, non-overwriting audit records.
- [x] Validate complete source-set semantic dependencies during planning, review, and apply.
- [x] Add typed node creation with revision-bound preview, validation, apply, and audit.
- [x] Add topology-constrained element creation with validated connectivity references.
- [x] Add dependency-aware deletion for unreferenced nodes.
- [x] Add typed node/element-set creation and validated member-list additions.
- [x] Add dependency-aware boundary-condition rename with atomic loading-sequence reference updates.
- [x] Bound G2 editing to the supported root-deck vertical slice; defer complete CRUD and included-file editing to G3 coverage.
- [x] Guarantee byte-identical no-op output for the complete source set.

### G2.4 Import, assembly, and rendering

- [x] Use a supplied `.ele` only to establish the generic interchange structure and check in an independent reduced synthetic fixture.
- [x] Import `.ele` nodes, elements, node/element sets, generated ranges, surfaces, orientations, dimensions, and provenance into the canonical mesh model.
- [x] Define the v1 assembly contract: the validated `.ele` supplies mesh data and an existing `.in` template supplies explicit analysis data through an empty named solid cluster.
- [x] Assemble the imported canonical mesh into a revision-bound complete template source set without a language model.
- [x] Render imported mesh data as deterministic current BSAM cluster syntax.
- [x] Provide reviewed source diffs, semantic validation, mesh provenance, and stale-input protection.
- [ ] Round-trip and executable-test the representative model.

### G2.5 Run supervision

- [x] Fingerprint and preflight the executable and full source set.
- [x] Run serial BSAM in an isolated artifact directory.
- [x] Capture streams and atomically publish state.
- [x] Classify sentinel, diagnostics, timeout, and stop outcomes.
- [x] Provide concurrent `status` and idempotent controlled `stop`.
- [x] Exercise a revision-bound modified notch deck through preflight, sustained isolated execution, artifacts, and a non-escalated controlled timeout with no fatal markers.
- [x] Accept sustained nonfatal modified-notch execution with controlled stop as sufficient for the current stage; defer a full success-sentinel run per user direction.
- [ ] Add imported-model executable acceptance after a relevant analysis template is supplied.

### G2.6 Local Agent API

- [x] Implement the initial versioned loopback-only JSON tool API service.
- [x] Expose capabilities, inspection, semantic validation, mesh import, supported change preview/review/apply, run, status, and stop tools.
- [x] Enforce workspace-relative paths, source/plan digests, mutation/run confirmation, and run policy at the API boundary.
- [x] Generate strict request schemas and required response invariants from one canonical tool-contract source.
- [x] Add API schema, HTTP-envelope, workspace escape, confirmation, concurrency, and error-normalization tests.
- [x] Launch runs asynchronously through the API and test accepted/running status plus early controlled cancellation delivery.

Exit: without an LLM, a client can safely inspect, modify, validate, render, and run the supported model, and combine the accepted `.ele` fixture with explicit analysis data.

## G3 - Complete deterministic capability layer

- [ ] Implement typed support for every capability admitted by G1.
- [ ] Close all unexplained current-syntax coverage gaps.
- [ ] Add golden no-op and minimal-patch tests for each syntax family.
- [ ] Complete dependency-aware rename/delete/transform behavior.
- [ ] Add complete typed entity creation, deletion, rename, list, table, and reference edits.
- [ ] Support minimal patches in included files and multi-file reviewed changes.
- [x] Implement and verify the supported notch two-ply-to-eight-ply transformation fixture, including a 120-second nonfatal controlled executable probe.
- [x] Implement and runtime-verify revision-bound migration of the notch legacy type-9 solver body to current PARDISO syntax.
- [ ] Add representative executable probes and regression cases.
- [x] Expose the pinned versioned capability and tool-schema manifest through the API.
- [ ] Ensure unsupported or ambiguous requests fail with actionable diagnostics.

Exit: supported edits cannot leave unresolved dependent references, and the API is sufficient authority for a model-assisted client.

## G4 - Local model and first chat agent

### G4.1 Provider-neutral boundary

- [x] Implement provider-independent message, structured-output, tool-call, usage, and request-correlation types.
- [x] Implement strict local configuration without embedding credentials or model weights, including loopback enforcement for CPU-local inference.
- [x] Keep provider responses out of deterministic domain models and audit records by contract and module boundary.
- [x] Add provider request cancellation and normalized transport errors with the first concrete adapter.

### G4.2 Evaluation and policy gate

- [x] Create the initial synthetic conversations for inspection, editing, validation, and run policy.
- [x] Specify strict expected tools, arguments, confirmation refusals, and unsupported-capability behavior.
- [x] Cover path escape, raw-deck generation, unsupported capability invention, and unauthorized apply/run in the initial policy cases.
- [x] Add prompt-injection, stale-revision, render, status, stop, and final-answer evaluation cases.
- [x] Define initial pass thresholds for schema validity, tool accuracy, refusal behavior, latency, and memory.

### G4.3 Acquire and benchmark the Meta model

- [x] Select a llama.cpp-compatible Windows CPU runtime and pin its version/checksum.
- [x] Create an ignored external model directory and local configuration template.
- [x] Have the user accept the Meta license and download the approved model weights.
- [x] Record model identity, quantization, file checksum, context limit, and provenance outside the capability registry.
- [x] Bind the runtime to loopback only and disable telemetry/network model fetching.
- [x] Benchmark the small interactive candidate against the checked-in evaluation suite (failed the accuracy and refusal gates; larger-candidate decision required).
- [x] Benchmark Llama 4 Scout after the small model missed the thresholds (Scout also failed accuracy; its memory-efficient mode also failed latency).
- [x] Select Scout provisionally for hardware-aware guarded chat; it is not authorized for autonomous dispatch and remains subject to end-to-end acceptance.

### G4.4 Local adapter and orchestrator

- [x] Implement the loopback model adapter with bounded context and structured tool calls.
- [x] Validate every model response and tool argument before dispatch.
- [x] Implement the conversation state machine: understand, inspect, propose, confirm, execute, verify, explain.
- [x] Require explicit confirmation for mutations and runs according to policy.
- [x] Summarize tool results without treating model text as authoritative state.
- [x] Persist privacy-safe conversation and tool audit metadata with opt-out controls.

### G4.5 First usable chat client

- [x] Add a local `bsam-agent chat` terminal client.
- [x] Support new/resume conversation, model selection, project binding, and cancellation.
- [x] Display proposed semantic/source diffs and confirmation prompts.
- [x] Display deterministic validation/run summaries and artifact paths.
- [x] Add end-to-end scripted conversation tests with a fake provider.
- [x] Run local-model routing cases plus guarded inspect/preview/apply conversations on synthetic and approved project fixtures.
- [x] Document installation, model placement, configuration, startup, limitations, and recovery.

Exit: a user can converse locally with BSAM Agent to inspect a project, request a supported change, review and confirm it, validate it, and run BSAM; all authoritative work is performed by deterministic tools.

### G4.6 Live-chat usability stabilization

- [x] Expand deterministic inspection messages with per-cluster mesh counts, ply-like structure, sections, boundary targets, constitutive types, reference resolution, source-set status, and diagnostics.
- [x] Resolve an explicitly named, uniquely registered parameter to its owning block and construct without model guessing.
- [x] Present the model with a registry-generated high-level parameter catalog instead of requiring internal block, construct, and plan-path knowledge.
- [x] Generate safe plan and non-overwriting output defaults for a natural registered-parameter request.
- [x] Chain a successful preview to a separately confirmed apply when the user requests a new output file.
- [x] Retain the latest reviewed plan so conversational follow-ups such as `apply that change` resolve deterministically, including across resumed sessions.
- [x] Return explicit clarification guidance for missing, unknown, or context-ambiguous parameters.
- [x] Replace generic model refusals for edit requests with an actionable summary of currently supported operations.
- [x] Add regression tests for the two requests used in the first real user conversation.
- [ ] Repeat the improved inspect and parameter-change conversation with the live Scout runtime and obtain user acceptance.

Exit: the first real notch inspection and registered-parameter edit work from natural prompts, with useful engineering output and an explicit confirmation boundary.

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
