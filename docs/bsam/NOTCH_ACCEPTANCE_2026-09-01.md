# Notch deterministic acceptance record - 2026-09-01

The original `projects/notch_v1/notch_v1.in` was not modified.

## Static and change-plan acceptance

- Root SHA-256: `B7ACAA7EFEF23D27F9ADCD01FE24AD6D2BC2F5EC9CB997AEE221CC562DB9010D`.
- Semantic entities: 15,480.
- Semantic references: 53,690 resolved; zero unresolved, ambiguous, or type-mismatched.
- The checked integration test previews `BOUNDARY.*CONVERGENCE[1].d_reduction` from `0.25` to `0.30` and requires zero proposed validation errors.

## Isolated executable exercise

A revision-bound copy with that change ran against the pinned executable for 180 seconds in the ignored `runs/notch-acceptance-run` directory. The supervisor requested a controlled `.exit` stop at the configured timeout. BSAM returned process code zero, the stop was not escalated, and no fatal markers were detected. The run produced 31 step artifacts but did not reach the BSAM success sentinel before the timeout, so it is classified `stopped`, not `succeeded`.

This proves modified-deck preflight, launch, sustained execution, artifact capture, and controlled timeout behavior on the real notch model. It does not satisfy the successful-completion acceptance gate. A longer runtime budget is required for that gate.
