# BSAM primary dispatch audit

Pinned source commit: `9954027f1c325c63d58aeb836e8fec41a4b363af`.

This generated audit compares the active initialization sequence and primary input dispatches with the capability registry. It records tokens and source locations only; BSAM source is not copied into this repository.

## Top-level initialization path

| Token | Initializer | Active call | Block lookup |
|---|---|---|---|
| `INPUT` | `INP_INI` | `source/bsam/mainf1.f90:55` | `handled by INPUT initializer` |
| `SOLVER` | `SOLVE_INI` | `source/bsam/mainf1.f90:60` | `source/libbsam/solve_ini.f90:285` |
| `UFUNCTIONS` | `UFUNCTION_INI` | `source/bsam/mainf1.f90:67` | `source/libbsam/ufunction_ini.f90:26` |
| `MOISTURE` | `MOI_INI` | `source/bsam/mainf1.f90:71` | `source/libbsam/moisture.f90:55` |
| `CLUSTERS` | `IAP_INI` | `source/bsam/mainf1.f90:73` | `source/libbsam/iap_ini.f90:119` |
| `BOUNDARY` | `IBN_INI` | `source/bsam/mainf1.f90:77` | `source/libbsam/ibn_ini.f90:111` |
| `CONSTITUTIVE` | `CON_INI` | `source/bsam/mainf1.f90:89` | `source/libbsam/con_ini.f90:50` |
| `TABLES` | `TABLE_INI` | `source/bsam/mainf1.f90:91` | `source/libbsam/table_ini.f90:42` |
| `STATISTICAL` | `STAT_DIST_INI` | `source/bsam/mainf1.f90:93` | `source/libbsam/stat_dist_ini.f90:42` |
| `MATERIALS` | `MAT_INI` | `source/bsam/mainf1.f90:95` | `source/libbsam/mat_ini.f90:133` |
| `FAILURE` | `FAI_INI` | `source/bsam/mainf1.f90:97` | `source/libbsam/fai_ini.f90:43` |
| `USER` | `USF_INI` | `source/bsam/mainf1.f90:99` | `source/libbsam/usf_ini.f90:34` |
| `CRACK` | `CRK_INI` | `source/bsam/mainf1.f90:101` | `source/libbsam/crk_ini.f90:127` |

## Finite-element cluster command dispatch

| Prefix | Source |
|---|---|
| `*TYPE` | `source/libbsam/mod_fe_input.f90:235` |
| `*DIME` | `source/libbsam/mod_fe_input.f90:242` |
| `*NAME` | `source/libbsam/mod_fe_input.f90:253` |
| `*CONS` | `source/libbsam/mod_fe_input.f90:255` |
| `*NODE` | `source/libbsam/mod_fe_input.f90:258` |
| `*NGEN` | `source/libbsam/mod_fe_input.f90:293` |
| `*NCOP` | `source/libbsam/mod_fe_input.f90:331` |
| `*ELEM` | `source/libbsam/mod_fe_input.f90:365` |
| `*ELGE` | `source/libbsam/mod_fe_input.f90:400` |
| `*NSET` | `source/libbsam/mod_fe_input.f90:421` |
| `*ELSE` | `source/libbsam/mod_fe_input.f90:483` |
| `*BOUN` | `source/libbsam/mod_fe_input.f90:520` |
| `*LOAD` | `source/libbsam/mod_fe_input.f90:561` |
| `*FIEL` | `source/libbsam/mod_fe_input.f90:566` |
| `*SELE` | `source/libbsam/mod_fe_input.f90:588` |
| `*TOLE` | `source/libbsam/mod_fe_input.f90:659` |
| `*INTE` | `source/libbsam/mod_fe_input.f90:699` |
| `*ORIE` | `source/libbsam/mod_fe_input.f90:703` |
| `*BUIL` | `source/libbsam/mod_fe_input.f90:717` |
| `*STOP` | `source/libbsam/mod_fe_input.f90:721` |
| `*INCL` | `source/libbsam/mod_fe_input.f90:743` |
| `*SHIF` | `source/libbsam/mod_fe_input.f90:769` |
| `*SCAL` | `source/libbsam/mod_fe_input.f90:822` |
| `*EXCL` | `source/libbsam/mod_fe_input.f90:875` |
| `*FLIP` | `source/libbsam/mod_fe_input.f90:966` |
| `*SPAC` | `source/libbsam/mod_fe_input.f90:1011` |
| `*SECT` | `source/libbsam/mod_fe_input.f90:1015` |
| `*CRAC` | `source/libbsam/mod_fe_input.f90:1067` |
| `*TRAN` | `source/libbsam/mod_fe_input.f90:1128` |

## BOUNDARY construct dispatch

| Prefix | Source |
|---|---|
| `*type` | `source/libbsam/ibn_ini.f90:127` |
| `*g-co` | `source/libbsam/ibn_ini.f90:219` |
| `*solv` | `source/libbsam/ibn_ini.f90:256` |
| `*geo_` | `source/libbsam/ibn_ini.f90:259` |
| `*name` | `source/libbsam/ibn_ini.f90:262` |
| `*stat` | `source/libbsam/ibn_ini.f90:284` |
| `*clus` | `source/libbsam/ibn_ini.f90:303` |
| `*boun` | `source/libbsam/ibn_ini.f90:372` |
| `*conn` | `source/libbsam/ibn_ini.f90:536` |
| `*load` | `source/libbsam/ibn_ini.f90:943` |
| `*conv` | `source/libbsam/ibn_ini.f90:1386` |
| `*outp` | `source/libbsam/ibn_ini.f90:1634` |

## Classified internal cases

| Token | Classification | Source |
|---|---|---|
| `*G-C` | internal G-CONTROL option token | `source/libbsam/ibn_ini.f90:231` |

## Reconciliation

Primary dispatch coverage is **complete**.

- `top_level_missing_from_registry`: none
- `top_level_missing_from_source`: none
- `cluster_missing_from_registry`: none
- `cluster_missing_from_source`: none
- `boundary_missing_from_registry`: none
- `boundary_missing_from_source`: none

## Excluded initialization paths

These paths are present in the pinned tree but are not reachable from the active main input sequence.

| Routine or token | Classification | Source |
|---|---|---|
| `PRC_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:69` |
| `OUT_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:75` |
| `OUT_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:79` |
| `STR_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:81` |
| `SET_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:83` |
| `LSR_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:85` |
| `MDL_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:87` |
| `OXD_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:103` |
| `CHE_INI` | unreachable commented-out initializer | `source/bsam/mainf1.f90:119` |
| `DISCRETIZATION` | inactive deprecated source; not called by main input sequence | `source/libbsam/deprecated/dis_ini.f:68` |
| `DELAMINATION` | inactive deprecated source; not called by main input sequence | `source/libbsam/deprecated/dlm_ini.f:33` |
| `GEOMETRY` | inactive deprecated source; not called by main input sequence | `source/libbsam/deprecated/geo_ini.f:90` |
| `LAMINATE` | inactive deprecated source; not called by main input sequence | `source/libbsam/deprecated/lam_ini.f:34` |
| `PROCESS` | inactive deprecated source; not called by main input sequence | `source/libbsam/deprecated/prc_ini.f:64` |
| `SPLINES` | inactive deprecated source; not called by main input sequence | `source/libbsam/deprecated/spl_ini.f:58` |

This closes primary token enumeration only. Record variants, subordinate value dispatches, grammar, and semantic dependencies remain tracked in M1.2 and M1.3.
