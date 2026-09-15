# BSAM Agent development roadmap

This is the single authoritative implementation roadmap. It describes the target product, the
order in which capabilities should mature, and the evidence required to claim each milestone.
Checked-in code, tests, capability metadata, controlled executable probes, and acceptance records
take precedence over assumptions about current behavior.

The concrete Version 2 work items and vertical delivery order are maintained in
[V2_VERTICAL_TODOS.md](V2_VERTICAL_TODOS.md).

## Product end goal

> Build a Codex-like engineering agent for BSAM that can accept high-level natural-language
> objectives, autonomously inspect models and project files, retrieve BSAM knowledge and
> precedent, plan multi-step work, modify or generate input files through deterministic tools,
> statically validate them, smoke-test them using BSAM, diagnose failures, safely recover or ask
> for engineering decisions, run full simulations when requested, inspect results, and report
> evidence.

The end product is not merely a natural-language wrapper around deterministic commands.

> **BSAM Agent should be autonomous in reasoning, exploration, planning, and tool selection, but
> deterministic in engineering execution and validation.**

```text
LLM                     = planner and reasoner
BSAM deterministic core = trusted execution environment
RAG                     = domain knowledge and evidence
BSAM runtime            = empirical verification
```

The LLM may choose what to inspect, retrieve, compare, plan, or explain. It may not write BSAM
files directly, run arbitrary processes, waive validation, bypass workspace or authorization
policy, or silently change engineering physics to make a task succeed.

## Grounded explanation policy

Explanations must identify the authority behind each material claim:

- general conceptual explanations may use the LLM's own knowledge and must be presented as general
  background rather than verified BSAM-project facts;
- claims about the active model, project, run, or result must come from deterministic inspection;
- claims attributed to BSAM documentation or precedent must come from retrieval with provenance
  when retrieval is available;
- conclusions that combine evidence or extrapolate beyond it must be labeled as inferences;
- missing deterministic or retrieved evidence must be stated, not filled with invented model facts.

For example, “Explain the cracks” should permit inspect crack 1 → inspect crack 2 → optionally
retrieve crack documentation → synthesize. It should not fail merely because no single deterministic
query can author the final explanatory sentence.

## Task-scoped authorization

Authorization is durable task state, not a confirmation prompt attached independently to every
tool call. Initial modes are:

- `read_only`: autonomous bounded inspection and retrieval; no writes or execution;
- `edits_with_confirmation`: autonomous planning, but every physics-changing or model-changing plan
  must receive deterministic review and explicit confirmation before application;
- `execution_when_explicitly_requested`: when the objective explicitly requests smoke and/or full
  execution, that request authorizes those named executions after deterministic prerequisites pass
  and after any requested model-changing plan is reviewed and confirmed;
- `task_scoped_autonomy`: reserved for a later explicit opt-in policy; it may reduce operational
  prompts but must never waive review of physics-changing edits.

Authorization records the approved objective, operations, source/destination scope, run kinds,
limits, and revocation state. Expanding that scope requires a new user decision. A bounded stop made
necessary by timeout, cancellation, or safety policy is part of the authorized run lifecycle and
does not require a redundant confirmation. The user may revoke authorization at any time.

## Per-task engineering workspace

Each agent task should receive a contained working area for plans, intermediate source sets,
ephemeral smoke derivatives, run artifacts, retries, and compact evidence. Failed or superseded
variants stay out of the user's project. Only an explicitly selected final artifact is promoted back
through an atomic, collision-safe operation. Task cleanup must preserve required audit/provenance
records and must never delete user-owned sources.

## Status and maturity rules

Milestone status is one of:

- **Complete**: all exit criteria are backed by repository or controlled-runtime evidence.
- **Substantial**: the architecture and most required behavior exist, but an exit criterion is not
  yet proven.
- **Partial**: useful infrastructure exists, but major required behavior remains.
- **Not started**: no implementation beyond incidental prerequisites.
- **Gated**: progress requires a named external asset or engineering decision.

Capability maturity is independent of milestone status:

```text
unsupported -> implemented -> verified -> runtime_verified -> production_qualified
```

Parsing or editing support alone is never evidence that a capability is runtime-verified or
production-qualified. Full BSAM grammar coverage is not a gate for advancing the agent architecture;
unsupported and ambiguous behavior must remain explicit and fail closed.

## Current repository position

As of 2026-09-14, the repository is transitioning from **M4 into M5**. The deterministic foundation
is qualified, provider and conversational layers are substantial, and an initial bounded agent loop
can complete selected multi-step trajectories. It has not yet demonstrated general open-ended
engineering exploration or a substantial generic model transformation with smoke-test evidence.

| Milestone | Current status | Evidence summary |
| --- | --- | --- |
| M0 Deterministic foundation | Complete | Loss-preserving source sets, registry, semantics, guarded plans, validation, audit, execution supervision, and regression coverage |
| M1 Provider-neutral LLM layer | Substantial | Local llama.cpp and OpenAI Responses adapters, shared contracts, configuration, mocked transport tests, hosted-data controls; cancellation parity remains |
| M2 Conversational grounding | Substantial | Persistent active model/entity/query/output/run context and Windows/workspace path normalization; the full crack-coreference acceptance dialogue remains unproven |
| M3 Canonical engineering actions | Substantial | Canonical query mapping, capability metadata, semantic queries, model comparison, and run inspection exist; some prompt-specific routing remains |
| M4 Bounded agent loop | Substantial | Explicit bounded loop, evidence-based completion, grounded post-completion synthesis, confirmations, fingerprints, terminal states, and executable multi-step tests; general unseen-task acceptance remains |
| M5 Autonomous read-only exploration | Substantial | Model inspection, semantic query/reference traversal, comparison, validation, status, bounded logs, and contained project-file discovery/read/search can chain; unseen live acceptance remains |
| M6 Goal-oriented modification | Partial | Generic create/modify/delete/rename and plan composition exist for verified capabilities; no qualifying substantial generic transformation has been demonstrated |
| M7 Validation and execution levels | Partial | Strong static validation and controlled execution exist; a distinct deterministic smoke-test contract and output inspection do not |
| M8 Runtime diagnosis and recovery | Partial | Run states, logs, failure classification, stale-plan recovery, and safety bounds exist; diagnosis-to-repair-to-rerun is not general |
| M9 Knowledge/RAG v1 | Partial | Non-authoritative retrieval interface is defined and fails closed; no indexed corpus or retrieval backend exists |
| M10 Trusted examples | Not started | Fixtures and acceptance projects are not indexed as provenance-ranked precedents |
| M11 Troubleshooting memory | Not started | No structured verified troubleshooting store or retrieval workflow exists |
| M12 Results interpretation | Not started | Runtime artifacts are classified, but engineering result quantities are not exposed or interpreted |
| M13 VS Code interaction | Substantial | Chat, provider selection, diagnostics, forms, previews, confirmation, and run controls exist; task/evidence activity UX remains limited |
| M14 Comprehensive evaluation | Partial | Decision, conversational, and trajectory assets exist; not all trajectory specifications execute end to end |
| M15 Production hardening | Partial | Safety, audit, CI, reproducible manifests, and data controls exist; scale, compatibility, recovery, and production qualification remain |

## M0 — Preserve and qualify the deterministic foundation

**Status: Complete.**

Objective: maintain a reliable deterministic BSAM execution environment beneath every agent
capability.

Implemented and verified:

- lossless root/include source-set loading and byte-identical no-op rendering;
- semantic entities, stable identities, forward/reverse references, and source locations;
- registry/capability metadata for the active BSAM 2.4 baseline;
- deterministic inspection, focused query, planning, preview, and validation;
- supported dependency-aware create, modify, delete, rename, and composed changes;
- revision-bound plans, digests, stale-plan detection, non-overwriting apply, and audit records;
- isolated execution, durable status, timeout, and controlled stop;
- bounded stale-plan recovery, explicit unsupported-capability refusal, and workspace containment;
- representative non-trivial validation and controlled executable acceptance records.

Exit criteria remain permanent regression gates: the deterministic suite passes, no-op round trips
are preserved, includes remain source-set safe, representative models validate, and confirmation
and change-safety behavior cannot regress.

## M1 — Provider-neutral LLM layer

**Status: Substantial.**

Objective: make the reasoning model replaceable without changing the BSAM core.

Implemented:

- one provider-neutral request/response/message/tool boundary;
- local Scout/llama.cpp and OpenAI Responses adapters;
- structured decisions, usage and error normalization, provider/model/reasoning configuration;
- environment-variable credentials and `store: false` hosted requests;
- strict hosted-data minimization and refusal of apparent pasted BSAM source/mesh content;
- mocked provider conformance tests and separate live acceptance evidence.

Remaining:

- define and verify cancellation behavior across providers;
- execute the same complete synthetic agent trajectory against both providers under one harness;
- retain an explicit opt-in policy if any future hosted flow needs local-private evidence.

Exit: provider switching is configuration-only, the same synthetic task passes through either
provider, mocked OpenAI transport tests pass, and hosted providers cannot receive local-private data
without explicit policy authorization.

## M2 — Conversational grounding and workspace context

**Status: Substantial.**

Objective: ground each turn in an ongoing engineering task and workspace, not an isolated message.

Implemented task/session state includes active source and digest, recent sources and entities,
selected entity, last query, last generated output, last run, observations, unresolved decisions,
engineering assumptions, failures, plans, and step/recovery counters. Workspace-relative and
contained absolute Windows paths are normalized before deterministic execution. Follow-ups such as
“Which ones are on ply2?”, “Change that value,” “Validate the changed model,” and “Why did it fail?”
have direct regression coverage. The complete inspect → cracks → ply2 → selected-crack dialogue
also runs as one executable acceptance case without repeating the filename.

Remaining:

- broaden plural and multi-entity reference resolution without guessing;
- improve user-facing recovery whenever context exists but a narrow query cannot consume it.
- add deterministic context compaction for 20–50-step tasks, preserving user decisions, active
  source/digest, assumptions, unresolved questions, evidence references, failures, authorization,
  and the current plan while reducing verbose historical observations.

Exit: the specified multi-turn crack dialogue succeeds without repeating the filename and without
leaking internal query/parser failures.

## M3 — Natural-language intent to canonical engineering actions

**Status: Substantial.**

Objective: separate natural-language understanding, canonical engineering intent, and deterministic
execution.

Implemented:

- paraphrase normalization for capability and editable-parameter questions;
- canonical semantic query names rather than arbitrary text passed into query enums;
- entity listing/inspection and inbound/outbound reference queries through `query_model`;
- first-class `inspect_entity` and `find_references` agent intents backed by that same semantic
  query engine;
- capability descriptions, deterministic model comparison, validation diagnostics, run state, and
  bounded run-log inspection;
- a clear distinction between misunderstood/invalid arguments and unsupported capabilities.

Remaining:

- replace remaining prompt-specific keyword branches with capability-derived applicability after
  equivalent trajectory tests exist;
- measure paraphrase equivalence across both configured providers.

Exit: natural paraphrases converge on the same canonical action, arbitrary prose never reaches a
narrow deterministic enum, and unsupported capability is distinct from misunderstood wording.

## M4 — Bounded Codex-like agent loop

**Status: Substantial.**

Objective: operate an explicit observe → reason → act → observe loop until the goal is completed or
safely blocked.

Implemented:

- objective-derived working plans and deterministic completion criteria;
- compact digest-bound observations and replanning context;
- immutable task-local observation IDs and bounded working hypotheses whose supporting/refuting
  links are validated against retained deterministic evidence;
- automatic chaining of permitted read-only actions;
- provider-selected focused read-only continuations without boundary- or convergence-specific loop
  branches;
- explicit complete, clarify, confirm, refused, failed, blocked, in-progress, step-limit, and
  recovery-limit outcomes;
- maximum steps/recoveries, repeated-action detection, failed-action fingerprints, and no repeat of
  an identical failed action, including canonical-equivalent query aliases;
- an explicit evidence-exhausted stop that cannot satisfy missing deterministic criteria;
- an evidence-grounded final synthesis pass, validated against deterministic observation IDs and
  unable to change completion state;
- separate confirmation boundaries in the current baseline for applying changes, running BSAM, and
  stopping a run;
- deterministic evidence requirements for creation, validation, comparison, and terminal run state.

Remaining:

- prove completion of previously unseen multi-step objectives through model-selected composition,
  not deterministic request-specific continuation;
- characterize model behavior when several equally safe investigation paths exist.
- replace per-tool execution confirmations with audited task-scoped authorization while retaining
  mandatory review/confirmation for every physics-changing or model-changing edit;
- create a per-task engineering workspace and deterministic promotion/cleanup lifecycle;
- compact long trajectories deterministically without losing decisions, failures, provenance,
  authorization, or completion evidence.

Exit: an unseen multi-step task is completed by composing registered primitives without a hard-coded
workflow, while all terminal and safety boundaries remain deterministic.

## M5 — Autonomous read-only exploration

**Status: Partial.**

Objective: let the agent investigate engineering questions the way Codex investigates a codebase.

Available composable reads include model inspection, canonical entity/reference intents, bounded
allowed-file discovery/read/literal search, model comparison, validation diagnostics, run status,
and bounded known-log inspection. Boundary-condition investigation and failed-run diagnosis already
demonstrate multi-call read-only trajectories without confirmation.

All read-only synthesis follows the grounded explanation policy: current-model claims require
deterministic observations, documentation claims require retrieved provenance when available,
general background is labeled as such, and inferences identify their evidence.

Next work:

- add general `compare_files` only if model comparison cannot serve the tested use case;
- add diagnostics, materials, failure definitions, sections, and project-file exploration cases;
- require evidence-linked summaries and stop exploration when additional reads cannot change the
  conclusion.

Exit: an open-ended read-only question is answered through several autonomously selected tools
without asking the user to prescribe the investigation.

## M6 — Goal-oriented model modification and generation

**Status: Partial.**

Objective: achieve engineering outcomes through generic deterministic operations rather than only
single-parameter edits.

Existing primitives cover capability-gated entity create/modify/delete/rename, reference-aware
renames and retargeting for verified capabilities, multi-plan composition, source-set copying,
canonical generation for one profile, and deterministic validation. A specialized notch ply
expansion remains a regression/compatibility tool and does not satisfy this milestone’s generic
acceptance criterion.

Next work:

- add generic duplicate/copy-structure and reference-retarget primitives where registry semantics
  can define them safely;
- define a typed model-building intermediate representation and deterministic bulk/structured
  construction primitives for repeated structures, transforms, orientations, and references;
- allow compact requests such as “duplicate this ply structure six times with these transforms and
  orientations” to expand deterministically into bounded validated model operations rather than
  thousands of model-selected `create_entity` calls;
- let the agent assemble and review a multi-operation structural plan before one confirmation;
- distinguish safe structural assumptions from choices affecting materials, loading, thickness,
  stacking sequence, constitutive behavior, or other physics;
- demonstrate at least one substantial transformation that has no special-purpose workflow.

Exit: a substantial model transformation is completed with generic primitives, explicit assumptions,
focused clarification, a reviewed plan, non-overwriting apply, and deterministic validation.

## M7 — Static validation, smoke testing, and full execution

**Status: Partial.**

Objective: prove that generated or modified input is valid at three distinct evidence levels.

### Level 1: static validation

Implemented for parsing, registry constraints, semantic references, dependencies, and deterministic
diagnostics across the registered active constructs.

### Level 2: BSAM smoke test

Controlled short executions and runtime acceptance records exist, but there is no dedicated
`run_smoke_test` contract with deterministic acceptance criteria. Add one that records executable
identity/version, input digest, command/configuration, working directory, bounded stdout/stderr,
exit/timeout state, BSAM diagnostics, expected artifacts, and initialization/solver-stage evidence.
Process launch or exit code alone must never count as success.

A smoke test must not silently alter engineering physics merely to finish quickly. If BSAM requires
a modified input for bounded verification, create an explicitly marked ephemeral smoke-only
derivative inside the task workspace, record an exact source/semantic diff and provenance, and
discard or retain it according to task policy. Passing that derivative proves initialization/runtime
compatibility only; it does not prove that the original full simulation will converge.

### Level 3: full run

`run_bsam`, `get_run_status`, `inspect_run_log`, and `stop_run` provide a guarded asynchronous
foundation. Add explicit full-run intent, monitoring policy, and `inspect_run_outputs`.

If the user explicitly requested smoke and full execution in the task objective, those named runs
may proceed after prerequisite checks and confirmation of any requested model-changing plan under
`execution_when_explicitly_requested`; they do not require repeated confirmations. New execution
kinds, changed limits, changed inputs, or expanded scope require renewed authorization.

Exit: “make sure the input is correct” defaults to static validation plus a successful deterministic
smoke test, and explicitly requested full runs expose terminal and output evidence with auditable
task-scoped authorization.

## M8 — Runtime diagnosis and agentic recovery

**Status: Partial.**

Objective: observe failed smoke/full executions, diagnose them, and safely continue.

Current support includes durable manifests, bounded logs, terminal classification, input/execution
failure evidence, timeout/stop handling, failed-action fingerprints, and bounded stale-plan recovery.

Next work:

- normalize input/syntax, semantic/reference, missing-asset, environment, initialization,
  convergence/numerical, timeout, and unknown-runtime classifications;
- connect diagnosis to relevant deterministic evidence and later retrieval;
- define repairs that are demonstrably operational/structural and do not alter engineering meaning;
- implement bounded repair → validate → smoke-test/rerun trajectories;
- require clarification before changing material properties, loads, BC physics, damage parameters,
  constitutive choices, solver tolerances, mesh physics, or comparable engineering intent.

Exit: at least one controlled runtime failure is detected, classified, diagnosed, safely repaired,
revalidated, and retested through generic mechanisms.

## M9 — BSAM Knowledge/RAG v1

**Status: Partial (interface only).**

Objective: provide source-aware domain knowledge beyond the active model and registry.

The repository defines fail-closed interfaces for `search_bsam_knowledge`,
`retrieve_documentation`, `find_similar_validated_examples`, and
`search_troubleshooting_history`. No retrieval backend or indexed corpus is implemented.

Implement local/private retrieval by default using exact capability lookup, metadata filters,
keyword search, semantic search where useful, and reranking. Preserve source type, document/project,
authority, BSAM version, capability IDs, validation/runtime status, and timestamp/version.

Authority order:

```text
current deterministic model and registry
    > authoritative BSAM documentation or source
    > runtime-verified example
    > validated example
    > legacy example
    > unverified notes
```

RAG provides knowledge and precedent; the deterministic BSAM core decides what is valid.

Exit: documentation, capability, diagnostic, and trusted-example questions return source-aware
evidence without elevating retrieval above deterministic authority.

## M10 — Trusted-example retrieval and analogical model construction

**Status: Not started.**

Objective: use validated BSAM precedent as evidence for constructing new models.

Index project/example metadata including BSAM version, model type, capability set, material models,
validation, smoke/full-run status, and important structural features. Retrieved syntax and patterns
must be rechecked against the current registry and validator before use.

Exit: the agent retrieves a related trusted model, extracts relevant structure, and uses generic
deterministic operations to create a new validated model.

## M11 — Troubleshooting knowledge and engineering memory

**Status: Not started.**

Objective: retain reusable, verified troubleshooting evidence.

Store structured diagnostic/error, model context, root cause, investigation, attempted fixes,
successful and failed fixes, validation evidence, runtime evidence, and BSAM version. Historical
fixes are advisory and cannot be applied automatically when engineering context differs.

Exit: runtime diagnosis can retrieve and cite previous verified troubleshooting evidence while still
requiring present-model validation and appropriate engineering decisions.

## M12 — Results inspection and engineering interpretation

**Status: Not started.**

Objective: extend the agent loop from input preparation into simulation outcomes.

Add deterministic primitives for available result files, load/displacement histories, solver
statistics, damage/crack indicators, requested output quantities, execution summaries, and run
comparisons where the actual BSAM outputs support them. The LLM may summarize deterministic
evidence but may not fabricate unavailable quantities.

Exit: supported workflows can run a model, explain what happened, compare baseline and changed
results, and identify evidence such as damage initiation from actual outputs.

## M13 — VS Code Codex-like interaction model

**Status: Substantial.**

Objective: make the engineering-agent architecture natural to use from VS Code.

Implemented: free-form guarded chat, active-file integration, provider/model/reasoning selection,
schema-aware diagnostics and forms, reviewed diffs, confirmations, generated-file actions, and
run/status/controlled-stop controls.

Remaining:

- expose current objective, task state, plan, and terminal reason;
- show expandable tool activity and deterministic evidence without exposing internal identifiers in
  normal mode;
- distinguish model reasoning summaries, deterministic findings, assumptions, and user decisions;
- integrate smoke-test state and later retrieval/result evidence;
- add recovery/crash UX for long-running tasks.

Exit: a BSAM user can work primarily through conversational engineering objectives without knowing
tool names, capability IDs, plan IDs, or query enums.

## M14 — Comprehensive agent evaluation

**Status: Partial.**

Objective: base release acceptance on complete engineering-task success rather than routing accuracy.

Maintain three levels:

1. **Tool/decision evaluation** — schema validity, tool selection, arguments, capability invention,
   and policy behavior.
2. **Conversational evaluation** — coreference, active-model grounding, continuity, and unnecessary
   clarification.
3. **Engineering trajectory evaluation** — completion, tool order, replanning, confirmation,
   recovery, deterministic evidence, loops, unsupported actions, and final usefulness.

The repository currently has decision benchmarks, conversational tests, 19 trajectory
specifications, an evidence-based trajectory scorer, and executable tests for selected autonomous
investigation, change/validate/run boundaries, comparison, and failed-run diagnosis. JSON
specifications alone do not count as executable acceptance.

Next work is to execute every specified trajectory with controlled fixtures, then add eight-ply
construction, smoke-test diagnosis, precedent-guided construction, recovery, full-run, and results
cases.

Exit: all release-critical trajectories execute end to end and are scored on engineering outcomes,
not merely the first routing decision.

## M15 — Production hardening

**Status: Partial.**

Objective: make BSAM Agent dependable for real engineering use.

Existing foundations include workspace containment, explicit confirmation, deterministic audit
records, digest-bound plans, durable run manifests, provider data controls, regression CI, and local
acceptance evidence.

Remaining work includes large-model and long-task profiling, end-to-end cancellation, crash/task
recovery, provenance throughout retrieval and results, reproducible run environments, configurable
policy, BSAM/version compatibility, explicit privacy controls, public non-proprietary CI, proprietary
local acceptance, and opt-in-only telemetry. Apply the capability maturity ladder independently to
each operation.

Exit: release gates cover safety, correctness, resilience, provenance, compatibility, performance,
privacy, task-workspace lifecycle, authorization scope, deterministic context compaction, and both
public and proprietary acceptance evidence.

## Long-term acceptance scenario

```text
User:
"Take this two-ply notch model and create an eight-ply version.
Keep the same material system and total thickness.
Use [45/0/-45/90]s.
Preserve the loading setup.
Make a new file, validate it, smoke-test it, and if that succeeds run it.
Tell me anything you had to assume and diagnose any failures."
```

Expected autonomous trajectory:

```text
understand objective
-> inspect workspace and model
-> inspect laminate, material, and loading structure
-> retrieve documentation or examples if useful
-> identify missing engineering decisions
-> ask only when genuinely required
-> formulate a working plan
-> compose generic deterministic operations
-> produce a reviewed change and request one edit confirmation
-> apply to a non-overwriting output
-> run static validation
-> run the explicitly requested deterministic smoke test under task authorization
-> inspect runtime evidence
-> diagnose, recover, or replan within bounds
-> run the explicitly requested full simulation under the same bounded task authorization
-> inspect outputs
-> report assumptions, changes, validation, runtime evidence, and results
```

No special-purpose `make_8_ply_notch_model` or equivalent workflow may be required to pass this
scenario.

## Dependencies and recommended order

```text
M0 deterministic authority
├── M1 providers ──┐
├── M2 context ────┼──> M4 agent loop ──> M5 exploration ──┬──> M6 modification ──> M7 execution
└── M3 actions ────┘                                       └──> M9 retrieval
                                                                    ├──> M10 examples
                                                  M7 + M9 ──> M8 recovery
                                                                    └──> M11 memory
                                                        M7 ──> M12 results

M13 VS Code consumes stable capabilities incrementally.
M14 evaluation gates every milestone and release trajectory.
M15 hardening turns verified capabilities into production-qualified ones.
```

Immediate prerequisite: close M4 with a genuinely model-composed unseen-task acceptance case.

The next recommended implementation milestones are:

1. **M5 — Autonomous read-only exploration:** add bounded workspace reads/search and broaden
   semantic investigations, using executable trajectories to retire remaining M4 special cases.
2. Begin **M6 — Goal-oriented modification and generation** and **M9 — BSAM Knowledge/RAG v1** in
   parallel after M5 establishes safe general exploration. M6 proves structured transformation;
   M9 improves grounded explanations without waiting for smoke-test work.
3. **M7 — Static validation, smoke testing, and full execution:** define a first-class smoke-test
   contract, ephemeral-derivative semantics, and task-scoped execution evidence before expanding
   automatic runtime recovery.

M8 can begin with classification work during M7, but recovery cannot be accepted until the smoke
test is deterministic. M10 and M11 depend on M9 provenance. M12 depends on stable M7 output
artifacts. M13 and M14 proceed continuously as user-facing and evaluation layers over each addition.

## Previous-roadmap mapping and architectural conflicts

The previous numbering is replaced as follows:

- old M0 plus old M1–M3 deterministic specification/engine work are consolidated into new M0;
- old M4 general workflow is split across new M2–M5 and M14;
- old M5 scoped embedded mesh generation becomes gated supporting work for future M6/M12 use cases,
  not the main product sequence;
- old M6 provider/client work maps to new M1 and M13;
- new M7–M12 and M14–M15 make runtime proof, retrieval, results, evaluation, and production maturity
  explicit for the first time.

There is no fundamental conflict between the current trusted-core architecture and this end state.
The following tactical conflicts or gaps must be retired:

- the project charter still describes the LLM as a narrower workflow assistant and defers automated
  result interpretation; treat that as Version 1 history and align the charter before the next
  product-definition release;
- remaining keyword-driven and deterministic special-case routing cannot be the main mechanism for
  unseen agent tasks;
- per-tool confirmation is too granular for explicitly requested multi-step execution and must be
  replaced by bounded, revocable task-scoped authorization;
- project-root intermediate outputs need to move into a contained task workspace with explicit
  final-artifact promotion;
- long trajectories currently retain bounded recent observations but lack deterministic compaction
  of decisions, evidence, hypotheses, failures, and plans;
- specialized notch expansion may remain as a regression adapter but cannot satisfy generic M6 or
  the long-term acceptance scenario;
- individual entity CRUD and small composed plans are insufficient for large construction without a
  generic structured/bulk model-building representation;
- `run_bsam` currently combines short and full execution concerns instead of exposing a deterministic
  smoke-test contract;
- retrieval is not yet connected to an indexed, provenance-ranked knowledge service;
- runtime artifacts are not yet exposed as deterministic engineering results;
- Scout’s recorded routing accuracy does not meet the existing autonomous-agent quality gate;
- the VS Code UI is command/workflow capable but does not yet present the full task/evidence loop.

Do not weaken deterministic validation, workspace policy, confirmation, provenance, or unsupported
capability refusal to close any of these gaps.

## Deferred or supporting work

- MPI execution remains deferred until serial smoke/full-run contracts are production-qualified.
- Embedded Gmsh generation remains gated on geometry-family and trusted-mesh decisions; it should
  serve generic model construction rather than displace the agent roadmap.
- General-purpose arbitrary CAD repair, unrestricted meshing, unrestricted shell access, and direct
  model-written deck text are out of scope.
- Modification of BSAM source code is outside the BSAM input-engineering agent boundary.
