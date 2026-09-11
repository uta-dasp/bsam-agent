# Abaqus-style `.ele` mesh import

## Version 1 contract

The mesh is created in Abaqus or another mesher. The user manually prepares an Abaqus-style `.ele` interchange file containing only the mesh records needed by BSAM. VTMS may later visualize or assemble meshed objects, but it is not the mesh generator or the authority for this format.

The deterministic importer currently accepts:

- `*DIMENSIONS`;
- `*NODE`;
- `*ELEMENT, TYPE=...`;
- explicit and generated `*NSET` and `*ELSET` records;
- element-based `*SURFACE` records;
- per-element `*ORIENTATION` records.

`*DIMENSIONS` follows the pinned BSAM allocator, not an Abaqus count convention: its four values are node capacity, element capacity, selection-slot count, and section-slot capacity. Zero is valid for unused selection/section arrays, and capacities may safely exceed populated counts. Import rejects node or element capacities smaller than the explicit mesh.

It rejects unknown keywords, duplicate labels and set names, missing connectivity or set members, missing surface sets, missing orientation elements, non-finite values, invalid orientation vectors, and dimension-count mismatches.

## Template-based assembly

For version 1, the existing BSAM `.in` template remains authoritative for materials, boundary conditions, constitutive/failure data, solver controls, and output requests. It must contain an empty named solid cluster:

```text
CLUSTERS
*TYPE
solid
*NAME
mesh_cluster
*STOP
END CLUSTERS
```

The import planner validates the `.ele`, renders canonical current cluster commands, inserts them before the cluster boundary, validates the proposed complete source set, and produces a reviewed revision-bound plan. The plan records the absolute mesh path and SHA-256, so review or apply fails if either the template source set or mesh input changes.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m bsam_agent plan-import-mesh template.in mesh.ele `
  --cluster mesh_cluster --workspace-root . --out import-plan.json
python -m bsam_agent diff import-plan.json
python -m bsam_agent apply-change import-plan.json --out assembled.in
python -m bsam_agent validate assembled.in
```

The template and mesh must remain inside the configured workspace. Import into a non-empty cluster is blocked.

Direct conversion from a full Abaqus input deck or Gmsh file is deferred; those future adapters will target the same canonical mesh model.

## Net-new deck generation

Registry profile `generation.mechanical-isotropic-solid-v1` builds one canonical linear-mechanical solid deck without a template. Its typed intent requires the unit system, analysis name/status, cluster name, PARDISO thread and matrix controls, convergence controls, static loading controls, every isotropic material and strength value, failure criterion, fiber rotation, and at least one explicit constraint and load. Targets must resolve to imported node sets. The generator promotes each node set to a deterministic one-based node `*SELECTION`, which the pinned executable requires during boundary assembly. Version 1 rejects imported `*SURFACE` records because the pinned BSAM cluster dispatcher has no matching active command.

`generate-deck` creates a new deck and JSON provenance manifest without overwrite. Stable comments and manifest fields bind the generator, registry profile, mesh digest, normalized-intent digest, and output digest. Static validation failure rolls back both outputs. Profile 1.3.0 derives one selection slot per imported node set and zero section slots; it completed a controlled pinned-executable run with an indefinite PARDISO matrix, exit code zero, the success sentinel, and no fatal marker.

```powershell
python -m bsam_agent generate-deck mesh.ele intent.json `
  --workspace-root . --out model.in --manifest-out model.generation.json
```
