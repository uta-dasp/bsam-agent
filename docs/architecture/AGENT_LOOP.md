# Bounded engineering-agent loop

BSAM Agent uses one orchestrator and one deterministic tool surface. The orchestrator may now
continue a task through multiple observe, plan, and act cycles; it does not grant the model a new
execution environment.

Each objective creates durable task state with completion criteria, a working plan, compact
observations, evidence-linked working hypotheses, completed steps, attempt fingerprints, failures,
recovery counts, and active model/run context. Every deterministic observation receives an immutable
task-local ID. A model may update a bounded hypothesis only with supporting/refuting IDs present in
task context; hypotheses never count as deterministic completion evidence. Persisted pre-0.7 task
state receives deterministic observation IDs during migration. After every deterministic result,
the orchestrator records digest-bound evidence and checks the objective's criteria. If evidence is
missing, it may select an obvious read-only continuation locally or ask the configured model to
choose one bounded next tool.

The loop terminates when all deterministic criteria are satisfied, a clarification or confirmation
is required, a run remains in progress, policy refuses the request, a tool fails, evidence is
exhausted, an equivalent canonical action would repeat, or a step/recovery limit is reached.
Evidence exhaustion safely blocks the task and reports the missing criteria; it cannot manufacture
completion. Model claims cannot satisfy criteria such as validation success, model creation,
comparison, or terminal run evidence.

Read-only exploration can compose model inspection, canonical entity/reference queries, bounded
workspace discovery/read/search, model comparison, run status, and bounded known-log inspection.
After mandatory general observations, the provider selects among the safe continuations; the loop no
longer contains boundary- or convergence-specific continuation branches. Applying a plan, starting
BSAM, and stopping a run retain the current confirmation boundaries pending task-scoped
authorization work.

The optional knowledge boundary is defined in `bsam_agent.knowledge`. Retrieval evidence is
non-authoritative and the default implementation returns no results. A future index may provide
documentation, examples, or troubleshooting precedent, but registry support, parsing, dependency
validation, editing, and execution policy remain deterministic.

Hosted providers receive only the typed objective, bounded tool schemas, and compact observations.
Observations exclude deck text, diffs, log text, and entity identities for hosted routing. The
existing hosted-data policy and pasted-source rejection remain in force.
