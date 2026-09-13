# Controlled VTK output probe — 2026-09-12

## Scope

This probe isolates one previously source-documented execution path: BOUNDARY `*OUTPUT` with `type=data_file`, `clusters=all`, `format=vtk`, and `intermediate=0`. The checked-in input is `tests/fixtures/runtime_vtk_output.in`. It is the already successful synthetic eight-node C3D8 mechanical-isotropic profile with only that output record added; no engineering value changed.

This evidence is intentionally narrow. It verifies legacy VTK output for this single-cluster mechanical-isotropic profile. It does not verify ParaView/SHEFF output, aggregate output families, other selectors, intermediate iteration output, or general output generation.

## Reproduction

From the repository root, with the pinned executable and license available:

```powershell
python -m bsam_agent validate tests\fixtures\runtime_vtk_output.in
python -m bsam_agent run tests\fixtures\runtime_vtk_output.in --output-dir runs\vtk-output-probe-20260912 --executable ..\projects\bsam20.exe --timeout 30 --stop-grace 30 --workspace-root .
```

The output directory must not already exist.

## Bound evidence

- Registry baseline before the probe: `0.135.0`
- Input SHA-256: `8670D5610E62F4E726D2F81CBC56056D2288A899D1961E7893A350D06B77942D`
- Source-set SHA-256: `6304685EF16EEFD56492921393D9810D7AF2AA892BFF2C175AC5ED920B00DED9`
- Executable SHA-256: `7AE34D9821C6FE017897B020D615BFFA8A33F33F6D3734EBA3FD5A435788FB2A`
- Classification: `succeeded`
- Process exit code: `0`
- Duration: `0.312986` seconds
- Success sentinel: present
- Fatal markers: none
- Controlled stop: not requested
- VTK artifact: `generated-profile-vtk-20260912_001.vtk`, 3,257 bytes
- VTK SHA-256: `669D03413872E9524AC9403DD5E249F95A9FB4203A147D38B9077663D98B90FA`

The VTK artifact begins with the VTK 3.0 header, declares an ASCII unstructured grid, and contains the expected eight points. Local run outputs remain ignored under `runs/vtk-output-probe-20260912`; the input and this digest-bound evidence record are checked in.
