# Model tool contracts

These are the only operations an optional language model should be allowed to request. The executable initial schemas are generated from `src/bsam_agent/tool_contracts.py` and exposed by `get_capabilities`; later domain expansion must update that source rather than duplicating schemas in prompts or adapters.

| Tool | Purpose | Mutates local state |
|---|---|---:|
| `get_capabilities` | List supported current BSAM features and required fields | No |
| `inspect_model` | Return source, structure, semantic entities/references, and diagnostics | No |
| `query_model` | Run focused registered-construct, parameter, entity, and reference queries | No |
| `validate_model` | Run deterministic validation | No |
| `import_mesh` | Inspect and validate a manually prepared Abaqus-style `.ele` mesh | No |
| `generate_deck` | Create a canonical deck and provenance manifest from a registered profile and complete typed intent | Yes, confirmation required |
| `preview_parameter_change` | Plan one registered parameter edit | Writes plan only |
| `preview_parameter_removal` | Plan removal of an isolated optional parameter with verified omission/default semantics | Writes plan only |
| `preview_compose_changes` | Compose 2–8 independent same-revision typed plans into one reviewed plan | Writes plan only |
| `preview_add_node`, `preview_add_element`, `preview_delete_node` | Plan bounded typed FE entity changes | Writes plan only |
| `preview_create_set`, `preview_add_set_members` | Plan bounded node/element-set changes | Writes plan only |
| `preview_import_mesh` | Plan assembly of a validated `.ele` mesh into an empty template cluster | Writes plan only |
| `preview_expand_notch_plies` | Plan the approved applicability-checked notch 2-to-8-ply transformation | Writes plan only |
| `preview_migrate_legacy_solver` | Plan legacy type-9 to current PARDISO syntax migration for the non-MPI baseline | Writes plan only |
| `preview_rename_boundary_condition` | Plan a boundary-condition rename and retarget all loading-sequence changes | Writes plan only |
| `preview_rename_entity` | Plan a rename through a capability with verified rename support | Writes plan only |
| `preview_create_entity`, `preview_modify_entity`, `preview_delete_entity` | Plan capability-gated generic node, element, set, and nodal-record operations | Writes plan only |
| `preview_refresh_change` | Re-preview a digest-valid stale typed plan against the changed source | Writes plan only |
| `review_change` | Re-derive and return an exact plan's semantic/source diff | No |
| `apply_change` | Apply one exact reviewed plan to a new deck and audit sidecar | Yes, confirmation required |
| `run_bsam` | Launch a validated rendered artifact | Yes |
| `get_run_status` | Read process and artifact state | No |
| `stop_run` | Request controlled BSAM termination | Yes |

## Mandatory policies

- Tool arguments are validated against strict schemas; unknown properties are rejected.
- The provider receives summaries and enumerations by default, never full source files or unrestricted decks.
- Model changes use stable capability/entity identifiers, never raw unrestricted text replacement.
- `generate_deck` requires `confirm: true`, refuses existing outputs, validates every engineering field and mesh target, and rolls back both deck and provenance manifest if generated static validation fails.
- Registry specification `coverage` and per-capability operational support are separate; `get_capabilities` exposes complete operation maturity plus derived inspect/query/create/modify/validate/run intent maturity, and omitted registry operations are reported as `unassessed`.
- Optional parameter insertion/removal occurs only when its parameter-level registry operation is `verified`. Current cases are absent or isolated-record `BOUNDARY/*CONVERGENCE/maxiterations`, Boolean `BOUNDARY/*G-CONTROL/DAMP` enable/disable, and the repeated SHEFF option row `SOLVER/relative_tolerance`; shared-record removal is blocked.
- `query_model` reports explicit versus registered-default parameter values, supports stable entity kind/name selectors for listings and references, and returns ambiguity instead of choosing among multiple contexts.
- Validation diagnostics identify both their level (`syntax`, `structure`, `references`, `bsam-semantic-constraints`, `numeric-constraints`, `execution-compatibility`, or `engineering-plausibility`) and provenance. Unclassified new diagnostic codes are rejected until both are explicit; engineering heuristics remain warnings and never mutate a deck.
- `preview_rename_entity` uses canonical capability IDs and deterministic Python adapters; it refuses unverified rename operations instead of interpreting transformation logic from registry text.
- Generic structural previews use canonical capability IDs, strict capability-specific payloads, and the same dependency-aware typed planners as the compatibility tools. `preview_modify_entity` retargets one exact cluster-local BOUNDARY, LOAD, SECTION, SHIFT, or SCALE record using `entity_name` as the current target and `changes` containing `cluster`, `new_target`, and an optional one-based `occurrence`.
- `preview_delete_entity` deletes an unreferenced node or element, or an explicit node/element set with one uncommented definition and no inbound semantic references. Implicit membership, generated, multiply-defined, and dependency-bearing cases are rejected.
- Generic set modification accepts exactly one of `add_members` or a single `remove_member`; removal targets one exact explicit token and refuses ambiguous or empty-set results.
- `preview_refresh_change` replays only the stale plan's digest-protected typed selector and requested values; the refreshed plan requires a new confirmation.
- `preview_compose_changes` revalidates every embedded typed component, rejects overlap or mixed revisions, validates the combined result, and creates one apply boundary; it does not infer sequential engineering dependencies.
- `apply_change` requires a non-stale plan identifier and digest returned by a preview tool.
- Applying a root edit to a different directory copies every relative include without overwriting existing files, verifies the copied source-set digest, and rolls back files created by a failed copy.
- Verified node creation/deletion, element creation, node/element-set creation, extension or member removal, BOUNDARY/LOAD target replacement, and empty-cluster mesh import can target an included FE fragment, including a fragment whose logical continuation is the root deck after EOF. The plan binds the patch to that source path, requires a separate destination directory, copies the complete source set, and reports the changed include in its audit. Composite plans may combine independent root and include patches.
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
