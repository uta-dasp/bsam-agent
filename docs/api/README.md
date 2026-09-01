# BSAM Agent API

## Initial local service

Run `python -m bsam_agent serve --workspace-root <path> --port 8765`. The server binds only to `127.0.0.1`. Health and capabilities are available at `/api/v1/health` and `/api/v1/capabilities`; deterministic tools use `POST /api/v1/tools/{tool}` with strict tool-specific JSON arguments. Paths must be relative to the configured workspace, request bodies are bounded, responses disable caching, and apply/run/stop require `confirm: true`.

The generic tool route is the first executable API used for model-tool integration. The resource-oriented routes in `openapi.yaml` remain the target once a persistent model-revision store is implemented.

`run_bsam` is asynchronous at this boundary: it reserves the output directory and returns `state: accepted`. Poll `get_run_status` for durable manifest state. `stop_run` can be requested immediately after acceptance; the service delivers the controlled request as soon as the run manifest exists.

The BSAM Agent API is the stable local boundary shared by the CLI, automated tests, and future VS Code extension. The initial contract is documented in [openapi.yaml](openapi.yaml). It is a design draft, not an implemented service.

## Contract principles

- Version every route under `/api/v1`.
- Use a configured workspace root; API paths are workspace-relative.
- Return stable machine-readable error and validation codes.
- Keep import, change planning/application, validation, rendering, and execution as separate operations.
- Bind every change plan to an exact model revision and content digest.
- Preview direct edits and structural transformations before applying them.
- Preserve original files by default and expose both semantic and source diffs.
- Require a successful validation result for the exact model revision before rendering.
- Require a rendered artifact digest before execution.
- Treat run launch as asynchronous and return a run identifier.
- Never infer run success from process exit code alone.
- Expose the BSAM executable fingerprint and syntax-specification version through capabilities.
- Keep natural-language/model-provider traffic outside the deterministic BSAM endpoints.

## Resource lifecycle

```text
source data
   -> model revision
   -> change preview/plan
   -> new model revision
   -> validation result
   -> rendered input artifact
   -> run
```

Every transition records the input digest and specification version. Editing creates a new revision and never mutates an earlier revision. The change invalidates prior validation and rendering results for the new revision.

## Compatibility

Additive response fields are allowed within v1. Removing or changing field meaning requires a new API version. BSAM capability additions do not automatically change the Agent API; they first update the versioned capability registry and domain schema.

## Model-provider tools

The optional language model uses the narrower contracts in [MODEL_TOOL_CONTRACTS.md](MODEL_TOOL_CONTRACTS.md). Those tools call the same application services as this API and cannot bypass its invariants.
