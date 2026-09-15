# Per-task engineering workspace

Every locally executed engineering task receives a private directory beneath:

```text
.bsam-agent/tasks/<conversation-prefix>-<turn>/
  task-workspace.json
  observations/
  plans/
  retries/
  runs/
  variants/
```

The task ID, root, manifest path, and lifecycle state are persisted in conversation task state. The
manifest binds the task directory to the objective digest and normalized source scope. It records
every staged artifact by task-local ID, category, relative path, media type, byte size, SHA-256,
state, and timestamp. Promotion attempts retain their destination, digest, outcome, and timestamps.

## Containment and lifecycle

Task paths must be relative, remain below the exact task root after resolution, and contain no
symlink component. The workspace boundary, task ID, manifest fields, lifecycle values, artifact
metadata, selection state, and promotion records are validated whenever the workspace is opened.
Corrupt state fails closed.

The workspace lifecycle is:

```text
active -> selected -> promoting -> promoted
   |          |
   +----------+-> discarded
```

Tools may create and register plans, variants, run evidence, retries, and compact observations only
while the workspace is active. Selecting one digest-verified artifact freezes the candidate set.
An unwanted selection may be discarded before another artifact is staged or selected. Discard
operations can remove only registered regular files inside the exact task root; the manifest is
retained for provenance and user-owned source files are never cleanup targets.

## Promotion contract

Only the selected regular-file artifact can be promoted. Promotion requires explicit confirmation,
rechecks its size and SHA-256, requires an existing workspace-contained destination parent, rejects
symlinks and destinations inside task storage, and never overwrites an existing path. The copy is
flushed to a temporary file in the destination directory and linked into its final name with
exclusive-create semantics. A pending promotion is recorded before the copy; completion or failure
is then recorded in the task manifest.

This contract establishes the safe boundary for final artifacts. Routing current plan/change/run
tools into these directories and promoting complete multi-file BSAM source sets is the next vertical
slice; until that routing is complete, existing project-output behavior remains unchanged.
