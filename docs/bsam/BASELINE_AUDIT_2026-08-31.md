# BSAM baseline audit — 2026-08-31

This audit replaces the earlier `7e414be55abae10e2a648bd39bcc07b4904e9edc` / `580B7AF...` knowledge baseline. It was performed only against local source, local examples, and the local executable.

## Active baseline

- Source superproject: `9954027f1c325c63d58aeb836e8fec41a4b363af` on `cracks/f/endel_eric_m`
- Source commit date: 2026-08-27
- Executable report: BSAM Version 2.4, Windows Intel, unlocked, built 2026-08-27 20:34:14
- Executable SHA-256: `7AE34D9821C6FE017897B020D615BFFA8A33F33F6D3734EBA3FD5A435788FB2A`

The source superproject was not fully clean: four first-party SHEFF submodules (`bsam_sheff_interface`, `mesh`, `simple_math`, and `utility`) contained local changes relative to the recorded submodule commits. No BSAM source was changed by this project. Because the executable may include those local submodule states, reproducibility requires both the superproject commit and executable hash. The hash is authoritative for runs.

## Input-API changes incorporated

- Top-level block lookup now uses exact, case-sensitive token comparison for every block. `SOLVER` replaces the former `SOLVE` lookup token.
- The statistical parser looks up `STATISTICAL` exactly, while its terminator remains `END STATISTICAL DISTRIBUTIONS`.
- A SOLVER block may contain multiple `*type` solver definitions (up to 50). BOUNDARY `*SOLVER` schedules 1 and 2 select solver 1 always, or solver 1 for iteration 0 and solver 2 afterward.
- BOUNDARY connections add the `surface` form, with paired master/slave node sets and SHEFF search.
- Convergence scanning increases from 11 to 12 records and adds `D_AA`. The active four-character cases now accept VTMS labels `d_reduction`, `d_min`, `d_max`, `it_opt`, and `it_restart`.
- Boundary-condition types include temperature and can reference an input-relative global/local auxiliary data file.
- Cluster names are rejected only when they exactly equal one of 13 reserved block words before the enclosing parser normalizes the name to lowercase.
- Material type 50 is reachable by numeric ID or the named `mises` form and identifies J2 flow theory with isotropic/kinematic hardening.
- Failure types 34, 35, and 36 were added to the interface-strength family (PLIGCOE, a vector Turon formulation, and direct Davila implementation respectively).
- Constitutive `*MIC` input now reads an array of values and retains both the selected MIC value and the full array.
- Many active fixed-form `.f` parser files moved to free-form `.f90`; all source evidence locators were repinned.

## Conservative boundaries

The parser exposes automatic-increment and fatigue controls whose complete safe ranges and interactions are not documented locally. `ini_dtime` and `fatigue2D3DD` also lack visible initialization in the audited initialization routine. They are registered for accurate inspection and preservation, but unconstrained generation remains blocked until controlled executable probes establish safe behavior.

Material, constitutive, failure, crack, user-function, moisture, table, and statistical entry grammars still require deeper reachable-dispatch enumeration before G1 can close. The deterministic core may begin as a lossless vertical slice without claiming full semantic support for those sections.
