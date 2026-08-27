# Verification and trust model

## What is runnable now

The BSAM Agent application is not runnable yet. No deck parser, editor, renderer, run supervisor, local API, or model adapter has been implemented.

The specification tooling is runnable now:

```powershell
cd "D:\Partha\BSAM\bsam agent"
python tools\registry_tools.py validate
python tools\registry_tools.py check
python -m unittest discover -s tests -v
```

`validate` checks registry identities, evidence references, hierarchy, body variants, fields, and dependencies. `check` proves the generated API reference matches the registry. The tests currently protect the pinned baseline, current block names, command dispatch prefixes, core FE edit grammars, active BOUNDARY inventory, and deterministic reference generation.

## Independently verify the pinned baseline

From the agent repository:

```powershell
git -C ..\bsam20 rev-parse HEAD
(Get-FileHash -Algorithm SHA256 ..\projects\bsam20.exe).Hash
```

Compare the results with `target.source_commit` and `target.executable_sha256` in `specs/bsam-2.4/capabilities.json`. A mismatch means the specification snapshot and executable/source are no longer the same baseline.

## How to review specification claims

Every registry claim must cite local evidence. For a sampled capability:

1. Find it in `specs/bsam-2.4/capabilities.json`.
2. Follow its `evidence_ids` to the evidence index.
3. Open the local source/example locator and inspect the recorded routine or lines.
4. Check its coverage label. `identified` and `partially-documented` are not claims of complete support.
5. For `runtime-verified`, require a reproducible probe manifest, copied/synthetic input, executable fingerprint, output classification, and expected sentinel.

The generated reference is a view of the same registry; it is not independent evidence.

## Acceptance layers for implementation

| Layer | What it proves | Required evidence |
|---|---|---|
| Specification | The current syntax and dependency rule were understood | Pinned local source/docs/examples and registry record |
| Parser/renderer | Text can be imported and emitted without unintended change | Byte-identical no-op and include-graph golden tests |
| Edit planner | A requested change touches all required dependents and nothing unrelated | Semantic plan, minimal source diff, and transformation tests |
| Static validation | Structure, types, references, and topology are internally consistent | Stable diagnostic assertions and negative fixtures |
| BSAM execution | The produced deck is accepted by the pinned executable | Isolated run, explicit end sentinel, and absence of fatal diagnostics |
| Model assistance | The model selects valid tools without inventing BSAM behavior | Provider-independent evaluation set and tool/schema accuracy results |

No single successful BSAM run proves general correctness. Each supported capability needs positive, negative, round-trip, and dependency tests appropriate to its risk.

## Planned user-facing audit path

When G2 is complete, a user will be able to run `inspect`, `plan-change`, `diff`, `validate`, `run`, and `status` without a language model. Every applied change will carry the source digest, plan digest, changed model paths, affected files, validation result, executable fingerprint, and run directory. This deterministic path is the reference against which local or hosted model behavior is checked.
