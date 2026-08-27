# ADR 0004: Generate current syntax only

- Status: Accepted
- Date: 2026-08-27

## Decision

Version 1 renders only canonical syntax accepted by the pinned current BSAM 2.4 parser. Obsolete syntax is not a generation target.

When an obsolete form is sufficiently understood, the importer may recognize it to produce a precise diagnostic or migration suggestion. Such recognition cannot reduce current-syntax coverage work.

## Consequences

- Current names such as `CLUSTERS` and `MATERIALS` are canonical.
- Legacy examples require classification before use as golden fixtures.
- The capability registry distinguishes canonical, recognized-obsolete, and unknown tokens.
