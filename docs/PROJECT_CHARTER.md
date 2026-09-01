# Project charter

## Goal

Create a dependable BSAM Agent that can understand and safely modify an existing current-syntax BSAM model, or create one from engineering intent plus mesh/cluster data, then run it with the existing Windows executable and clearly report run state.

The language model is an assistant to the workflow. It is not the parser, validator, renderer, or process supervisor.

## Three APIs

The word “API” has three distinct meanings in this project:

1. **BSAM input API** — the current input language accepted by the pinned BSAM executable.
2. **BSAM Agent API** — the versioned local interface used by the CLI and future VS Code extension.
3. **Model-provider API** — a replaceable adapter for local inference, Gemini, or OpenAI.

They must remain separate so changes in a model vendor cannot alter BSAM syntax or the editor integration.

## Version 1 scope

- Import manually prepared Abaqus-style mesh/cluster data from `.ele` interchange files. VTMS may assemble or visualize existing meshes but is not treated as the mesh generator or file-format authority.
- Generate supported mesh families through a pinned local Gmsh adapter after the `.ele`-import vertical slice, then convert them through the same validated mesh/cluster interface.
- Import current BSAM input files and their include graph into a loss-preserving syntax representation and typed model.
- Modify any supported model parameter while preserving unrelated source text, ordering, comments, and include structure.
- Perform dependency-aware structural transformations such as converting a two-ply model to an eight-ply model.
- Identify consequential changes to mesh topology, sets, materials, orientations, connections, cracks, boundary conditions, loads, and references.
- Present a change plan, assumptions, unresolved decisions, and semantic/source diff before applying a modification.
- Represent all active current-syntax BSAM capabilities in a typed domain model.
- Validate structural, reference, numerical, and execution prerequisites locally.
- Render deterministic `.in` files.
- Start, monitor, and stop serial BSAM runs in isolated output directories.
- Detect success and failure from BSAM artifacts and messages, not from process exit code alone.
- Provide a CLI first and a stable local API for a later VS Code extension.

## Deferred

- MPI execution
- Automated result interpretation and report generation
- Migration-quality generation of obsolete syntax
- General-purpose unstructured mesh generation
- Modification of BSAM source code

Gmsh-backed embedded mesh generation remains a product requirement, but follows the `.ele`-import vertical slice. Its first supported geometries, element mappings, physical-group conventions, ply/orientation rules, and quality gates will be defined only after the current cluster/element contract is complete. General-purpose arbitrary CAD repair and unrestricted unstructured meshing remain deferred.

## Completion criteria for version 1

Version 1 is complete only when:

- every active current-syntax capability has a documented provenance record and support status;
- an unchanged imported deck round-trips without altering bytes, including comments and include structure;
- direct parameter edits alter only the intended construct and required dependent references;
- registered structural transformations pass dependency, topology, semantic, and executable tests;
- the two-ply-to-eight-ply acceptance scenario is supported for a documented model pattern, with ambiguous thickness and layup policies requested rather than guessed;
- generated decks pass static validation and representative executable probes;
- runs are isolated, cancellable, and classified without trusting exit code zero;
- provider-free operation is possible;
- model-assisted operation cannot bypass validation or execution policy;
- user source and engineering data remain local unless an explicit sanitized payload is approved.
