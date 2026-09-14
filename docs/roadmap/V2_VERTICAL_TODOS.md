# BSAM Agent Version 2 vertical delivery plan

This document is the actionable backlog for the Version 2 milestones in
[MILESTONES.md](MILESTONES.md). The milestone roadmap defines outcomes and authority; this plan
defines the concrete implementation order.

## Branch and promotion policy

- All Version 2 planning, code, tests, evidence, and documentation are developed on `developer`.
- Checkpoints are committed and may be pushed to `origin/developer` for review and recovery.
- Do not commit directly to or push Version 2 work onto `main`.
- Promote `developer` to `main` only after explicit user verification and approval.
- Keep each checkpoint internally consistent and preserve all deterministic safety regressions.

## Vertical delivery rule

Work is organized by usable engineering outcome, not by implementing an entire horizontal layer in
isolation. A vertical slice is complete only when its relevant path includes:

1. a representative user objective and controlled fixture;
2. deterministic domain behavior and authority boundaries;
3. versioned tool/API contracts and workspace/data policy;
4. agent planning, observations, completion criteria, and safe terminal behavior;
5. conversational continuity and persisted state where applicable;
6. confirmation before every mutation, execution, or controlled stop;
7. user-visible VS Code behavior where the capability is interactive;
8. executable trajectory evaluation, negative cases, and regression tests;
9. documentation, provenance, and reproducible acceptance evidence.

A JSON trajectory specification, isolated parser feature, UI mock, or successful process launch is
not a complete vertical slice by itself.

## Permanent foundation gates — M0

These gates apply to every slice and are not optional feature work.

- [ ] **V2-G001** Run `python tools/repository_checks.py`; generated contracts and pinned registry
  evidence must remain current.
- [ ] **V2-G002** Run the complete Python suite and affected client tests before closing each slice.
- [ ] **V2-G003** Preserve byte-identical no-op rendering and source-set/include containment tests.
- [ ] **V2-G004** Preserve plan digest, staleness, non-overwrite, confirmation, audit, validation,
  execution-isolation, and unsupported-capability regressions.
- [ ] **V2-G005** Record the capability maturity reached by the slice; never infer
  `runtime_verified` or `production_qualified` from implementation alone.
- [ ] **V2-G006** Retain sanitized acceptance evidence for controlled live-provider or BSAM-runtime
  checks without committing credentials, proprietary model contents, or raw hosted payloads.

## Slice V2-S1 — General autonomous engineering investigation

**Milestones advanced:** M1, M2, M3, M4, M5, M13, M14, M15.

**User outcome:** the agent can investigate an unfamiliar model/project question through
model-selected read-only steps, follow semantic references and allowed project evidence, and report
a grounded conclusion without the user prescribing tools.

- [ ] **V2-S1-001** Add executable acceptance fixtures for the complete crack-coreference dialogue
  and at least one unseen open-ended model investigation.
- [ ] **V2-S1-002** Define allowed project-file classes, ignored directories, symlink policy,
  maximum file/result sizes, binary detection, and hosted-provider disclosure policy.
- [ ] **V2-S1-003** Implement `list_workspace_files` with workspace containment, bounded output,
  deterministic ordering, and ignored/generated-directory handling.
- [ ] **V2-S1-004** Implement `read_allowed_text_file` with byte/line windows, encoding reporting,
  truncation evidence, and rejection of binary, disallowed, or escaping paths.
- [ ] **V2-S1-005** Implement `search_workspace` with bounded matches, file metadata, stable ordering,
  and no unrestricted regex/resource consumption.
- [ ] **V2-S1-006** Decide through tests whether general `compare_files` is needed; implement it only
  if `compare_models` plus bounded reads cannot satisfy an accepted investigation.
- [ ] **V2-S1-007** Promote `inspect_entity` and `find_references` to canonical agent intents over
  the existing semantic query engine without duplicating BSAM authority.
- [ ] **V2-S1-008** Add durable working hypotheses, supporting/refuting observation IDs, and schema
  migration to task state.
- [ ] **V2-S1-009** Let the provider select among several safe read-only continuations; remove
  request-specific deterministic continuation only after equivalent negative and trajectory tests.
- [ ] **V2-S1-010** Add exploration stop rules for exhausted evidence, repeated equivalent queries,
  context-size limits, and conclusions that require an engineering decision.
- [ ] **V2-S1-011** Add an evidence-grounded final synthesis pass whose prose cannot satisfy or
  override deterministic completion criteria.
- [ ] **V2-S1-012** Complete provider cancellation semantics and run the same synthetic
  investigation through local and mocked OpenAI providers.
- [ ] **V2-S1-013** Show current objective, plan, tool activity, evidence, assumptions, and terminal
  reason in an initial expandable VS Code task view.
- [ ] **V2-S1-014** Score tool order, evidence sufficiency, unnecessary reads/clarification,
  repetition, final usefulness, policy behavior, and provider parity in executable tests.
- [ ] **V2-S1-015** Retain sanitized acceptance evidence for one previously unseen investigation;
  close M4 only if the trajectory is model-composed rather than hard-coded.

**Exit:** M1–M4 exit criteria are closed, and M5 has one general multi-tool read-only acceptance
path spanning model semantics and allowed workspace evidence.

## Slice V2-S2 — Generic substantial model transformation

**Milestones advanced:** M2, M3, M4, M6, M13, M14, M15.

**User outcome:** the agent creates a meaningful model variant through generic deterministic
operations, asks only for unresolved engineering choices, preserves the original, and validates the
new source set.

- [ ] **V2-S2-001** Select a non-proprietary substantial transformation fixture and acceptance
  objective; the acceptance path may not call the specialized notch-expansion tool.
- [ ] **V2-S2-002** Specify the source structures, invariants, dependencies, and engineering choices
  needed by that transformation in capability metadata.
- [ ] **V2-S2-003** Add generic duplicate/copy-structure operations for the smallest capability set
  exposed by the acceptance fixture.
- [ ] **V2-S2-004** Add generic reference-retarget operations with forward/reverse dependency impact
  and fail-closed ambiguity handling.
- [ ] **V2-S2-005** Extend composed plans where needed so all independent operations share one
  source revision, one coherent preview, and one confirmation boundary.
- [ ] **V2-S2-006** Distinguish inferable structural assumptions from material, loading, thickness,
  layup, constitutive, damage, solver, and mesh-physics decisions.
- [ ] **V2-S2-007** Add focused clarification/resume tests that retain the partially constructed
  plan and do not repeat completed inspection.
- [ ] **V2-S2-008** Require plan validation and concise semantic/source impact evidence before
  confirmation.
- [ ] **V2-S2-009** Apply only to a collision-free source-set destination, validate the output, and
  compare it deterministically with the original.
- [ ] **V2-S2-010** Present assumptions, unresolved decisions, changed entities/files, diff,
  confirmation, output link, and static-validation evidence in VS Code.
- [ ] **V2-S2-011** Add executable happy, clarification, unsupported, stale, dependency-breaking,
  cancellation, and no-partial-write trajectories.
- [ ] **V2-S2-012** Demonstrate one previously unseen substantial transformation composed by the
  agent with no workflow-specific transformation tool.

**Exit:** M6 is complete for one substantial generic transformation and the resulting model has
deterministic static-validation evidence. Runtime proof is added in V2-S3.

## Slice V2-S3 — Deterministic smoke test and guarded full run

**Milestones advanced:** M4, M7, M13, M14, M15.

**User outcome:** “make sure this input is correct” produces static-validation plus meaningful BSAM
smoke-test evidence; a full run occurs only when requested and separately confirmed.

- [ ] **V2-S3-001** Define a versioned smoke-test request/result schema and deterministic acceptance
  criteria beyond process launch or exit code.
- [ ] **V2-S3-002** Define the permitted short-run configuration, timeout bounds, executable
  allowlist/fingerprint, working-directory policy, and expected initialization/solver stages.
- [ ] **V2-S3-003** Implement `run_smoke_test` in the run supervisor with isolated output, durable
  manifest, input/executable/configuration digests, stdout/stderr capture, and artifact inventory.
- [ ] **V2-S3-004** Classify smoke success from BSAM diagnostics, required stage/sentinel evidence,
  and expected artifacts; explicitly reject exit-code-only success.
- [ ] **V2-S3-005** Add `get_smoke_test_status` or unify status safely through a typed run kind
  without weakening existing asynchronous status semantics.
- [ ] **V2-S3-006** Separate canonical `run_model` intent from smoke-test intent while retaining the
  current `run_bsam` compatibility contract where needed.
- [ ] **V2-S3-007** Add completion criteria for static validation, terminal smoke evidence, and
  terminal full-run evidence.
- [ ] **V2-S3-008** Require independent confirmation for smoke execution and later full execution;
  confirmation for one may not authorize the other.
- [ ] **V2-S3-009** Add `inspect_run_outputs` inventory metadata needed for acceptance without yet
  claiming engineering interpretation.
- [ ] **V2-S3-010** Add VS Code smoke/full-run status, evidence, cancellation, and generated-artifact
  affordances.
- [ ] **V2-S3-011** Add deterministic unit/integration tests for success, fatal marker with zero
  exit, missing artifact, timeout, stop, crash, stale input, and path/collision violations.
- [ ] **V2-S3-012** Run a controlled non-proprietary smoke acceptance and retain executable version,
  digests, commands, bounded logs, artifacts, and terminal classification.
- [ ] **V2-S3-013** Complete a change → static validate → smoke confirm/run → full-run confirm/run
  trajectory with exact confirmation accounting.

**Exit:** M7 Levels 1–3 have distinct contracts and evidence; the selected generated/modified model
passes static validation and a deterministic BSAM smoke test.

## Slice V2-S4 — Source-aware BSAM knowledge retrieval

**Milestones advanced:** M1, M5, M9, M13, M14, M15.

**User outcome:** the agent can explain a construct or diagnostic with provenance-ranked local
documentation while deterministic model/registry state remains authoritative.

- [ ] **V2-S4-001** Define versioned knowledge document, chunk, provenance, authority, and retrieval
  result schemas.
- [ ] **V2-S4-002** Inventory and approve the initial local corpus: authoritative BSAM reference,
  generated registry reference, developer documentation, permitted comments, and trusted examples.
- [ ] **V2-S4-003** Implement deterministic exact capability lookup and metadata filtering before
  fuzzy retrieval.
- [ ] **V2-S4-004** Implement bounded local keyword indexing/search with reproducible corpus and
  index digests.
- [ ] **V2-S4-005** Evaluate semantic/vector search and reranking on measured cases; retain them only
  where they improve retrieval beyond exact and keyword search.
- [ ] **V2-S4-006** Implement the four existing knowledge interfaces as agent-callable read-only
  tools with citations, authority, version, and validation/runtime metadata.
- [ ] **V2-S4-007** Enforce the documented authority hierarchy and reject retrieved syntax that
  conflicts with current registry/validator evidence.
- [ ] **V2-S4-008** Add context-budget, deduplication, stale-index, missing-source, and prompt-
  injection defenses for retrieved text.
- [ ] **V2-S4-009** Keep proprietary/local chunks out of hosted requests unless an explicit data
  policy permits the exact payload.
- [ ] **V2-S4-010** Add evidence/citation rendering and source-opening actions to VS Code.
- [ ] **V2-S4-011** Add executable documentation, capability, diagnostic, conflicting-source,
  unsupported, privacy, and citation-accuracy evaluations.
- [ ] **V2-S4-012** Retain an acceptance record showing that retrieval informed an answer but did not
  override a deterministic result.

**Exit:** M9 is complete for the initial approved corpus and M5 includes documentation exploration.

## Slice V2-S5 — Runtime diagnosis and bounded safe recovery

**Milestones advanced:** M4, M7, M8, M9, M13, M14, M15.

**User outcome:** after a controlled smoke-test failure, the agent inspects evidence, classifies the
failure, retrieves relevant guidance, performs only a meaning-preserving repair when authorized,
revalidates, and retests.

- [ ] **V2-S5-001** Define stable runtime failure classes for syntax/input, semantic/reference,
  missing asset, environment, initialization, convergence/numerical, timeout, and unknown failure.
- [ ] **V2-S5-002** Map run-manifest, log, sentinel, artifact, and process evidence to those classes
  with deterministic confidence/evidence fields.
- [ ] **V2-S5-003** Select one controlled failure whose repair is operational or structural and does
  not change engineering meaning.
- [ ] **V2-S5-004** Define the allowlisted safe-repair contract and an explicit denylist for material,
  load, BC physics, damage, constitutive, solver-tolerance, and mesh-physics changes.
- [ ] **V2-S5-005** Add agent recovery planning that links failure evidence, retrieved guidance,
  proposed repair, and remaining completion criteria.
- [ ] **V2-S5-006** Route ambiguous or physics-changing recovery to one focused engineering
  clarification rather than an automatic edit.
- [ ] **V2-S5-007** Enforce failed-action fingerprints, maximum recoveries, no identical rerun after
  the same evidence, and concise safety-stop explanations.
- [ ] **V2-S5-008** Require a reviewed plan and confirmation for recovery mutations, then static
  validation and a new smoke confirmation before retest.
- [ ] **V2-S5-009** Persist the original failure, each attempt, new evidence, and terminal outcome
  across save/resume.
- [ ] **V2-S5-010** Show diagnosis, evidence, proposed repair, decisions, attempts, and retest state
  in VS Code.
- [ ] **V2-S5-011** Add executable safe-repair, user-decision, unsupported, repeated-failure,
  recovery-limit, and policy-stop trajectories.
- [ ] **V2-S5-012** Complete a controlled detect → classify → diagnose → repair → validate → retest
  acceptance without a workflow-specific fixer.

**Exit:** M8 is complete for one generic safe recovery and unsafe convergence-seeking edits remain
blocked or require explicit engineering decisions.

## Slice V2-S6 — Trusted precedent to validated construction

**Milestones advanced:** M6, M9, M10, M13, M14, M15.

**User outcome:** the agent finds a similar verified model, explains why it is relevant, extracts a
compatible pattern, and constructs a new validated model through generic deterministic operations.

- [ ] **V2-S6-001** Define trusted-example/project metadata for BSAM version, model type,
  capabilities, materials, structural features, validation, smoke test, and full-run state.
- [ ] **V2-S6-002** Build a sanitized initial example corpus with explicit authority and validation
  provenance.
- [ ] **V2-S6-003** Implement hybrid similarity using exact capabilities, metadata, keywords, and
  measured semantic retrieval where beneficial.
- [ ] **V2-S6-004** Report why each candidate is similar, which requirements differ, and what evidence
  qualifies it as precedent.
- [ ] **V2-S6-005** Re-parse and validate all adopted syntax/patterns against the current registry;
  retrieved files never become execution authority.
- [ ] **V2-S6-006** Translate selected precedent into generic deterministic create/copy/modify/
  retarget plan operations.
- [ ] **V2-S6-007** Ask for incompatible or missing engineering choices and preserve the selected
  precedent across clarification.
- [ ] **V2-S6-008** Preview, confirm, apply, statically validate, smoke-test, and compare the new model
  with the source precedent.
- [ ] **V2-S6-009** Show precedent provenance, structural reuse, differences, and verification
  evidence in VS Code.
- [ ] **V2-S6-010** Add executable relevant, misleading, obsolete-version, unverified, no-match,
  privacy, and successful-construction trajectories.
- [ ] **V2-S6-011** Retain acceptance evidence for one precedent-guided construction that uses no
  special-purpose workflow.

**Exit:** M10 is complete and precedent is proven useful without becoming authoritative.

## Slice V2-S7 — Verified troubleshooting memory

**Milestones advanced:** M8, M9, M11, M13, M14, M15.

**User outcome:** the agent recognizes a previously observed failure, retrieves the verified prior
investigation, checks present context, and uses it as evidence without blindly replaying a fix.

- [ ] **V2-S7-001** Define a versioned troubleshooting record for diagnostic, context, root cause,
  investigation, attempted fixes, failed fixes, successful fix, and validation/runtime evidence.
- [ ] **V2-S7-002** Define redaction, ownership, retention, provenance, deduplication, and immutable
  evidence-link policies.
- [ ] **V2-S7-003** Record troubleshooting outcomes only from deterministic task/run evidence and
  explicit user decisions, never from unverified model prose alone.
- [ ] **V2-S7-004** Implement exact diagnostic and contextual retrieval before semantic similarity.
- [ ] **V2-S7-005** Rank prior cases by BSAM version, capability/material/load/solver context, evidence
  strength, and successful retest status.
- [ ] **V2-S7-006** Require present-model compatibility checks before proposing a historical repair.
- [ ] **V2-S7-007** Route materially different engineering context to clarification or fresh
  diagnosis.
- [ ] **V2-S7-008** Add VS Code history/evidence display with clear current-versus-historical labels.
- [ ] **V2-S7-009** Add executable exact-repeat, near-match, misleading-match, version-mismatch,
  failed-fix, privacy, and no-history trajectories.
- [ ] **V2-S7-010** Demonstrate one diagnosis improved by verified history while current deterministic
  validation and smoke evidence remain decisive.

**Exit:** M11 is complete for the initial troubleshooting store.

## Slice V2-S8 — Deterministic results inspection and comparison

**Milestones advanced:** M7, M12, M13, M14, M15.

**User outcome:** after a completed run, the agent reports what actually happened and compares a
baseline with a changed run using deterministic output evidence.

- [ ] **V2-S8-001** Inventory supported BSAM result artifacts and pin format/version evidence for the
  first result family.
- [ ] **V2-S8-002** Define typed result provenance linking run manifest, executable, input digest,
  requested outputs, artifact digest, and parser version.
- [ ] **V2-S8-003** Implement bounded result-file inventory and format validation.
- [ ] **V2-S8-004** Implement the smallest deterministic parsers needed for selected load/
  displacement histories, solver statistics, or damage/crack evidence.
- [ ] **V2-S8-005** Expose `inspect_run_outputs`, `inspect_result_quantity`, and `compare_run_results`
  with explicit unavailable/unsupported responses.
- [ ] **V2-S8-006** Define numerical comparison tolerances and never let the LLM invent absent
  quantities or material-significance thresholds.
- [ ] **V2-S8-007** Add goal completion criteria tying requested interpretations to available typed
  evidence.
- [ ] **V2-S8-008** Add plots/tables or expandable evidence in VS Code only from deterministic result
  payloads, with source artifact links.
- [ ] **V2-S8-009** Add executable success, missing quantity, corrupt/truncated output,
  version mismatch, baseline mismatch, and unsupported-format trajectories.
- [ ] **V2-S8-010** Complete controlled “run and tell me what happened” and baseline-versus-changed
  result comparison acceptance cases.

**Exit:** M12 is complete for at least one useful BSAM result family and unavailable quantities are
reported rather than fabricated.

## Slice V2-S9 — Long-term scenario and production qualification

**Milestones advanced:** M6–M15; production closure for M13, M14, and M15.

**User outcome:** the roadmap’s complete two-ply-to-eight-ply scenario succeeds through the general
agent architecture, including evidence, safe decisions, static validation, smoke testing, optional
recovery, full execution, and result inspection.

- [ ] **V2-S9-001** Convert every release-critical JSON trajectory specification into an executable
  controlled case or explicitly remove it from release scope with rationale.
- [ ] **V2-S9-002** Freeze the long-term scenario fixture, expected engineering invariants, permitted
  assumptions, required user decisions, and deterministic result evidence.
- [ ] **V2-S9-003** Run the scenario without `preview_expand_notch_plies`, prompt-specific workflows,
  direct deck text generation, shell access, or waived validation.
- [ ] **V2-S9-004** Exercise local and OpenAI providers under their respective data policies and
  compare task success, steps, clarification, latency, usage, and failure behavior.
- [ ] **V2-S9-005** Complete the VS Code objective/task/evidence/decision/diff/run/results experience
  without requiring normal users to know tool, capability, plan, or query identifiers.
- [ ] **V2-S9-006** Add end-to-end cancellation, restart, persisted-task recovery, interrupted-run
  recovery, and idempotent resume tests.
- [ ] **V2-S9-007** Profile large source sets, long contexts, retrieval indices, result files, and
  long-running tasks; set enforced resource budgets.
- [ ] **V2-S9-008** Verify reproducible environments, executable/registry/provider compatibility,
  provenance chains, configurable policy, and local/private data controls.
- [ ] **V2-S9-009** Separate public non-proprietary CI from local proprietary/runtime acceptance and
  document both release gates.
- [ ] **V2-S9-010** Apply the maturity ladder to every exposed operation and require direct evidence
  before `runtime_verified` or `production_qualified` status.
- [ ] **V2-S9-011** Keep telemetry disabled unless an explicit policy and user opt-in are approved.
- [ ] **V2-S9-012** Produce a final sanitized acceptance report covering assumptions, decisions,
  plans, confirmation, changes, validation, retrieval, smoke/full runs, recovery, results, audit,
  performance, and provider behavior.
- [ ] **V2-S9-013** Run the complete repository, client, trajectory, provider-conformance, and local
  proprietary acceptance suites from a clean checkout.
- [ ] **V2-S9-014** Request explicit user verification of `developer`; merge/promote to `main` only
  after approval.

**Exit:** the long-term acceptance scenario passes without a special-purpose workflow, M13 and M14
are complete, and each released capability meets its declared M15 maturity level.

## Slice order and dependencies

```text
V2-S1 general investigation
  -> V2-S2 generic transformation
       -> V2-S3 smoke/full execution
            -> V2-S4 knowledge retrieval
                 -> V2-S5 runtime recovery
                      -> V2-S6 precedent construction
                           -> V2-S7 troubleshooting memory
            -> V2-S8 results inspection

V2-S1..S8 -> V2-S9 long-term acceptance and production qualification
```

V2-S4 intentionally precedes final M8 recovery acceptance even though the roadmap number is higher:
retrieval is required for the target diagnosis loop. Initial deterministic failure classification
may be developed during V2-S3. V2-S8 can proceed after V2-S3 while V2-S4–S7 are underway, provided
shared schemas and manifests remain stable.

## Progress accounting

At every checkpoint, update this file and report:

- task IDs completed, blocked, or deferred;
- milestone exit criteria advanced;
- deterministic capability/maturity changes;
- tests and controlled evidence added;
- confirmation, privacy, and workspace-safety impact;
- remaining slice blockers;
- commit pushed to `origin/developer`.

Do not report a slice complete when only its unit tests or deterministic core exist. The executable
engineering trajectory and user-visible evidence are part of the same vertical definition of done.
