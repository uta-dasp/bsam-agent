# Current BSAM syntax coverage ledger

This is the top-level ledger for the BSAM input API. It prevents “all capabilities” from becoming an unverifiable claim. Detailed command and parameter records will be added during the specification milestone.

## Baseline

- Product version reported by executable: BSAM 2.4
- Local source commit: `9954027f1c325c63d58aeb836e8fec41a4b363af`
- Executable build: 2026-08-27 20:34:14, Windows Intel unlocked build
- Executable SHA-256: `7AE34D9821C6FE017897B020D615BFFA8A33F33F6D3734EBA3FD5A435788FB2A`
- Target execution: Windows serial
- Generation policy: current canonical syntax only

The updated block locator compares every requested token exactly and case-sensitively. Current generation must therefore use the registered tokens verbatim. In particular, the optional statistical block starts with `STATISTICAL` but still terminates with `END STATISTICAL DISTRIBUTIONS`. Older examples using `APPROXIMATION` or singular `MATERIAL` are evidence for diagnostics and migration messages, not generation templates.

## Initial machine-readable inventory

Registry `0.123.0` closes the explicit mesh-record limits: NODE and ELEMENT accept only registered headers, enforce exact finite row shapes, topology-specific connectivity widths, positive labels within the source's fixed 999999 lookup bound, duplicate-label diagnostics, resolved connectivity, and DIMENSIONS node/element capacity checks.

Registry `0.122.0` additionally verifies the required MATERIALS block: exact single-block termination, all 28 active numeric dispatches and the named type-50 header, source-bounded declaration capacity, complete per-type cursor consumption, structured key/value dispatch, legacy row types and widths, finite numeric values, source-defined ranges, order-sensitive options, and traversal-free external paths. Static validation is now verified for all 54 active constructs.

Registry `0.121.0` additionally verifies the optional USER block: exact envelope and disabled sentinel, bounded analytic coefficients, increasing piecewise segments, monotonic inline splines, traversal-free external-file preservation, bounded sparse-matrix structure, complete cursor consumption, and declaration capacity.

Registry `0.120.0` additionally verifies global CRACK declarations: exact optional-block termination, active types 101/201/301, bounded leading counts and spacing, populated cluster targets, up to eight recognized option rows, finite orientation/threshold/length values, exact predefined-point consumption, and the source's declaration-capacity boundary.

Registry `0.119.0` additionally verifies the optional, execution-blocked MOISTURE block: exact single-block termination, canonical unique key/value records, registered keys, positive step indices, bounded basenames, and a relative traversal-free directory.

Registry `0.118.0` additionally verifies the required BOUNDARY container: one exact block and terminator, at least one explicit `*TYPE` problem boundary, and registered nested dispatch only. The source's implicit first problem-type record remains parseable but fails closed under deterministic Agent policy because it cannot establish an explicit typed problem boundary.

Registry `0.117.0` additionally verifies the required CLUSTERS container: one exact current block, at least one `*TYPE`-started cluster, registered command dispatch across root and include streams, per-cluster `*STOP`, and exact current or registered compatibility termination. Generic mesh import now rejects neutral Abaqus `*SURFACE` records instead of emitting a command absent from BSAM's active dispatch.

Registry `0.116.0` additionally verifies every cluster `*CRACK` suffix: REGION selectors/actions and finite geometry, SPACING modes, required INITIATION location, residual-buffer-safe FUNCTION type, unknown suffix rejection, and fail-closed DEFINITION preservation. All 29 cluster commands and all 12 nested BOUNDARY constructs now have verified static validation.

Registry `0.115.0` additionally verifies `*NGEN` headers and direct, paired-set, and source-safe single-row arc variants, including bounded unique labels, finite biased coordinates, endpoint geometry, output membership, and chained use of NGEN/NCOPY-derived coordinates.

Registry `0.114.0` additionally verifies cluster-local `*BOUNDARY` FORMAT selection and exact finite ABAQUS, LIST, and POLYNOMIAL rows, including ordered component ranges, source-buffer-safe targets, polynomial cardinality, and rejection of the source's unsafe polynomial individual-node branch.

Registry `0.113.0` additionally verifies `*SECTION` ELSET/LAYERS/CONNECTION headers, source-buffer-bounded layer counts, exact positive layer rows, finite normalized thicknesses, and material-or-constitutive reference selection.

Registry `0.112.0` additionally verifies option-free `*INTEGRATION` headers, bounded positive point counts, exact finite point rows, uniquely resolved X3D8/Y3D8 targets, and source-defined last-header replacement semantics.

Registry `0.111.0` additionally verifies `*ELGEN`'s sole required TYPE option, exact seven-integer rows, uniquely resolved topology-compatible seeds, bounded positive grids, positive existing shifted connectivity, and positive unique generated labels.

Registry `0.110.0` additionally verifies `*NCOPY` optional output-set shape, exact six-field rows, existing nonempty source sets, bounded positive copy counts, nonzero offsets, finite translations, and positive generated labels.

Registry `0.109.0` additionally resolves cluster `*ORIENTATION` nodal/elemental behavior and verifies NAME selection, eight-field finite rows, source-bounded targets, references, and elemental nonzero orthogonal V1/V3 geometry without inventing nodal restrictions.

Registry `0.108.0` additionally verifies cluster `*FIELD` required VARIABLES 1–10, exact finite-real row widths, source-bounded set names, and resolved targets; generation remains unsupported and execution unassessed because the consumer-state defect is unchanged.

Registry `0.107.0` additionally verifies cluster `*LOAD` as option-free repeated three-field rows with DOF 1–3, finite values, source-bounded set names, and resolved node or node-set targets.

Registry `0.106.0` additionally verifies cluster `*EXCLUSION` shape/side exclusivity, exact BOX/PLANE/PREVIOUS record widths, finite geometry, ordered box bounds, nonzero plane normals, nonnegative bands, and positive prior-crack diameter.

Registry `0.105.0` additionally verifies cluster `*SHIFT` and `*SCALE` ALL/NSET targeting, source buffer limits, exactly one three-finite-real vector, and nonzero scale factors.

Registry `0.104.0` additionally verifies cluster `*TOLERANCE` optional uppercase TYPE selection, unknown-option rejection, exactly one value record, and a nonnegative finite real value.

Registry `0.103.0` additionally verifies cluster `*SPACING` strict default, mutually exclusive STRICT/RELAXED/VALUE modes, positive finite VALUE, unknown-option rejection, and command-only shape.

Registry `0.102.0` additionally verifies cluster `*TRANSFORM` command-line grammar: required INERTIA, optional finite-real FLATTEN, unknown-option rejection, and no attached data rows; FLATTEN remains explicitly ineffective and generation-blocked.

Registry `0.101.0` additionally verifies cluster `*FLIP` default and explicit command-line mappings, uppercase-sensitive TYPE values, rejection of unknown options, and its no-data-row contract.

Registry `0.100.0` additionally verifies cluster `*BUILD` as a command-only topology operation and rejects attached data records before source execution can consume them as commands.

Registry `0.99.0` additionally verifies all BOUNDARY `*CONNECTIONS` variants: typed headers, bounded key/value rows, positive tolerances and declaration IDs, selected-cluster-qualified sets, penalty sentinels, ordered nodal selectors, surface pairs, and blocked type -21 or duplicate-penalty execution paths.

Registry `0.98.0` additionally verifies BOUNDARY `*LOADING SEQUENCE` key/value cardinality, static and fatigue header requirements, change rows, finite numeric values, balanced positive block markers, boundary-condition references, and blocked unsafe fatigue branches.

Registry `0.97.0` additionally verifies BOUNDARY `*G-CONTROL` command-line-only shape, four-character option dispatch, value requirements, safe numeric domains, threshold ordering, and UPDATE compatibility.

Registry `0.96.0` additionally verifies BOUNDARY `*TYPE` mechanical and thermal record shape, finite thermal temperature values, the bounded kinematic flag subset, and fail-closed contact dispatch.

Registry `0.95.0` additionally verifies BOUNDARY `*NAME` default/explicit record shape, reserved-token rejection, cross-problem uniqueness, generation, and pinned-executable acceptance.

Registry `0.94.0` additionally verifies command-only `*STOP` data shape, cluster termination boundaries, generation, and pinned-executable acceptance.

Current addendum: registry `0.93.0` retains the inventory below and now contains 77 local evidence records. Its verified generation profile 1.3.0 derives correct BSAM DIMENSIONS allocation slots, emits explicit node `*SELECTION` records, excludes the defective current PARDISO `definite` spelling, and completed a digest-bound pinned-executable run with exit code zero, the success sentinel, and no fatal marker. `*SELECTION` and `*DIMENSIONS` static validation enforce their full bounded contracts. Cluster `*TYPE`, `*NAME`, and `*CONSTITUTIVE` validation now enforce declaration boundaries, cardinality, supported values, unique/reserved naming, and resolved positive constitutive IDs. The runtime evidence qualifies the generated forms, while defective `*FIELD` execution remains unassessed. The detailed `0.87.0` paragraph below remains the prior baseline narrative for the unchanged capability families.

Registry version `0.87.0` records 13 active top-level blocks, 29 finite-element cluster command dispatches, 12 active BOUNDARY constructs, one verified generation profile, two runtime-verified transformations, five obsolete/compatibility tokens, and 75 local evidence records. All 54 active constructs have enforced implemented-or-verified parse, semantic, and inspect contracts. It defines structured bodies and dependencies for all 29 FE commands and all 12 BOUNDARY constructs plus the complete SOLVER, UFUNCTIONS, USER, CRACK, CONSTITUTIVE, FAILURE, TABLES, STATISTICAL, and externally bounded MOISTURE grammars; all 28 active MATERIALS types, including positional records for the 25 legacy types and structured 50, 998, and 999 forms. INPUT, canonical MOISTURE key/value settings, and the parameterless CLUSTERS/BOUNDARY containers are selected by registry body, parameter, and entity shape and expose typed, source-located records; MOISTURE execution remains unsupported. Global CRACK declarations expose typed fixed-leading parameters and name-or-ordinal cluster dependencies while optional geometry remains inspection-only. Numeric USER declarations expose safe analytic/inline records in declaration order; external type 100 and sparse type 301 remain preservation-only. CONSTITUTIVE types 3 and 4 resolve their four or six curve-function selectors to those declaration-order numeric USER identities. Legacy MATERIAL type 4 resolves all twelve property selectors, legacy/keyed type 40 plus type 41 resolve their active elastic selectors, and types 15/500 resolve their compliance, phase, or viscoelastic selector to numeric USER identities. Type 105 and orthotropic `*shear` resolve their G13/G12 selectors to the same declaration-order numeric USER identities. Structured `poly_<table>...` parameters resolve every underscore-separated TABLES identity. MATERIAL type-11 mixtures and type-300 interpolation rows resolve prior declaration-order material identities. Typed `*SECTION` rows resolve their cluster-local ELSET and select MATERIALS identities normally or CONSTITUTIVE identities when CONNECTION is present. MATERIAL type-800 COMPRO ownership resolves to its declaration-order cluster identity while external-file execution remains blocked. Every reachable cluster command emits a uniform capability record with registry-derived parameters, defaults, and operations while preserving the original bytes. All 12 BOUNDARY constructs expose verified typed parse, semantic, and inspection records; solver schedules and connections are queryable entities, connection material/constitutive/failure selectors resolve declaration-order identities, and nodal ALL or same-row qualified set selectors expand to their master/slave dependencies. Unsafe, ineffective, fragile, or uninitialized source paths are explicitly preservation-only or blocked, including external heterogeneous/COMPRO materials, legacy order-sensitive options, BOUNDARY contact dispatch, connection type -21, unsafe fatigue combinations, automatic increment activation without explicit values, and unverified output formats. The FE include reader uses a nested unit stack, prepends the original BSAM input directory for every FILE target, and resumes the parent stream at included-file EOF. The Agent preserves this source graph while additionally blocking cycles and workspace escapes; semantic traversal expands reachable includes inline so nested fragments inherit cluster state and included `*NAME` changes persist after return, and each reachable include occurrence is a typed operation targeting its active cluster. Loaded source files have workspace-stable semantic identities, and resolved INCLUDE operations reference their target files. Repeated inclusion of one physical file now gives every semantic occurrence a unique ID while retaining shared keys for duplicate-definition validation. Semantic model schema 0.5 derives reference IDs from source, target, kind, and location so unrelated edges cannot renumber unchanged cross-file links. TYPE declarations and DIMENSIONS capacity records bind to the following normalized cluster NAME; omitted NAME commands retain BSAM's `noname<declaration-index>` identity and scope all child entities to it. Cluster CONSTITUTIVE assignments resolve declaration-order constitutive definitions. Cluster-local BOUNDARY, LOAD, FIELD, SELECTION, SECTION, ORIENTATION, SHIFT, SCALE, FLIP, inertial TRANSFORM, BUILD, STOP, TOLERANCE, SPACING, INTEGRATION, NGEN, NCOPY, ELGEN, EXCLUSION, and CRACK REGION records expose source-located operations and node, element, set, topology, state-setting, and spatial-selection relationships. BOUNDARY `*CLUSTERS` selectors expose explicit or ALL cluster dependencies with missing-name diagnostics; uniform temperature conditions inherit that active selection. BOUNDARY `*OUTPUT` data-file and aggregate selectors resolve explicit, list, and all cluster/NSET/ELSET targets and reject targets outside the active cluster scope. ALL/default coordinate operations target the current cluster; engineering-significant coordinate mutation remains unavailable. BOUNDARY/LOAD, SECTION, and SHIFT/SCALE NSET targets support capability-gated exact edits; explicit NSET/ELSET names support dependency-aware cross-file rename; and unreferenced explicit elements and sets support fail-closed deletion, including include-file changes. Bounded NGEN/NCOPY node labels and ELGEN element/connectivity identities resolve downstream references; NGEN output sets include endpoints and generated nodes, while NCOPY output sets include generated copies only. Generic coordinate-command generation remains unavailable; the verified mechanical-isotropic-solid-v1 profile performs complete mesh coordinate/capacity checks within its bounded contract and requires every engineering choice explicitly. Registered repeated-last-wins parameters support append-only insertion and exact occurrence replacement/removal with minimal reviewed patches. Existing rectangular TABLES grids support exact finite-real cell replacement by one-based row and column without changing axes, names, or shape. Reorder is exposed as an operational status but remains fail-closed because no current capability defines safe ordering semantics. The Agent API exposes generation profiles, transformation rules, and obsolete-token rules with the remaining capability manifest. The registry generates the [BSAM 2.4 current input API reference](reference/BSAM_2_4_INPUT_API.md). The baseline transition and reproducibility qualification are recorded in [the 2026-08-31 audit](BASELINE_AUDIT_2026-08-31.md). INPUT static validation is verified for exact required occurrence, type 3, single-record cardinality, and END INPUT termination.

This is an active-dispatch inventory, not completed G1 coverage. Records marked `identified` or `partially-documented` still require exact body grammar, types, defaults, dependencies, edit impacts, and tests.

Parameter-level `edit_operations` are fail-closed independently of construct maturity. Registry 0.87.0 explicitly marks convergence `maxiterations` and SHEFF `relative_tolerance` as repeated-last-wins values and permits append-only insertion plus occurrence-selected replacement/removal under their verified edit policies. It also verifies optional `maxiterations` record insertion/removal and `DAMP` flag token insertion/removal; unmarked parameter shape changes remain unavailable. Supported parameter plans patch only exact spans, isolated records, flags, or registered append positions, use deterministic defaults, revalidate the complete source set, and return stable API classifications for missing, unknown, ambiguous, invalid-value, invalid-occurrence, and unsupported edits. Explicit NSET/ELSET rename is registry-verified and updates every resolved dependent name across root and include files; generated, implicit, duplicate, or non-token-safe definitions remain blocked. Existing TABLES values support exact one-based row/column finite-real edits; axis, name, shape, insertion, and deletion changes remain unavailable. Reorder is a first-class operational status and remains unassessed for every current capability, so no ordering mutation is exposed.

The generated [primary dispatch audit](DISPATCH_AUDIT.md) independently reconciles the pinned source with the registry: all 13 active top-level initializers, 29 finite-element cluster-command prefixes, and 12 active BOUNDARY construct prefixes are accounted for with no registry/source omissions. It also records the internal `*G-C` option case and excludes commented or deprecated initialization paths. This closes primary command enumeration, not subordinate record/value grammars.

## Capability categories

| Category | Primary local entry point | Inventory status | V1 requirement |
|---|---|---|---|
| Solver and analysis control | `source/libbsam/solve_ini.f90` | Multiple solver records and boundary schedule identified | Complete |
| User functions | `source/bsam/mainf1.f`, related input routines | Entry point identified | Complete |
| Moisture | `source/bsam/mainf1.f`, related input routines | Entry point identified | Complete |
| Clusters, nodes, elements, sets, orientation | `source/libbsam/iap_ini.f90`, `source/libbsam/mod_fe_input.f90` | All 29 command grammars documented; dependency completion pending | Complete |
| Boundary conditions, loads, connections, convergence, output | `source/libbsam/ibn_ini.f90` and callees | All 12 active nested grammars documented; unsafe paths explicitly blocked | Complete |
| Constitutive controls | `source/libbsam/con_ini.f90` | Entry point identified | Complete |
| Tables | input routines reached from `source/bsam/mainf1.f` | Entry point identified | Complete |
| Statistical distributions | input routines reached from `source/bsam/mainf1.f` | Entry point identified | Complete |
| Materials | `source/libbsam/mat_ini.f90`, `material.f90`, `interface_material.f90` | All active type grammars documented; structured required sets and compatibility pending | Complete |
| Failure criteria | `source/libbsam/fai_ini.f90` | Entry point identified | Complete |
| User-defined input | input routines reached from `source/bsam/mainf1.f` | Entry point identified | Complete |
| Crack and damage input | `source/libbsam/crk_ini.f90` | Entry point identified | Complete |

“Entry point identified” is not equivalent to supported. A category becomes complete only after every reachable current construct has a registry record and tests.

## Registry record required per construct

Each block, command, option, or parameter will record:

- stable capability identifier;
- canonical spelling and hierarchy;
- value type, units if applicable, cardinality, and default behavior;
- required/optional and mutual-dependency rules;
- allowed references and cross-reference targets;
- reverse dependency/impact rules required when the construct changes;
- source file and line/routine evidence;
- example evidence when available;
- executable-probe evidence when safe and necessary;
- support state: `documented`, `implemented`, `tested`, `blocked`, or `unsupported`;
- reason and replacement for obsolete forms.

## Completeness gate

A generated capability manifest must prove that:

1. all active top-level dispatch paths are accounted for;
2. all active nested command dispatch paths are accounted for;
3. every domain type has parse, validation, and render coverage;
4. every mutable construct has direct-edit behavior and dependency tests;
5. representative combinations run against the pinned executable;
6. undocumented or ambiguous behavior is explicitly marked and never silently guessed.
