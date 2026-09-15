# Unseen named-data investigation acceptance — 2026-09-14

This synthetic-only acceptance closes the bounded-loop M4 exit criterion with a new fixture and
objective that were not represented by an orchestrator workflow. The request asked the agent to
investigate a structured material, trace its outbound dependencies, and explain whether they
resolved. No mutation or BSAM execution was authorized or performed.

The provider-neutral test composed the trajectory `query_model → inspect_model → find_references`.
The first two steps came from existing generic intent/completion behavior; after observing them, the
provider selected `find_references` from the general read-only tool set. No named-data-, material-,
or fixture-specific continuation branch was added. Deterministic execution found three resolved
outbound relationships: table, user-function, and statistical-distribution use.

The grounded synthesis contained separate `current_model` and `inference` claims citing immutable
observation IDs. The expanded trajectory scorer passed tool order, argument accuracy, read bound,
clarification/confirmation behavior, policy behavior, evidence sufficiency, repetition, final
usefulness, and non-mutation checks.

Reproduction is the repository test:

```powershell
python -m pytest -q tests/test_unseen_investigation_acceptance.py
```

The sanitized machine-readable record is
[`evals/results/unseen_named_data_investigation_2026-09-14.json`](../../evals/results/unseen_named_data_investigation_2026-09-14.json).
It stores fixture/source-set/objective digests and structural outcomes, not model prompts, raw source
content, credentials, or proprietary data. This proves bounded agent-loop composition and grounded
reporting on the synthetic fixture; it is not BSAM runtime or production qualification evidence.
