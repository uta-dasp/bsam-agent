# System architecture

## Core flow

```text
User / VS Code / CLI
        |
        v
Intent and Agent tools  <---->  Optional model-provider adapter
        |
        v
Typed BSAM domain model
        |
        +--> change planner + dependency/impact analysis
        |
        +--> local syntax + semantic validator
        |
        +--> deterministic current-syntax renderer
        |
        v
Isolated run supervisor --> bsam20.exe --> local run artifacts
```

The model provider never writes a BSAM deck or launches a process directly. It can propose typed intent and tool arguments; the local core owns validation, rendering, authorization, and execution.

## Components

### BSAM specification package

A machine-readable registry of blocks, commands, parameters, types, defaults, constraints, cross-references, and provenance. It is versioned against a BSAM executable fingerprint.

### Canonical domain model

A typed representation of analysis configuration, clusters, mesh entities, sets, materials, failure definitions, boundary/load data, solution controls, output requests, user functions, moisture, tables, statistical distributions, and cracks. Stable entity identities and dependency links allow coordinated changes rather than fragile line edits.

An imported deck also retains a concrete syntax tree and source-file/include graph. This preserves source location, whitespace, comments, ordering, spelling, and unknown text. New generation uses current canonical names only.

### Parser and importer

Adapters convert current BSAM decks, VTMS data, and later Gmsh-backed embedded-mesh requests into the canonical model. Import formats are independent plugins behind a narrow interface; VTMS source code is not required.

The Gmsh path uses a typed geometry/meshing request, a pinned local Gmsh adapter, and a neutral intermediate mesh model. Gmsh physical groups map to candidate BSAM clusters, node sets, and element sets. A deterministic converter then validates supported element types, assigns stable labels, derives required sets/orientations, and inserts the cluster into the BSAM domain model. The language model can propose geometry-tool arguments but cannot write connectivity or bypass mesh and BSAM validation.

### Change planner

Every requested modification first produces a revision-bound change plan. Direct parameter edits and higher-level transformations share the same planning path. The planner resolves dependencies, states assumptions, requests missing engineering choices, predicts touched entities/files, and produces a semantic and source preview. Applying the plan requires its identifier and digest, preventing stale or silently changed edits.

Structural transformations operate on the typed model. For example, changing ply count may regenerate through-thickness nodes/elements, copy or replace ply assignments and orientations, rebuild sets and interfaces, and update dependent references. If the source does not establish total-thickness, per-ply-thickness, stacking-sequence, material, or orientation policy, the planner stops for those decisions rather than guessing.

See [MODEL_EDITING.md](MODEL_EDITING.md) for editing invariants and the ply-count acceptance scenario.

### Validator

Validation is layered:

1. lexical and structural validity;
2. required blocks and parameter types;
3. cross-reference integrity among nodes, elements, sets, materials, clusters, loads, and cracks;
4. numerical and topology checks that can be established locally;
5. execution preflight, including executable identity and path safety.

Every issue has a stable code, severity, model path, human message, and evidence reference.

### Renderer

Rendering is deterministic and has two modes. A newly generated model uses canonical current syntax. A modified imported model applies a minimal source patch to the retained syntax tree and include graph, preserving unrelated content. A no-op render is byte-identical to the imported source set. Both modes record content digests.

### Run supervisor

Each run receives a unique output directory and a manifest. The supervisor invokes BSAM using separate input/output directory arguments, captures output, monitors `.lst`, `.ssn`, and `.exit`, and classifies the run using explicit messages and the BSAM end sentinel. Process exit code is supporting evidence only because BSAM can report a fatal input error and still return zero.

### Local Agent API

The CLI and VS Code extension call one versioned local API. File paths are resolved within a configured workspace root. Arbitrary remote access is disabled by default.

### Provider adapters

Provider adapters translate a constrained intent schema and tool declarations to:

- a local CPU inference server;
- Gemini;
- OpenAI.

BSAM logic and vocabulary remain in local specification services, not provider-specific prompts.

## Suggested repository layout after implementation begins

```text
bsam agent/
  docs/
  schemas/            # versioned JSON Schemas and BSAM capability registry
  src/bsam_agent/     # Python core and local API
    mesh/              # neutral mesh model, VTMS importer, and future Gmsh adapter
  tests/
    fixtures/         # small, reviewed, non-sensitive fixtures
    contract/
    integration/
  extension/          # future TypeScript VS Code extension
```

Only `docs/` is established during groundwork.
