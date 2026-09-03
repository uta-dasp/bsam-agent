# Verification and trust model

## What is runnable now

The deterministic CLI and loopback HTTP API are runnable now. They support lossless source-set inspection, semantic validation, revision-bound parameter and typed FE edits, `.ele` template assembly, the approved notch 2-to-8-ply transformation, legacy type-9 to current PARDISO solver migration, reviewed plans, non-overwriting audit sidecars, isolated execution, concurrent run status, and controlled stopping. A validated llama.cpp loopback adapter and synthetic model benchmark harness are also present. Complete syntax coverage, general structural transformations, included-file editing, Gmsh generation, and the chat orchestrator are not implemented yet.

```powershell
cd "D:\Partha\BSAM\bsam agent"
$env:PYTHONPATH = "$PWD\src"
python -m bsam_agent baseline
python -m bsam_agent inspect ..\projects\notch_v1\notch_v1.in
python -m bsam_agent validate ..\projects\notch_v1\notch_v1.in
python -m unittest discover -s tests -v
```

The tests protect the pinned baseline, registry generation, byte-identical multi-file no-op rendering, original-input-directory nested include resolution, file-boundary and mixed-line-ending retention, cycle/missing/path/workspace diagnostics, include-aware run preflight, source-set-bound plan staleness and output-directory restrictions, block/command indexing, stable diagnostics, typed minimal patches, stale-plan rejection, semantic/unified diff review, no-in-place and no-audit-overwrite policies, audit/output digest binding, executable fingerprint rejection, run classification, atomic status reads, process-liveness reporting, and controlled idempotent stop requests.

## Execution smoke evidence

On 2026-08-31 the supervisor launched the pinned executable against `projects/notch_v1/notch_v1.in` using separate absolute input and output directories. A two-second timeout deliberately exercised controlled stopping. BSAM created its listing, step, and TP artifacts; the supervisor wrote the `.exit` stop request; the process ended; and the manifest classified it as `stopped` with no fatal marker and no success sentinel. This proves invocation and stop supervision, not successful analysis completion.

A second isolated smoke run on 2026-08-31 exercised concurrent external control in `runs/smoke-notch-external-stop-20260831`. While the pinned executable was active, `status` reported the durable `running` state and a live Windows process. `stop` persisted a user stop request and set BSAM's already-created `.exit` control file to 2. BSAM then exited with code zero; the owning supervisor recorded `classification: stopped`, `stop_reason: user`, `timed_out: false`, no fatal marker, and no success sentinel. This proves the concurrent status and user-stop path. It does not prove successful analysis completion.

Run artifacts are local and ignored beneath `runs/`. A successful acceptance run still requires a reviewed test case allowed to finish and classification `succeeded`.

On 2026-09-01 the approved notch transformation produced eight 0.25-thick plies, alternating 75/15-degree constitutive assignments, seven chained constitutive-3 interfaces, replicated in-plane controls, and bottom-only Z restraint. The expanded semantic index resolves all 214,824 FE, cluster, constitutive, boundary-condition, loading, connection, and crack references with zero errors. The pinned executable completed input and connection setup, produced step/TP artifacts, and ran for 120 seconds before a controlled timeout stop with exit code zero and no fatal marker. The user subsequently confirmed that the generated eight-ply deck runs correctly. This is accepted transformation evidence; the recorded automated probe remains a controlled stop rather than a success-sentinel completion.

On 2026-09-02 the Agent migrated that eight-ply deck's legacy numeric type-9 SOLVER body to explicit current PARDISO syntax, preserving 14 threads and the indefinite matrix classification. The pinned executable reported `SOLVER type=pardiso`, completed repeated symbolic/numerical factorization and solution phases, advanced through seven loading steps, and stopped cleanly after the 120-second controlled probe with exit code zero and no fatal marker. This verifies parser and sustained execution acceptance, not full analysis completion.

On 2026-09-02 Meta Llama 3.1 8B Instruct revision `0e9e39f2` was locally converted from verified safetensors to a 4,920,739,328-byte Q4_K_M GGUF with SHA-256 `12A201D3DE0AB7BE1820D6340B0F38848D639F374DCF9EABC652AF695F638210`. Pinned llama.cpp build b10621 (`v0.3.0`, commit `c1d0e7a0`) loaded the model through its Haswell CPU backend and bound only to `127.0.0.1:18080`. Exact CLI and HTTP smoke responses passed; observed generation was 11.01 tokens/second. The checked-in model profile records full provenance. This proves local inference transport, not BSAM chat acceptance.

The 16-case synthetic chat benchmark then achieved 100% top-level schema validity, 62.5% exact tool-and-argument accuracy, 33.3% policy-refusal accuracy, a 7.466-second median complete response after prefix warm-up, and an 8.847 GiB observed peak working set. It therefore failed the 95% tool accuracy and 100% refusal gates. Llama 3.1 8B remains useful as a transport baseline but is rejected as the first chat-agent model; the roadmap now requires a larger Meta candidate benchmark.

Meta Llama 4 Scout 17B-16E Instruct revision `92f3b159` was then verified and converted to a 65,359,899,808-byte Q4_K_M GGUF with SHA-256 `A5C993CAA2329F5BF0F65EA444FF40E61FD7164E240A3F73A9DF36DD711D63BF`. Exact CLI and loopback HTTP smoke responses passed at 4.8 generated tokens/second. The structured-decision benchmark achieved 100% schema validity, 68.75% exact tool-and-argument accuracy, 100% policy-refusal accuracy, 87.5% outcome accuracy, and a 10.896-second median response; the repacked runtime reached 107.933 GiB. A memory-efficient `--no-repack` native-tool trial stayed at 62.683 GiB but achieved only 81.25% schema validity, 68.75% exact tool-and-argument accuracy, 33.3% policy-refusal accuracy, and a 32.35-second median. Scout therefore fails the accuracy gate in both modes and also misses either the latency or memory gate. The llama.cpp end-token warning is benign for this result: the runtime inserts the configured `<|eot|>` token into its end-of-generation set before inference. Its built-in PEG parser did not accept Scout's native function syntax, so the adapter's tested parser accepts only a bounded AST literal subset and never evaluates model text. The checked-in profile records the full provenance and results.

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
