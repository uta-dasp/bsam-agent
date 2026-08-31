# Existing-model editing

Modifying an existing BSAM input is a Version 1 requirement. The implementation must understand the model and its references; it must not rely on unrestricted search-and-replace or ask a language model to rewrite a deck.

## Two synchronized representations

An imported model has:

1. a lossless concrete syntax tree and include graph that retain every source token, comment, line ending, ordering choice, and file boundary;
2. a typed semantic model with stable identities and explicit dependency edges.

The semantic model answers what a construct means and what depends on it. The concrete tree controls the smallest safe source patch. Unknown constructs remain preserved; a change is blocked if an unknown construct could depend on the affected entities.

## Change classes

### Direct parameter edit

Examples include a material constant, load magnitude, solver tolerance, output option, damage parameter, orientation, or boundary value. The change planner validates the target and type, finds dependent constraints, and patches the owning token or record.

### Structural transformation

Examples include changing ply count, replacing a material throughout selected regions, refining a recognized structured mesh, duplicating cluster patterns, or changing a stacking sequence. These operations can create/remove entities and update many references. Each supported transformation has a versioned algorithm, applicability test, parameter schema, impact rules, and acceptance tests.

## Required workflow

```text
import source set
   -> select exact base revision
   -> preview requested change
   -> resolve required engineering decisions
   -> review assumptions + semantic/source diff
   -> apply immutable change plan
   -> validate new revision
   -> render modified source set
   -> optionally run BSAM
```

Applying a change never overwrites the original input by default. The first implementation writes a revision artifact or user-selected destination. In-place replacement, if added later, requires an explicit operation and recoverable backup policy.

## Ply-count acceptance scenario

Given a supported current-syntax two-ply input model, a request to make it eight plies must:

- identify how plies are represented by clusters, elements, sets, materials, orientations, interfaces/connections, and thickness coordinates;
- determine whether total laminate thickness or individual ply thickness is preserved;
- determine the eight-ply material/orientation stacking sequence, including whether the original sequence repeats, mirrors, or is explicitly replaced;
- regenerate or duplicate the necessary nodes and elements without identifier collisions;
- rebuild ply/interface sets and connections;
- update every dependent reference, including loads, boundary conditions, cracks, failure definitions, and output selections when applicable;
- retain unrelated user formatting, comments, blocks, and included files;
- fail with precise required inputs when the source and user request do not determine a unique transformation;
- pass static validation and a controlled run against the pinned executable before the transformation is marked supported.

This acceptance scenario applies to documented model patterns. “Correctly” does not mean silently extrapolating an arbitrary mesh: the transformation must first prove that its applicability rules match the imported model.

## Editing invariants

- No-op import/render is byte-identical for every file in the source set.
- Plans are bound to a model revision and content digest.
- Plans for decks with FE includes are bound to the digest of every source file; a change to any included file makes the plan stale.
- Applying a stale plan fails without modifying files.
- Unaffected source spans remain unchanged.
- Identifiers are unique and all references resolve after a change.
- Validation errors block rendering and execution.
- Every applied operation produces a machine-readable audit record and human-readable diff.

The current direct-edit slice patches only the root deck. If that deck has FE includes, the output deck must remain in the original BSAM input directory so unchanged relative include resolution is preserved. Copying or editing a complete source set is blocked until a multi-file change plan can preview and audit every destination file boundary.
