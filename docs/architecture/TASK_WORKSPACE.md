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
every staged artifact or multi-file source set by task-local ID, category, relative member paths,
media type, byte sizes, per-member and aggregate SHA-256, state, and timestamp. Promotion attempts
retain all destination paths, identical reused dependencies, the aggregate digest, outcome, and
timestamps. Version 0.3 manifests read the initial single-file 0.1 and multi-file 0.2
representations through lossless migration.

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
                         |
                         +-> selected (a later task artifact)
```

Tools may create and register plans, variants, run evidence, retries, and compact observations only
while the workspace is active or after an earlier promotion. Selecting one digest-verified artifact
freezes the candidate set until it is promoted or discarded. Discard operations can remove only
registered regular files inside the exact task root; the manifest is retained for provenance and
user-owned source files are never cleanup targets.

## Promotion contract

Only the selected regular-file artifact or complete registered source set can be promoted. Promotion
requires explicit confirmation, rechecks every member and the aggregate digest, requires an existing
workspace-contained root destination parent, rejects symlinks and destinations inside task storage,
and never overwrites an existing path. Copies are flushed to temporary files in their destination
directories and linked into final names with exclusive-create semantics; partial output is rolled
back on failure. An existing source-set member may be reused only when its bytes have the same
SHA-256 as the selected candidate member; it is recorded as reused and never rewritten. A pending
promotion is recorded before the copy; completion or failure is then recorded in the task manifest.

Chat-generated plans, refreshed retry plans, candidate source sets, run directories, and compact
observations now use the task workspace. Confirming a reviewed model edit creates and validates its
candidate there, selects the digest-bound complete source set, and promotes only that set to the
collision-free project destination. Direct deterministic API and Command Palette workflows retain
their explicitly supplied output paths.
