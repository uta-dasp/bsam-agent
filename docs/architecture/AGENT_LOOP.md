# Bounded engineering-agent loop

BSAM Agent uses one orchestrator and one deterministic tool surface. The orchestrator may now
continue a task through multiple observe, plan, and act cycles; it does not grant the model a new
execution environment.

Each objective creates durable task state with completion criteria, a working plan, compact
observations, completed steps, attempt fingerprints, failures, recovery counts, and active
model/run context. After every deterministic result, the orchestrator records digest-bound evidence
and checks the objective's criteria. If evidence is missing, it may select an obvious read-only
continuation locally or ask the configured model to choose one bounded next tool.

The loop terminates when all deterministic criteria are satisfied, a clarification or confirmation
is required, a run remains in progress, policy refuses the request, a tool fails, an action would
repeat, or a step/recovery limit is reached. Model claims cannot satisfy criteria such as validation
success, model creation, comparison, or terminal run evidence.

Read-only exploration can compose model inspection, canonical semantic queries, model comparison,
run status, and bounded known-log inspection. Applying a plan, starting BSAM, and stopping a run
retain separate user-confirmation boundaries. A change-and-run objective therefore pauses once
before file creation and again before execution.

The optional knowledge boundary is defined in `bsam_agent.knowledge`. Retrieval evidence is
non-authoritative and the default implementation returns no results. A future index may provide
documentation, examples, or troubleshooting precedent, but registry support, parsing, dependency
validation, editing, and execution policy remain deterministic.

Hosted providers receive only the typed objective, bounded tool schemas, and compact observations.
Observations exclude deck text, diffs, log text, and entity identities for hosted routing. The
existing hosted-data policy and pasted-source rejection remain in force.
