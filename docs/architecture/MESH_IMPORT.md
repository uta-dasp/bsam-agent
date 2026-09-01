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
