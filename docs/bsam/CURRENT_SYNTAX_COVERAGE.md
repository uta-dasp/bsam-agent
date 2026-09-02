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

Registry version `0.11.0` records 13 active top-level blocks, 29 finite-element cluster command dispatches, 12 active nested BOUNDARY constructs, one runtime-verified transformation, five obsolete/compatibility tokens, and 50 local evidence records. It defines structured bodies and dependencies for core FE commands plus the complete SOLVER, UFUNCTIONS, USER, CRACK, TABLES, STATISTICAL, and externally bounded MOISTURE grammars, BOUNDARY solver scheduling, connections, loading sequences, convergence controls, and output requests. The FE include reader uses a nested unit stack, prepends the original BSAM input directory for every FILE target, and resumes the parent stream at included-file EOF. The Agent preserves this source graph while additionally blocking cycles and workspace escapes. The Agent API exposes transformation and obsolete-token rules with the remaining capability manifest. The registry generates the [BSAM 2.4 current input API reference](reference/BSAM_2_4_INPUT_API.md). The baseline transition and reproducibility qualification are recorded in [the 2026-08-31 audit](BASELINE_AUDIT_2026-08-31.md).

This is an active-dispatch inventory, not completed G1 coverage. Records marked `identified` or `partially-documented` still require exact body grammar, types, defaults, dependencies, edit impacts, and tests.

## Capability categories

| Category | Primary local entry point | Inventory status | V1 requirement |
|---|---|---|---|
| Solver and analysis control | `source/libbsam/solve_ini.f90` | Multiple solver records and boundary schedule identified | Complete |
| User functions | `source/bsam/mainf1.f`, related input routines | Entry point identified | Complete |
| Moisture | `source/bsam/mainf1.f`, related input routines | Entry point identified | Complete |
| Clusters, nodes, elements, sets, orientation | `source/libbsam/iap_ini.f90`, `source/libbsam/mod_fe_input.f90` | Dispatch inventoried; core bodies structured | Complete |
| Boundary conditions, loads, connections, convergence, output | `source/libbsam/ibn_ini.f90` and callees | Solver schedule, surface contact, VTMS convergence labels, and major record families structured | Complete |
| Constitutive controls | `source/libbsam/con_ini.f90` | Entry point identified | Complete |
| Tables | input routines reached from `source/bsam/mainf1.f` | Entry point identified | Complete |
| Statistical distributions | input routines reached from `source/bsam/mainf1.f` | Entry point identified | Complete |
| Materials | `source/libbsam/mat_ini.f90`, `material.f90`, `interface_material.f90` | Entry points identified | Complete |
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
