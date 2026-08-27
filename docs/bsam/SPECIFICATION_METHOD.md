# BSAM specification method

The current BSAM input API will be documented from local evidence only. No BSAM-specific syntax or implementation question is sent to an internet search engine or external model.

## Evidence order

1. Active parser and execution paths in the pinned local source.
2. Local comments and documentation adjacent to those paths.
3. Current local input examples.
4. Controlled runs of copied inputs in isolated temporary directories.
5. VTMS documentation and original VTMS export samples supplied locally.

Conflicts are recorded; lower-ranked evidence does not silently override active source behavior.

## Extraction workflow

1. Trace top-level dispatch from the main input sequence.
2. Enumerate every reachable current block and nested command.
3. Record spelling, matching rules, types, defaults, constraints, cross-references, and reverse edit impacts.
4. Link each record to its local evidence location and pinned source commit.
5. Compare against current examples and identify obsolete forms.
6. Create minimal non-destructive executable probes for ambiguous behavior.
7. Encode the result in versioned machine-readable schemas.
8. Generate human API documentation and the capability manifest from the same registry.
9. Add parser, validator, renderer, and executable-contract tests.

## Documentation rule

Machine-readable registry data is the single source for generated keyword/API reference pages. Handwritten architecture and examples may explain behavior but cannot redefine grammar.

## Source boundary

The agent repository may read the BSAM tree during specification extraction and tests. It must not edit, vendor, commit, or transmit BSAM source. References use relative evidence locators plus a source commit rather than copied implementation text.
