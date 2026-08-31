# Verification and trust model

## What is runnable now

The deterministic CLI is runnable now. It supports baseline inspection, lossless deck inspection, conservative validation, revision-bound minimal edits to existing registered nested parameters, fresh-plan diff review, non-overwriting applied-change audit sidecars, isolated execution, concurrent run status, and controlled stopping. The local HTTP API, general semantic model, structural transformations, mesh import/generation, and model adapters are not implemented yet.

```powershell
cd "D:\Partha\BSAM\bsam agent"
$env:PYTHONPATH = "$PWD\src"
python -m bsam_agent baseline
python -m bsam_agent inspect ..\projects\notch_v1\notch_v1.in
python -m bsam_agent validate ..\projects\notch_v1\notch_v1.in
python -m unittest discover -s tests -v
```

The tests protect the pinned baseline, registry generation, byte-identical no-op rendering, block/command indexing, stable diagnostics, typed minimal patches, stale-plan rejection, semantic/unified diff review, no-in-place and no-audit-overwrite policies, audit/output digest binding, executable fingerprint rejection, run classification, atomic status reads, process-liveness reporting, and controlled idempotent stop requests.

## Execution smoke evidence

On 2026-08-31 the supervisor launched the pinned executable against `projects/notch_v1/notch_v1.in` using separate absolute input and output directories. A two-second timeout deliberately exercised controlled stopping. BSAM created its listing, step, and TP artifacts; the supervisor wrote the `.exit` stop request; the process ended; and the manifest classified it as `stopped` with no fatal marker and no success sentinel. This proves invocation and stop supervision, not successful analysis completion.

A second isolated smoke run on 2026-08-31 exercised concurrent external control in `runs/smoke-notch-external-stop-20260831`. While the pinned executable was active, `status` reported the durable `running` state and a live Windows process. `stop` persisted a user stop request and set BSAM's already-created `.exit` control file to 2. BSAM then exited with code zero; the owning supervisor recorded `classification: stopped`, `stop_reason: user`, `timed_out: false`, no fatal marker, and no success sentinel. This proves the concurrent status and user-stop path. It does not prove successful analysis completion.

Run artifacts are local and ignored beneath `runs/`. A successful acceptance run still requires a reviewed test case allowed to finish and classification `succeeded`.

## Independently verify the pinned baseline

From the agent repository:

```powershell
git -C ..\bsam20 rev-parse HEAD
(Get-FileHash -Algorithm SHA256 ..\projects\bsam20.exe).Hash
```

Compare the results with `target.source_commit` and `target.executable_sha256` in `specs/bsam-2.4/capabilities.json`. A mismatch means the specification snapshot and executable/source are no longer the same baseline.

## How to review specification claims

Every registry claim must cite local evidence. For a sampled capability:

1. Find it in `specs/bsam-2.4/capabilities.json`.
2. Follow its `evidence_ids` to the evidence index.
3. Open the local source/example locator and inspect the recorded routine or lines.
4. Check its coverage label. `identified` and `partially-documented` are not claims of complete support.
5. For `runtime-verified`, require a reproducible probe manifest, copied/synthetic input, executable fingerprint, output classification, and expected sentinel.

The generated reference is a view of the same registry; it is not independent evidence.

## Acceptance layers for implementation

| Layer | What it proves | Required evidence |
|---|---|---|
| Specification | The current syntax and dependency rule were understood | Pinned local source/docs/examples and registry record |
| Parser/renderer | Text can be imported and emitted without unintended change | Byte-identical no-op and include-graph golden tests |
| Edit planner | A requested change touches all required dependents and nothing unrelated | Semantic plan, minimal source diff, and transformation tests |
| Static validation | Structure, types, references, and topology are internally consistent | Stable diagnostic assertions and negative fixtures |
| BSAM execution | The produced deck is accepted by the pinned executable | Isolated run, explicit end sentinel, and absence of fatal diagnostics |
| Model assistance | The model selects valid tools without inventing BSAM behavior | Provider-independent evaluation set and tool/schema accuracy results |

No single successful BSAM run proves general correctness. Each supported capability needs positive, negative, round-trip, and dependency tests appropriate to its risk.

## Planned user-facing audit path

The current deterministic slice provides `inspect`, `plan-change`, `diff`, `apply-change`, `validate`, `run`, `status`, and `stop` without a language model. Every applied change audit carries the source and output digests, plan digest, changed model paths, affected file, validation result, registered executable fingerprint, and a null run directory. Linking an edit audit to a subsequent run remains future work. This deterministic path is the reference against which local or hosted model behavior is checked.
