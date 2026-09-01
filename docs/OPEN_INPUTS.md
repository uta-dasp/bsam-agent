# Open inputs and recorded assumptions

These items do not block groundwork or the current source-derived API inventory.

## Abaqus-style `.ele` import decision

- Resolved 2026-09-01: a user-supplied `.ele` example established the interchange structure; product behavior and acceptance testing must not be specialized around that example.
- For version 1, the user manually creates `.ele` files from Abaqus by retaining mesh-related records and removing unrelated model data.
- VTMS visualizes or assembles already meshed objects; it does not generate the mesh and is not the `.ele` format authority.
- Direct Abaqus/Gmsh conversion into this interchange is a later capability.
- Material-library import is outside the first mesh-import slice unless a separate material fixture and requirement are supplied.

## Manual availability

The separate BSAM-FE user's manual is not currently available. The first specification is therefore source-derived and evidence-labelled. If the manual becomes available later, it will be used as an additional local documentation source and discrepancies will be recorded rather than silently changing behavior.

## Scope assumption

“All current BSAM capabilities documented in API” means all active input capabilities reachable in the pinned BSAM 2.4 code path, documented in the generated BSAM input API reference. Deprecated, commented-out, or unreachable routines are excluded from generation but may produce migration diagnostics.

## Version 1 editing acceptance case

An existing supported two-ply current-syntax model must be transformable into an eight-ply model and then run. The agent will derive what it can from the source and ask only for engineering choices the deck cannot determine, such as total-versus-ply thickness preservation and the intended eight-ply stacking sequence. A suitable non-sensitive input will be needed before this transformation can become an executable acceptance fixture.

The notch model is now the accepted source fixture. Its two clusters occupy Z=0..1 and Z=1..2, use constitutive/orientation pairs 1/75 degrees and 2/15 degrees, connect `PLY1.ZMAX` to `PLY2` with connection constitutive 3, restrain in-plane sets on both plies, and restrain Z only on the bottom ply. Before implementing the eight-ply transformation, confirm:

- whether total thickness remains 2.0 (eight 0.25-thick plies) or each ply remains 1.0;
- the eight-ply constitutive/orientation sequence;
- whether all seven adjacent interfaces use the current connection constitutive 3;
- whether in-plane boundary/loading controls replicate to every ply while the Z restraint remains bottom-only.

## Decision needed after G1

Choose the first Gmsh-backed geometry families and their acceptance tolerances after the cluster, element, set, orientation, connection, and crack contracts are understood. This avoids designing a mesh API around incomplete syntax knowledge.

Before G5 implementation, select and pin a local Gmsh version, identify the BSAM element types that may be produced, define physical-group naming for clusters/node sets/element sets, and provide one small trusted target mesh for each initial geometry family. Ply extrusion, interface generation, and orientation policy must be explicit rather than inferred from geometry alone.
