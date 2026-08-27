# ADR 0002: Deterministic core with optional model providers

- Status: Accepted
- Date: 2026-08-27

## Decision

Parsing, the domain model, validation, rendering, and process supervision are deterministic local components. Language models interact only through strict structured-output and tool contracts.

The first functional vertical slice must run with no model configured.

## Consequences

- Generated BSAM files remain reproducible and testable.
- Local CPU model quality does not determine correctness.
- Gemini, OpenAI, and local inference can be exchanged without changing BSAM semantics.
- The project must maintain explicit schemas and capability identifiers.
