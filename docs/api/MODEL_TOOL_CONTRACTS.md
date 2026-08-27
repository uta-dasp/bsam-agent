# Model tool contracts

These are the only operations an optional language model should be allowed to request. Exact JSON Schemas will be generated from the canonical domain types during implementation.

| Tool | Purpose | Mutates local state |
|---|---|---:|
| `get_capabilities` | List supported current BSAM features and required fields | No |
| `inspect_mesh` | Return bounded mesh metadata, sets, extents, and diagnostics | No |
| `get_model_summary` | Return a bounded summary of a model revision | No |
| `create_model` | Create a typed draft from explicit engineering intent | Yes |
| `preview_model_change` | Plan direct edits or dependency-aware transformations and return decisions/impact/diff | No |
| `apply_model_change` | Apply one exact, reviewed change-plan digest to create a new revision | Yes |
| `get_model_diff` | Compare two revisions semantically and at source level | No |
| `validate_model` | Run deterministic validation | No |
| `render_input` | Render an already validated revision | Yes |
| `estimate_run` | Return local preflight facts; not a physics prediction | No |
| `run_bsam` | Launch a validated rendered artifact | Yes |
| `get_run_status` | Read process and artifact state | No |
| `stop_run` | Request controlled BSAM termination | Yes |

## Mandatory policies

- Tool arguments are validated against strict schemas; unknown properties are rejected.
- The provider receives summaries and enumerations by default, never full source files or unrestricted decks.
- Model changes use stable capability/entity identifiers, never raw unrestricted text replacement.
- `apply_model_change` requires a non-stale plan identifier and digest returned by `preview_model_change`.
- Ambiguous structural changes return required engineering decisions; the provider cannot invent them.
- `run_bsam` requires an artifact identifier and digest produced by `render_input`.
- A model cannot approve its own invalid data: deterministic errors block rendering and execution.
- Destructive file operations are absent from the tool surface.
- `stop_run` targets one known run and uses BSAM's controlled stop mechanism where available.
- Material, failure, and solver selections must resolve to capability-registry identifiers rather than free-form keywords.

## Provider interface

All model vendors implement one conceptual interface:

```text
complete(messages, response_schema, tools, policy) ->
  structured_response | tool_calls | provider_error
```

The application owns retries, schema repair limits, redaction, audit metadata, and provider allowlists. Provider output is untrusted input.
