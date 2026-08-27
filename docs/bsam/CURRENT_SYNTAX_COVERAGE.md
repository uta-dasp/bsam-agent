# Current BSAM syntax coverage ledger

This is the top-level ledger for the BSAM input API. It prevents “all capabilities” from becoming an unverifiable claim. Detailed command and parameter records will be added during the specification milestone.

## Baseline

- Product version reported by executable: BSAM 2.4
- Local source commit: `7e414be55abae10e2a648bd39bcc07b4904e9edc`
- Executable SHA-256: `580B7AF434BF4F453B8137802246FEB292DD89A04FDB3DD54000EC9A225E146F`
- Target execution: Windows serial
- Generation policy: current canonical syntax only

Exact top-level names observed as required by the current parser include `CLUSTERS` and `MATERIALS`. Older examples using `APPROXIMATION` or singular `MATERIAL` are evidence for diagnostics and migration messages, not generation templates.

## Initial machine-readable inventory

Registry version `0.2.0` records 13 active top-level blocks, 29 finite-element cluster command dispatches, 11 active nested BOUNDARY constructs, and 27 local evidence records. It also defines structured bodies and dependencies for DIMENSIONS, NODE, ELEMENT, NSET, ELSET, INTEGRATION, ORIENTATION, and SECTION, and generates the [BSAM 2.4 current input API reference](reference/BSAM_2_4_INPUT_API.md).

This is an active-dispatch inventory, not completed G1 coverage. Records marked `identified` or `partially-documented` still require exact body grammar, types, defaults, dependencies, edit impacts, and tests.

## Capability categories

| Category | Primary local entry point | Inventory status | V1 requirement |
|---|---|---|---|
| Solver and analysis control | `source/bsam/solve_ini.f` | Entry point identified | Complete |
| User functions | `source/bsam/mainf1.f`, related input routines | Entry point identified | Complete |
| Moisture | `source/bsam/mainf1.f`, related input routines | Entry point identified | Complete |
| Clusters, nodes, elements, sets, orientation | `source/libbsam/iap_ini.f`, `source/libbsam/mod_fe_input.f90` | Dispatch inventoried; eight core bodies structured | Complete |
| Boundary conditions, loads, connections, convergence, output | `source/libbsam/ibn_ini.f` and callees | Active primary constructs inventoried | Complete |
| Constitutive controls | `source/libbsam/con_ini.f` | Entry point identified | Complete |
| Tables | input routines reached from `source/bsam/mainf1.f` | Entry point identified | Complete |
| Statistical distributions | input routines reached from `source/bsam/mainf1.f` | Entry point identified | Complete |
| Materials | `source/libbsam/mat_ini.f`, `material.f90`, `interface_material.f90` | Entry points identified | Complete |
| Failure criteria | `source/libbsam/fai_ini.f` | Entry point identified | Complete |
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
