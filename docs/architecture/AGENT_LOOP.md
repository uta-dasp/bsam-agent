# Bounded engineering-agent loop

BSAM Agent uses one orchestrator and one deterministic tool surface. The orchestrator may now
continue a task through multiple observe, plan, and act cycles; it does not grant the model a new
execution environment.

Each objective creates durable task state with completion criteria, a working plan, compact
observations, evidence-linked working hypotheses, completed steps, attempt fingerprints, failures,
recovery counts, task-scoped authorization, a contained task-workspace reference, and active
model/run context. For a local workspace the task directory and strict manifest are allocated before
tool routing; allocation failure blocks the task. Every deterministic observation receives an immutable
task-local ID. A model may update a bounded hypothesis only with supporting/refuting IDs present in
task context; hypotheses never count as deterministic completion evidence. Persisted pre-0.7 task
state receives deterministic observation IDs during migration. After every deterministic result,
the orchestrator records digest-bound evidence and checks the objective's criteria. If evidence is
missing, it may select an obvious read-only continuation locally or ask the configured model to
choose one bounded next tool.

Once deterministic completion criteria pass, explanation/review objectives that used model-selected
steps receive a separate structured synthesis pass. Every current-model or run finding cites a
deterministic observation ID, documentation claims cite retrieval/workspace evidence, inferences are
labeled and evidence-linked, and general background is labeled without task citations. Synthesis is
validated, repaired once if needed, and persisted with provider/model provenance. It runs only after
completion and cannot change task status or satisfy a missing criterion; failure falls back to the
completed deterministic evidence.

The loop terminates when all deterministic criteria are satisfied, a clarification or confirmation
is required, a run remains in progress, policy refuses the request, a tool fails, evidence is
exhausted, an equivalent canonical action would repeat, or a step/recovery limit is reached.
Evidence exhaustion safely blocks the task and reports the missing criteria; it cannot manufacture
completion. Model claims cannot satisfy criteria such as validation success, model creation,
comparison, or terminal run evidence.

Callers may supply one cancellation event for the whole turn. It is propagated through initial
routing, every model-selected continuation, confirmation continuation, and final synthesis. A
cancelled routing request blocks safely with `provider_cancelled`; cancellation during optional
synthesis leaves already-proven deterministic completion intact and skips repair/retry.

Trajectory evaluation compares the full deterministic path rather than only the first model
decision. It scores ordered tools and argument subsets, bounded/unnecessary reads, clarification and
confirmation behavior, policy outcomes, immutable evidence sufficiency, grounded claim kinds and
citations, recovery, final response requirements, and a provider-neutral semantic signature.

Read-only exploration can compose model inspection, canonical entity/reference queries, bounded
workspace discovery/read/search, model comparison, run status, and bounded known-log inspection.
After mandatory general observations, the provider selects among the safe continuations; the loop no
longer contains boundary- or convergence-specific continuation branches. Applying a model-changing
plan always stops for deterministic review and explicit confirmation. An objective that explicitly
requests a bounded full run or controlled stop grants one scoped, expiring authorization for that
operation, so execution may proceed after prerequisites without another confirmation. Scope
expansion is not inferred, and `/revoke` clears active authorization and any pending action. Smoke
requests remain fail-closed until the distinct smoke-test contract exists; a full run is never
silently substituted.

The optional knowledge boundary is defined in `bsam_agent.knowledge`. Retrieval evidence is
non-authoritative and the default implementation returns no results. A future index may provide
documentation, examples, or troubleshooting precedent, but registry support, parsing, dependency
validation, editing, and execution policy remain deterministic.

Hosted providers receive only the typed objective, bounded tool schemas, and compact observations.
Observations exclude deck text, diffs, log text, and entity identities for hosted routing. The
grounded synthesis pass uses the same sanitized task context. Hosted task context exposes only the
task-workspace lifecycle state, not its path or manifest. The existing hosted-data policy and
pasted-source rejection remain in force. The full task-workspace contract is documented in
[Per-task engineering workspace](TASK_WORKSPACE.md).
