# Open inputs and recorded assumptions

These items do not block groundwork or the current source-derived API inventory.

## Needed before the VTMS import implementation

- At least one original VTMS `.ele` export that may be used locally as a development fixture or transformed into a small non-sensitive fixture.
- A VTMS `.mtl` sample only if material-library import is required in the first vertical slice.
- Confirmation of whether VTMS can export cluster data in another stable text format that should be preferred over `.ele`.

## Manual availability

The separate BSAM-FE user's manual is not currently available. The first specification is therefore source-derived and evidence-labelled. If the manual becomes available later, it will be used as an additional local documentation source and discrepancies will be recorded rather than silently changing behavior.

## Scope assumption

“All current BSAM capabilities documented in API” means all active input capabilities reachable in the pinned BSAM 2.4 code path, documented in the generated BSAM input API reference. Deprecated, commented-out, or unreachable routines are excluded from generation but may produce migration diagnostics.

## Version 1 editing acceptance case

An existing supported two-ply current-syntax model must be transformable into an eight-ply model and then run. The agent will derive what it can from the source and ask only for engineering choices the deck cannot determine, such as total-versus-ply thickness preservation and the intended eight-ply stacking sequence. A suitable non-sensitive input will be needed before this transformation can become an executable acceptance fixture.

## Decision needed after G1

Choose the first Gmsh-backed geometry families and their acceptance tolerances after the cluster, element, set, orientation, connection, and crack contracts are understood. This avoids designing a mesh API around incomplete syntax knowledge.

Before G5 implementation, select and pin a local Gmsh version, identify the BSAM element types that may be produced, define physical-group naming for clusters/node sets/element sets, and provide one small trusted target mesh for each initial geometry family. Ply extrusion, interface generation, and orientation policy must be explicit rather than inferred from geometry alone.
