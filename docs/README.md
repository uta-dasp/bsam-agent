# Documentation index

## Product authority

- [Project charter](PROJECT_CHARTER.md) — product goal, scope, and completion criteria.
- [Development roadmap](roadmap/MILESTONES.md) — authoritative milestones and current work.
- [Verification model](VERIFICATION.md) — evidence and acceptance requirements.
- [Open inputs](OPEN_INPUTS.md) — unresolved user decisions and recorded assumptions.

## BSAM language authority

- [Specification method](bsam/SPECIFICATION_METHOD.md) — how local source and runtime evidence become registry records.
- [Coverage ledger](bsam/CURRENT_SYNTAX_COVERAGE.md) — current measured coverage and gaps.
- [Primary dispatch audit](bsam/DISPATCH_AUDIT.md) — generated reconciliation of active source dispatches with the registry.
- [Generated BSAM 2.4 input reference](bsam/reference/BSAM_2_4_INPUT_API.md) — human-readable generated syntax reference.
- [`capabilities.json`](../specs/bsam-2.4/capabilities.json) — machine-readable source of truth.
- [Baseline audit](bsam/BASELINE_AUDIT_2026-08-31.md) — pinned source and executable identity.

## Architecture

- [System architecture](architecture/SYSTEM_ARCHITECTURE.md)
- [Loss-preserving model editing](architecture/MODEL_EDITING.md)
- [Manual `.ele` import](architecture/MESH_IMPORT.md)
- [Local-data policy](security/LOCAL_DATA_POLICY.md)

## Interfaces and operation

- [Local Agent API](api/README.md)
- [OpenAPI contract](api/openapi.yaml)
- [Model tool contracts](api/MODEL_TOOL_CONTRACTS.md)
- [Provider adapters](api/PROVIDER_ADAPTERS.md)
- [Local model runtime](api/LOCAL_MODEL_RUNTIME.md)
- [Terminal chat](api/CHAT_CLIENT.md)

## Acceptance records

- [Notch regression acceptance](bsam/NOTCH_ACCEPTANCE_2026-09-01.md) — one laminate transformation fixture, not the product scope.

Architecture documents explain design. The capability registry defines BSAM grammar and semantics. The roadmap alone defines implementation order.
