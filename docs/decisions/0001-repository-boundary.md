# ADR 0001: Independent repository boundary

- Status: Accepted
- Date: 2026-08-27

## Decision

All BSAM Agent files live in `D:\Partha\BSAM\bsam agent`, which is its own Git repository. The existing `bsam20` source tree and `projects` data remain outside it.

The agent may reference configured external paths at runtime but must not vendor or modify BSAM source.

## Consequences

- Agent history is independent from BSAM history.
- Accidental source commits are less likely.
- Test fixtures must be intentionally curated rather than copied wholesale.
- Local path configuration will be needed for the executable, source evidence, examples, and workspaces.
