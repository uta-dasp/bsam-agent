# Model tool contracts

These are the only operations an optional language model should be allowed to request. The executable initial schemas are generated from `src/bsam_agent/tool_contracts.py` and exposed by `get_capabilities`; later domain expansion must update that source rather than duplicating schemas in prompts or adapters.

| Tool | Purpose | Mutates local state |
|---|---|---:|
| `get_capabilities` | List supported current BSAM features and required fields | No |
| `inspect_model` | Return source, structure, semantic entities/references, and diagnostics | No |
| `validate_model` | Run deterministic validation | No |
| `import_mesh` | Inspect and validate a manually prepared Abaqus-style `.ele` mesh | No |
| `preview_parameter_change` | Plan one registered parameter edit | Writes plan only |
| `preview_add_node`, `preview_add_element`, `preview_delete_node` | Plan bounded typed FE entity changes | Writes plan only |
| `preview_create_set`, `preview_add_set_members` | Plan bounded node/element-set changes | Writes plan only |
| `preview_import_mesh` | Plan assembly of a validated `.ele` mesh into an empty template cluster | Writes plan only |
| `preview_expand_notch_plies` | Plan the approved applicability-checked notch 2-to-8-ply transformation | Writes plan only |
| `review_change` | Re-derive and return an exact plan's semantic/source diff | No |
| `apply_change` | Apply one exact reviewed plan to a new deck and audit sidecar | Yes, confirmation required |
| `run_bsam` | Launch a validated rendered artifact | Yes |
| `get_run_status` | Read process and artifact state | No |
| `stop_run` | Request controlled BSAM termination | Yes |

## Mandatory policies

- Tool arguments are validated against strict schemas; unknown properties are rejected.
- The provider receives summaries and enumerations by default, never full source files or unrestricted decks.
- Model changes use stable capability/entity identifiers, never raw unrestricted text replacement.
- `apply_change` requires a non-stale plan identifier and digest returned by a preview tool.
- Ambiguous structural changes return required engineering decisions; the provider cannot invent them.
- `run_bsam` validates and fingerprints the exact source set before launch.
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
