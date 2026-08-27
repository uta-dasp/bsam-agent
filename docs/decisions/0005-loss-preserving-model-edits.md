# ADR 0005: Loss-preserving, dependency-aware model edits

- Status: Accepted
- Date: 2026-08-27

## Decision

Modification of existing current-syntax input files is a Version 1 capability. Imported decks retain both a lossless concrete syntax tree/include graph and a typed semantic model with dependencies.

All edits use revision-bound preview/apply plans. Direct parameter edits patch the smallest safe source region. Structural transformations operate on the semantic model, update dependent entities and references, and then produce minimal source patches. Original files are not overwritten by default.

## Consequences

- A normalized abstract syntax tree alone is insufficient.
- Include files, comments, ordering, whitespace, and unknown constructs must be retained.
- Ply-count changes require documented transformation algorithms and applicability checks.
- Ambiguous engineering intent must produce explicit required inputs rather than inferred values.
- Diff, optimistic concurrency, dependency validation, and transformation tests become core requirements rather than editor-only features.
