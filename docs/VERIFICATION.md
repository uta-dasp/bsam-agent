# Verification and trust model

## What is runnable now

The M3 negative-case audit now covers every classified diagnostic code and fails on future code/test drift. The final missing assertions exercise duplicate top-level-block warning `BSAM-W120` and nonnumeric/out-of-range BOUNDARY solver schedule `BSAM-E312`, including their level and provenance. Existing suites cover invalid syntax/value/cardinality variants, ambiguous definitions and selectors, unresolved/type-mismatched dependencies, stale plans, and dependency-blocked destructive edits.

The M3 golden/minimal-patch audit is complete. SourceSet rendering returns each bound file's original bytes and is exercised across every named active syntax family, mixed newlines, nested includes, and unknown preserved records. Direct successful generic-route tests now cover each mutable family; the final gaps add exact boundary-condition value and G-CONTROL flag spans, BOUNDARY and SCALE target spans, plus ELSET create/member-removal/delete/rename plans.

Registry 0.135.0 directly qualifies the previously implicit BOUNDARY `*GEO_NL` and `*STATUS` families. Golden tests prove byte-identical preservation, typed records, and the canonical `no restart` value; negative tests reject GEO_NL options/data, STATUS command options, multiple status rows, and unregistered status values. A registry meta-regression requires every active canonical syntax family to be named in the behavioral suite.

The first M3 closure audits all 36 registered semantic edge kinds against behavioral regression tests spanning includes, mesh connectivity, explicit/generated/derived set membership, topology, selections, assignments, and cross-feature consumers. Direct assertions now cover SECTION-to-ELSET assignment and statistical fiber-seeding-to-SECTION resolution; an out-of-range section produces the classified unresolved-reference diagnostic. A meta-regression fails if any future registered edge kind lacks a named test assertion.

Registry 0.134.0 completes M1 generated-contract enforcement. `python tools/repository_checks.py` now fails on registry invariant drift, registry/JSON-Schema root or version mismatch, stale generated reference output, committed dispatch token/source-commit/gap drift, or missing CI command binding. Windows CI runs that aggregator and the complete test suite. An available pinned adjacent source tree additionally activates exact live dispatch-audit regeneration; its absence in an isolated CI checkout is explicit rather than silently weakening committed token and zero-gap checks.

Registry 0.133.0 closes the shared consumer-route contract. Registry validation proves that parse, semantic indexing, inspection, and static validation cover all 54 active capabilities and that six grouped mutation routes exactly cover all 23 supported modify/create/delete/rename capability pairs. Runtime generic adapters require their exact route; parameter editing now fails closed for constructs whose modify operation is unsupported and directs boundary-condition identity changes to the dependency-aware rename adapter.

The deterministic CLI and loopback HTTP API are runnable now. They support lossless source-set inspection, semantic validation, revision-bound parameter and typed FE edits, composite reviewed plans, `.ele` template assembly, the approved notch 2-to-8-ply transformation, legacy type-9 to current PARDISO solver migration, non-overwriting audit sidecars, isolated execution, concurrent run status, and controlled stopping. A bounded guarded chat orchestrator, validated llama.cpp loopback adapter, and model benchmark harness are also present. Complete syntax coverage, fully general structural and included-file editing, and Gmsh generation are not implemented yet.

```powershell
cd "D:\Partha\BSAM\bsam agent"
$env:PYTHONPATH = "$PWD\src"
python -m bsam_agent baseline
python -m bsam_agent inspect ..\projects\notch_v1\notch_v1.in
python -m bsam_agent validate ..\projects\notch_v1\notch_v1.in
python -m unittest discover -s tests -v
```

The tests protect the pinned baseline, registry generation, byte-identical multi-file no-op rendering, original-input-directory nested include resolution, portable non-overwriting source-set copies, path-bound node/element creation and deletion, set insertion, set-member and unreferenced explicit-set removal, cluster BOUNDARY/LOAD/FIELD/SELECTION dependency references, exact BOUNDARY/LOAD/SECTION target edits, and empty-cluster mesh import in included FE fragments (including EOF-terminated fragments), root/include composite plans, file-boundary and mixed-line-ending retention, classified cycle/missing/path/workspace diagnostics, include-aware run preflight, source-set-bound plan staleness, block/command indexing, typed minimal and composite patches, stale-plan rejection, semantic/unified diff review, no-in-place and no-audit-overwrite policies, audit/output digest binding, executable fingerprint rejection, run classification, atomic status reads, process-liveness reporting, and controlled idempotent stop requests. Every current validation diagnostic now carries an explicit level and provenance, and summaries expose counts by both dimensions.

## Execution smoke evidence

On 2026-08-31 the supervisor launched the pinned executable against `projects/notch_v1/notch_v1.in` using separate absolute input and output directories. A two-second timeout deliberately exercised controlled stopping. BSAM created its listing, step, and TP artifacts; the supervisor wrote the `.exit` stop request; the process ended; and the manifest classified it as `stopped` with no fatal marker and no success sentinel. This proves invocation and stop supervision, not successful analysis completion.

A second isolated smoke run on 2026-08-31 exercised concurrent external control in `runs/smoke-notch-external-stop-20260831`. While the pinned executable was active, `status` reported the durable `running` state and a live Windows process. `stop` persisted a user stop request and set BSAM's already-created `.exit` control file to 2. BSAM then exited with code zero; the owning supervisor recorded `classification: stopped`, `stop_reason: user`, `timed_out: false`, no fatal marker, and no success sentinel. This proves the concurrent status and user-stop path. It does not prove successful analysis completion.

Run artifacts are local and ignored beneath `runs/`. A successful acceptance run still requires a reviewed test case allowed to finish and classification `succeeded`.

On 2026-09-01 the approved notch transformation produced eight 0.25-thick plies, alternating 75/15-degree constitutive assignments, seven chained constitutive-3 interfaces, replicated in-plane controls, and bottom-only Z restraint. The current expanded semantic index resolves all 234,969 FE, cluster-declaration, cluster-dimensions, cluster, constitutive, boundary-condition, loading, connection, output-selection, topology-operation, and crack references with zero errors. The pinned executable completed input and connection setup, produced step/TP artifacts, and ran for 120 seconds before a controlled timeout stop with exit code zero and no fatal marker. The user subsequently confirmed that the generated eight-ply deck runs correctly. This is accepted transformation evidence; the recorded automated probe remains a controlled stop rather than a success-sentinel completion.

On 2026-09-02 the Agent migrated that eight-ply deck's legacy numeric type-9 SOLVER body to explicit current PARDISO syntax, preserving 14 threads and the indefinite matrix classification. The pinned executable reported `SOLVER type=pardiso`, completed repeated symbolic/numerical factorization and solution phases, advanced through seven loading steps, and stopped cleanly after the 120-second controlled probe with exit code zero and no fatal marker. This verifies parser and sustained execution acceptance, not full analysis completion.

On 2026-09-02 Meta Llama 3.1 8B Instruct revision `0e9e39f2` was locally converted from verified safetensors to a 4,920,739,328-byte Q4_K_M GGUF with SHA-256 `12A201D3DE0AB7BE1820D6340B0F38848D639F374DCF9EABC652AF695F638210`. Pinned llama.cpp build b10621 (`v0.3.0`, commit `c1d0e7a0`) loaded the model through its Haswell CPU backend and bound only to `127.0.0.1:18080`. Exact CLI and HTTP smoke responses passed; observed generation was 11.01 tokens/second. The checked-in model profile records full provenance. This proves local inference transport, not BSAM chat acceptance.

The 16-case synthetic chat benchmark then achieved 100% top-level schema validity, 62.5% exact tool-and-argument accuracy, 33.3% policy-refusal accuracy, a 7.466-second median complete response after prefix warm-up, and an 8.847 GiB observed peak working set. It therefore failed the 95% tool accuracy and 100% refusal gates. Llama 3.1 8B remains useful as a transport baseline but is rejected as the first chat-agent model; the roadmap now requires a larger Meta candidate benchmark.

Meta Llama 4 Scout 17B-16E Instruct revision `92f3b159` was then verified and converted to a 65,359,899,808-byte Q4_K_M GGUF with SHA-256 `A5C993CAA2329F5BF0F65EA444FF40E61FD7164E240A3F73A9DF36DD711D63BF`. Exact CLI and loopback HTTP smoke responses passed at 4.8 generated tokens/second. The structured-decision benchmark achieved 100% schema validity, 68.75% exact tool-and-argument accuracy, 100% policy-refusal accuracy, 87.5% outcome accuracy, and a 10.896-second median response; the repacked runtime reached 107.933 GiB. A memory-efficient `--no-repack` native-tool trial stayed at 62.683 GiB but achieved only 81.25% schema validity, 68.75% exact tool-and-argument accuracy, 33.3% policy-refusal accuracy, and a 32.35-second median. Scout therefore fails the accuracy gate in both modes and also misses either the latency or memory gate. The llama.cpp end-token warning is benign for this result: the runtime inserts the configured `<|eot|>` token into its end-of-generation set before inference. Its built-in PEG parser did not accept Scout's native function syntax, so the adapter's tested parser accepts only a bounded AST literal subset and never evaluates model text. The checked-in profile records the full provenance and results.

Scout is nevertheless the provisional guarded-chat model after applying the workstation constraint: 512 GiB RAM makes the roughly 108 GiB faster repacked mode acceptable, while a dense 70B control is expected to reduce CPU interactivity. This does not waive the failed raw-routing result. The implemented orchestrator bounds the offered tools, validates structured decisions, permits one schema repair, enforces workspace paths in the local API, and requires `/confirm` in a separate user turn for apply, run, and stop. A live local-model smoke routed inspection of `projects/notch_v1/notch_v1.in`; the deterministic tool then reported zero errors, one compatibility warning, and 53,706 resolved references. No model-generated text was treated as the inspection result.

On 2026-09-04 Scout was re-benchmarked in the preferred repacked mode against the expanded 33-case registry `0.30.0` routing suite. It achieved 96.97% schema validity, 30.30% exact tool-and-argument accuracy, 12.5% policy-refusal accuracy, 78.79% outcome accuracy, and a 22.44-second median response; observed working set reached approximately 110.3 GiB. It again fails every autonomous-routing gate. The largest regression is on generic query arguments and guarded refusals, reinforcing that deterministic routing and policy—not raw model decisions—must remain authoritative.

On 2026-09-08 the deterministic core completed non-notch acceptance on an isolated copy of the trusted `projects/TriC_v311/TriC_v311.in` deck. Lossless inspection found 220,737 entities and 878,434 references, all resolved, with zero errors and the existing `END APPROXIMATION` compatibility warning. A dependency-aware boundary-condition identifier rename produced a one-line reviewed patch, applied to a separate deck with an audit sidecar, and independently revalidated with zero errors and the same warning. The original project remained unchanged. This verifies static inspect/review/apply/validate behavior on the 31,186,755-byte TriC deck; it does not claim executable or live-model completion.

The same repository state adds bounded composite planning: two to eight independent same-revision typed plans are individually re-derived, checked for overlap, combined, and validated behind one review and confirmation boundary. Registry-first routing now recognizes documented parameter phrases and broader create/modify/delete/rename/query verbs while preserving narrow compatibility fallbacks. Path-bound plans can insert verified nodes, elements, sets, and imported meshes into include-hosted clusters, always rendering a separate complete source set. Parameter-level edit policy gates absent optional-value insertion, isolated-record removal back to documented defaults, Boolean `DAMP` flag enable/disable, and append-only insertion plus exact occurrence replacement/removal for explicitly registered repeated-last-wins `maxiterations` and SHEFF `relative_tolerance` values. Reorder is now an explicit operation/intent status and remains unassessed for every capability, keeping ordering mutation fail-closed. Every supported parameter plan is limited to an exact span, isolated record, flag token, or registered append position and is checked against deterministic defaults plus full source-set validation; parameter failures expose stable missing, unknown, ambiguous, invalid-value, invalid-occurrence, and unsupported classifications. All 54 active constructs have enforced implemented-or-verified typed read contracts. INPUT, canonical MOISTURE key/value records, and CLUSTERS/BOUNDARY container records are selected through a shared registry-shape extractor; global CRACK declarations, numeric USER functions, every reachable cluster command, and all 12 BOUNDARY constructs also expose lossless registry-derived typed records; solver schedules, connections, cracks, and numeric functions are queryable entities. MOISTURE execution remains blocked; USER types 100 and 301 remain preservation-only. Loaded source files have workspace-stable identities, and resolved INCLUDE operations reference their targets. Repeated cross-file semantic occurrences have unique entity IDs while retaining shared keys for duplicate-definition validation. Semantic model schema 0.5 uses source-derived, occurrence-safe reference IDs, so unrelated edges cannot renumber unchanged cross-file links. Omitted cluster NAME commands retain BSAM's `noname<declaration-index>` identity and scope all child entities to it. CONSTITUTIVE types 3 and 4 resolve four or six curve-function selectors to declaration-order numeric USER identities; legacy MATERIAL type 4 resolves all twelve property selectors, legacy/keyed type 40 plus type 41 resolve their active elastic selectors, and types 15/500 resolve their compliance, phase, or viscoelastic selector to the same declaration-order identity space. Type 105 and orthotropic `*shear` resolve their G13/G12 selectors to the same numeric USER identity space. Structured polynomial parameters resolve every encoded TABLES identity. MATERIAL type-11 mixtures and type-300 interpolation rows resolve prior declaration-order material identities. Typed `*SECTION` rows resolve their cluster-local ELSET and select MATERIALS identities normally or CONSTITUTIVE identities when CONNECTION is present. MATERIAL type-800 COMPRO ownership resolves to its declaration-order cluster identity while external-file execution remains blocked. BOUNDARY connection material, constitutive, and failure selectors resolve their declaration-order identities; nodal ALL and same-row qualified set selectors expand to typed master/slave dependencies. Existing rectangular TABLES grids permit one exact finite-real cell replacement by one-based row/column while preserving axis, name, and shape bytes. Dependency-aware explicit NSET/ELSET rename updates exact resolved tokens across root/include files and blocks generated, implicit, duplicate, or unsafe definitions. Cluster-local dependency indexing and fail-closed structural edits cover TYPE, DIMENSIONS, NAME, CONSTITUTIVE assignments, BOUNDARY, LOAD, FIELD, SELECTION, SECTION, ORIENTATION, SHIFT, SCALE, FLIP, inertial TRANSFORM, BUILD, STOP, TOLERANCE, SPACING, INTEGRATION, NGEN, NCOPY, ELGEN, CRACK REGION, EXCLUSION, node, element, set, typed inline include operations, BOUNDARY cluster-selection, and output-selection relationships, including bounded generated identities. Registry generation, generated-reference checking, dispatch audit, compilation, and the full 259-test suite passed.

On 2026-09-03 a second live Scout conversation operated on an isolated copy of the approved notch deck. Scout proposed the registered `d_reduction` parameter change, the orchestrator removed its unrequested invalid `occurrence=0`, and the deterministic planner produced a valid review plan. A later apply request stopped at the confirmation boundary; only a separate `/confirm` turn wrote the changed copy and audit sidecar, with zero validation errors and one compatibility warning. The disposable four-file smoke directory was then moved to the Windows Recycle Bin. This verifies the first guarded chat path without changing the approved project files.

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

Registry 0.86.0 adds the verified `generation.mechanical-isotropic-solid-v1` profile. Its tests prove canonical repeatability, stable mesh/intent/output digests, explicit-choice rejection, mesh-target resolution, unsupported-surface refusal, confirmation enforcement, no-overwrite behavior, rollback safety, and zero-error static validation of the generated deck. This is a bounded static-generation qualification, not executable evidence for arbitrary user-selected engineering values.

Registry 0.87.0 promotes INPUT static validation after exact positive and negative tests for required presence, current type 3, one active data record, one block occurrence, exact termination, comment tolerance, typed inspection, and byte-identical no-op rendering.

Registry 0.88.0 runtime-qualifies profile 1.2.0 on a synthetic eight-node C3D8 mesh with every engineering value explicit. Controlled probes exposed and corrected three pinned-source requirements: current PARDISO accepts only explicit indefinite or unsymmetric matrices, convergence tolerances must share one record, and boundary-target node sets must be promoted to one-based node SELECTION records. The final digest-bound deck completed with exit code zero, the end-of-program sentinel, and no fatal marker. This qualifies the bounded profile and fixture, not arbitrary meshes or engineering choices.

Registry 0.89.0 corrects the runtime-evidence attribution: the successful profile run qualifies generated node `*SELECTION` records, while cluster `*FIELD` generation remains unsupported and its defective execution path remains unassessed.

Registry 0.90.0 verifies cluster `*SELECTION` static validation for required positive IDs, exact uppercase NODE/ELEMENT types, nonempty bodies, DIMENSIONS selection capacity, the source ten-named-set limit, duplicate identities, and node/element/set references.

Registry 0.91.0 corrects `.ele` DIMENSIONS semantics to BSAM's four allocation capacities: nodes, elements, selections, and sections. Import accepts zero unused slots and safe over-allocation while rejecting node/element under-allocation. Generation profile 1.3.0 derives one selection slot per imported node set and zero section slots; its controlled executable acceptance completed with exit code zero, the success sentinel, and no fatal marker.

Registry 0.92.0 verifies general `*DIMENSIONS` static validation for exactly four nonnegative integer capacities, one declaration before allocated records, and sufficient node, element, selection-ID, and section bounds, including bounded generated entities.

Registry 0.93.0 verifies cluster declaration controls: each cluster begins with one supported solid `*TYPE` and ends with `*STOP`; each `*NAME` is one non-reserved token of at most 80 characters while later names preserve BSAM's state change across includes; each `*CONSTITUTIVE` is one positive declaration-order ID and must resolve.

Registry 0.94.0 verifies `*STOP` as a command-only cluster terminator, rejects attached data and reachable commands lacking a new `*TYPE`, and retains the source-proven include-stop boundary behavior. The generated profile's final `*STOP` remains runtime-qualified.

Registry 0.95.0 verifies BOUNDARY `*NAME`: an empty body retains the indexed default, while an explicit name is one non-reserved token of at most 80 characters and must remain unique across boundary problems. The generated explicit-name form is runtime-qualified.

Registry 0.96.0 verifies BOUNDARY `*TYPE`: mechanical permits one optional registered kinematic-options row, thermal requires one finite temperature row followed by at most one options row, and unknown or excess records are rejected. Contact remains recognized syntax but produces a blocking diagnostic because the active outer dispatch stops instead of executing it.

Registry 0.97.0 verifies BOUNDARY `*G-CONTROL` as a command-line-only construct. Validation mirrors its four-character option dispatch, rejects unknown or valueless settings, enforces positive integer iterations and finite nonnegative thresholds, requires GMIN not to exceed GMAX, and blocks UPDATE unless GTHR is positive.

Registry 0.98.0 verifies BOUNDARY `*LOADING SEQUENCE`: every row has one to nine key/value pairs and exactly one header/change discriminator; static and fatigue headers require their safe explicit fields and numeric domains; change types, values, and boundary-condition references are checked; repeated blocks require balanced positive markers. Change rows for 2D and reduced fatigue remain blocked because their source allocation branches are incomplete.

Registry 0.99.0 verifies BOUNDARY `*CONNECTIONS` across penalty, nodal, and surface-contact state machines. It checks header and row cardinality, type-specific options, positive finite tolerances, positive declaration IDs, selected-cluster-qualified node sets, penalty `last` sentinels, ordered nodal selectors, and complete surface pairs. Type -21 and multiple penalty headers remain blocking because active execution does not safely dispatch them.

Registry 0.100.0 verifies cluster `*BUILD` as command-only. Any attached data record now produces a structural validation error; valid instances retain their source-located topology operation and cluster dependency.

Registry 0.101.0 verifies cluster `*FLIP`: omission retains the XY default, while an explicit command line accepts exactly one uppercase TYPE mapping from XY, YX, XZ, ZX, YZ, or ZY. Unknown options, lowercase mapping values, and attached data records are rejected.

Registry 0.102.0 verifies cluster `*TRANSFORM` command-line structure: INERTIA is mandatory, FLATTEN is optional but must carry a finite real, unknown options are rejected, and no data row may follow. FLATTEN remains parsed-but-ineffective and generic transformation generation remains blocked.

Registry 0.103.0 verifies cluster `*SPACING`: omission selects the strict zero default; explicit STRICT, RELAXED, or positive finite VALUE modes are mutually exclusive; unknown options and attached data records are rejected.

Registry 0.104.0 verifies cluster `*TOLERANCE`: TYPE is optional but must select uppercase PTOL, ITOL, FTOL, or OTOL; exactly one data record is required; and its value must be one nonnegative finite real.

Registry 0.105.0 verifies cluster `*SHIFT` and `*SCALE`: omission or ALL targets existing nodes, NSET selects one bounded name, targeting options are mutually exclusive, and exactly one three-finite-real vector is required. SCALE additionally rejects zero factors that would collapse an axis.

Registry 0.106.0 verifies cluster `*EXCLUSION`: BOX, PLANE, and PREVIOUS shape flags are mutually exclusive; INSIDE and OUTSIDE are mutually exclusive and invalid with PREVIOUS; each variant has exact finite-real width and safe geometric domains.

Registry 0.107.0 verifies cluster `*LOAD`: command-line options are rejected; each row contains exactly a node/node-set target, DOF 1–3, and finite real value; node-set names respect the source lookup buffer; and target references must resolve.

Registry 0.108.0 verifies cluster `*FIELD` input shape: VARIABLES is required once in the range 1–10; each row has one target and exactly that many finite values; target lengths and references are checked. This does not qualify execution or generation because the existing node field-state defect remains.

Registry 0.109.0 verifies cluster `*ORIENTATION`: NAME selects nodal or elemental mode, rows contain one target plus six finite vector components and finite fiber volume, and targets resolve within source buffer limits. Elemental V1/V3 must be nonzero and orthogonal within the source's `1e-8` raw-dot tolerance; nodal vectors retain the source's unchecked direct/cross-product semantics.

Registry 0.110.0 verifies `*NCOPY`: only optional NSET targeting is accepted; rows have exactly source set, count, offset, and three finite translations; source sets must exist and contain nodes; copy expansion is bounded; offsets are nonzero; and generated labels remain positive and unique.

Registry 0.111.0 verifies `*ELGEN`: TYPE is the sole required option; rows contain exactly seven integers; seeds resolve uniquely with matching topology; grid expansion is positive and bounded; shifted connectivity resolves to positive nodes; and generated element labels remain positive and unique. Zero combined offsets retain the source's skip behavior.

Registry 0.112.0 verifies `*INTEGRATION`: it accepts no options; each exact two-integer header selects one existing X3D8/Y3D8 element and 1–100000 point rows; point rows contain four finite reals and cannot be replaced by physical comments or blanks. Repeated headers retain the source's clear-and-replace behavior.

Registry 0.113.0 verifies `*SECTION`: canonical ELSET and bounded positive LAYERS are required, CONNECTION is an optional valueless flag, rows contain exactly finite positive thickness and a positive definition ID, thickness totals remain finite before normalization, and references select MATERIALS or CONSTITUTIVE according to CONNECTION.

Registry 0.114.0 verifies cluster-local `*BOUNDARY`: FORMAT is limited to source-recognized ABAQUS, LIST, or POLYNOMIAL modes; rows have exact cardinality, finite values, valid component/coordinate indices, and resolved format-appropriate targets. Polynomial individual-node targeting is rejected because the source pauses and writes through a stale index in that branch.

Registry 0.115.0 verifies `*NGEN`: canonical options, finite positive bias, exact direct/paired rows, nonempty equal-size endpoint sets, progressing increments, bounded unique positive labels, and finite derived coordinates are enforced. Arc mode requires finite noncollinear geometry and one generation row because the source's double record advance makes additional rows unsafe. NGEN and NCOPY now retain derived coordinates for validated chained generation.

Registry 0.132.0 closes engineering-clarification specification and completes M1.3. Nine machine-readable triggers bind affected capabilities, operations, conditions, and required user-approved choices. Registry validation requires exact trigger coverage for all 24 required choices in the verified generation profile and every user-approved decision in both registered transformations; broader triggers cover structured material, boundary/load, geometry, failure/fatigue, topology, and external-workflow intent without converting source-derived facts into questions.

Registry 0.131.0 closes create/delete/rename/transformation impact specification. Seven grouped policies exactly cover all eleven verified entity-operation pairs and bind each to its generic adapter, direct file/entity effects, and reverse-dependency checks. The change contract also requires complete coverage of both registered transformations and their versioned impacts. SELECTION create is corrected to unsupported because only its full-profile generation path is implemented.

Registry 0.130.0 closes the forward/reverse reference matrix. Twenty-five contracts exactly partition all 36 classified edge kinds and declare their permitted source entities, target entities, forward resolution, and reverse change policy. Registry validation rejects missing, duplicate, misclassified, or undeclared-kind contracts, while semantic construction rejects runtime source/target drift. The entity inventory is extended for structured-material attribution, implicit NODE/ELEMENT/generation sets, and implicit scheduled solvers.

Registry 0.129.0 closes the entity-output inventory. Every active construct is covered exactly once by either its registered primary entity_kind or the explicit no-primary-entity list, and six conditional output rules cover implicit clusters, generated nodes and elements, included source files, referenced structured material parameters, and loading changes. The generated reference and capability API expose the same contract.

Registry 0.128.0 establishes the dependency/decision taxonomy. The registry uniquely classifies every emitted semantic-reference kind as a deterministic structural edge or a pinned-source BSAM semantic constraint, while engineering decisions remain separate required choices with user-approved or source-derived provenance. Semantic model schema 0.6 exposes the class on every edge and fails closed for unregistered kinds; API capability discovery exposes the same contract.

Registry 0.127.0 closes the structured-material grammar item. Source consumers establish the required property groups and dimensional units for types 50, 998, and 999; missing polymorphic values are recorded as HUGE sentinels, explicit accessor defaults remain distinguished from engineering defaults, and type-50 validation admits rho/density for the active C3D8 mass path. Creation stays unsupported across conditional consumer requirements and the type-999 density/thickness ambiguity.

Registry 0.125.0 closes the CLUSTERS reverse-dependency item. Structural deletion tests now cover explicit and implicit membership, generated-range and coordinate-box membership, element connectivity, direct selection, orientation, integration, boundary/load/field targets, coordinate operations, NGEN/NCOPY sources, ELGEN seeds, section assignment, and crack-region targeting. Generated entities and ambiguous, implicit, multiply defined, or referenced structures remain fail-closed.

Registry 0.126.0 closes the material/constitutive/element compatibility item. Source-mapped solid stiffness branches cover material types 1-7, 10-12, 40-41, 50, 100-106, 200, 210, 800, and 999 across the six active solid element implementations and the B3D10-to-C3D10 alias. Semantic validation rejects parsed types 15, 300, 500, and structured interface type 998 from cluster-constitutive and direct or CONNECTION section assignments; focused tests cover every rejected family plus accepted structured bulk and J2 assignments.

Registry 0.124.0 closes NSET/ELSET validation evidence: canonical headers, required source-bounded names, mutually exclusive node-set modes, source-compatible empty sets, exact positive lookup-bounded label rows, progressing generated ranges capped before expansion, finite ordered coordinate boxes, resolved explicit/generated members, derived box membership, and explicit duplicate-member diagnostics across repeated set extensions.

Registry 0.123.0 closes explicit NODE/ELEMENT validation evidence: only registered command options are accepted; rows use exact finite coordinate or topology-specific integer connectivity shapes; labels remain within the source's fixed 1-through-999999 lookup range; duplicate node/element identities fail; connectivity resolves; and DIMENSIONS capacities cover the resulting entity counts.

Registry 0.122.0 verifies the required MATERIALS block: exact occurrence and termination; all 28 active numeric dispatches and the named type-50 spelling; no unsupported, incomplete, or unconsumed declarations; the 1500-entry source capacity; structured-key dispatch and values; legacy row widths, numeric types, source-defined ranges, order-sensitive options, and safe relative external paths. Focused tests cover every active type family and malformed envelopes, cursors, values, keys, and paths; the trusted TriC and notch decks remain free of MATERIALS diagnostics. This completes verified static validation across all 54 active constructs.

Registry 0.121.0 verifies the optional USER block: exact termination and zero sentinel; complete finite analytic records; increasing piecewise segments; monotonic inline scalar/vector splines; traversal-free type-100 path preservation; bounded type-301 sparse-matrix structure; no unconsumed records; and preserved declaration capacity.

Registry 0.120.0 verifies global CRACK declarations: exact optional-block termination; types 101, 201, and 301; bounded counts and canonical spacing; populated cluster targets; at most eight recognized options; finite, nondegenerate geometry and thresholds; exact predefined-point consumption; and fewer than 250 declarations so END CRACK remains readable.

Registry 0.119.0 verifies the optional MOISTURE block while retaining unsupported execution: exact single-block termination, canonical unique key/value records, registered settings, positive step indices, bounded converter basenames, and a relative traversal-free directory.

Registry 0.118.0 verifies the required BOUNDARY container around its 12 validated constructs: one exact block and terminator, at least one explicit `*TYPE` problem boundary, and registered nested dispatch only. The source-readable implicit first problem type is rejected under explicit-boundary Agent policy.

Registry 0.117.0 verifies the required CLUSTERS container around the fully validated FE command stream: one exact current block, at least one `*TYPE`-started cluster, registered command dispatch across root and include streams, every cluster closed by `*STOP`, and an exact current or registered compatibility terminator. Generic mesh import rejects neutral Abaqus `*SURFACE` records because BSAM has no active matching cluster dispatch.

Registry 0.116.0 verifies every cluster `*CRACK` branch. REGION requires one bounded existing ELSET or one immediate finite box/sphere/cylinder row with valid geometry; SPACING, INITIATION, and FUNCTION enforce their command-only state contracts and source parsing limits; unknown suffixes fail closed. DEFINITION is always rejected because its active reader consumes the residual command buffer as data. This closes static validation for all 29 cluster commands and all 12 nested BOUNDARY constructs.

## Planned user-facing audit path

The current deterministic slice provides `inspect`, `plan-change`, `diff`, `apply-change`, `validate`, `run`, `status`, and `stop` without a language model. Every applied change audit carries the source and output digests, plan digest, changed model paths, affected file, validation result, registered executable fingerprint, and a null run directory. Linking an edit audit to a subsequent run remains future work. This deterministic path is the reference against which local or hosted model behavior is checked.
