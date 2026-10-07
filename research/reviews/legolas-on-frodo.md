# Legolas on Frodo (compute / performance review, round 2)

## 1. Verdict
The catalog is the most immediately useful artefact among the reports, and it is well grounded in the repos. From a compute angle almost every rule is cheap; the risk is what goes inside the optimiser (Q4). The proposed day-one in-optimiser list is right except STR-001 as a penalty, which silently adds adjoint solves. Frodo's Q3 is answered below with measurements (`D:\Code\Models\fdm-gen\scratch\legolas\bench_checks.py`).

## 2. Findings

1. **[warning] Section 7 Q4: STR-001 inside the optimiser as a penalty.** An inter-layer stress term needs a per-element stress recovery each iteration (cheap) plus one adjoint solve per aggregated constraint (expensive), multiplied by load cases. At 0.8 mm that is about 2-3 s per added solve per iteration (estimate, legolas.md). Sauron's traction prescreen is analytic and needs no solve per direction. Requested change: day-one in-optimiser set = OVH-001 (AM filter), WALL-001/GAP-001 (length scale), frozen interfaces and keep-outs. STR-001 starts as a post-check and as the orientation prescreen (the "max interlayer tension / allowable" column of the section 5.2 table is one stress field plus a loop over directions). Promote it to a penalty only in the strength stage.

2. **[warning] WALL-001/GAP-001 as "hard (length scale)" via a robust formulation.** Eroded/nominal/dilated triples the solves. For day one, use a density filter plus projection at the 2w radius, then verify on the thresholded design. Measured verification cost: 2D Euclidean distance transform on a 750x400 layer takes 13 ms, so 300 layers (0.2 mm layers over 60 mm) is 3.9 s; a single 3D EDT on 11.25 M voxels takes 1.3 s (about 11 s at 90 M voxels, extrapolated); binary erosion by a 4-cell disc is 3.3 ms per layer. Negligible beside a solve.

3. **[answer to Frodo Q3] Cost of per-layer M checks and T-level parsing.** M level, every layer (the T5 guard), on a part of about 200 mm: voxelise plus per-layer EDT or closing is about 4-15 s per candidate at 0.2 mm in plane; mesh sectioning with shapely is not measured (assume tens of seconds). T level: Orca slice 2.67 s, `plastic_shape` raw footprint cache 16.1 s for a 74 cm3 part, occupancy cache about 14 s (repo EVOLUTION.md/ADAPTIVE-MESH.md), so about 35 s per finalist. Three finalists per generation cost about 2 min of rule checks; the 3D FE (5-10 min each today, Jacobi-CG) is the bottleneck. Yes, the existing cache is fast enough.

4. **[warning] OVH-002 `k_step` and angles other than 45 degrees on a voxel grid (your Q1 to Sauron).** The Langelaar stencil with one-cell reach gives tan(angle) = dx/dz, exactly 45 degrees on cubic cells. Other angles need anisotropic cells or wider stencils, which cost more per layer and add azimuthal grid anisotropy (Sauron I13). Practical route: enforce 45 degrees at V level and treat the 5 degree margin (design alpha >= 50) as an M/T-level check with repair. The catalog should say that V can only enforce what the grid stencil allows.

5. **[warning] SUP-002 and VOID-002 levels.** Flood fill of the void phase is cheap on a voxel grid (scipy label on 11 M voxels, under a second, estimated). SUP-002 (opening >= 6 mm, depth <= 3x) is a morphological or geodesic check taking seconds, but it needs support geometry, which exists only from Orca (T) or a simulated support (M-estimated). V is not available. The table lists V,T; I suggest M(estimated),T.

6. **[note] COOL-001 and WARP-001 as V penalties.** Per-layer perimeter length divided by area is a trivial reduction and fine inside the optimiser. WARP-001's footprint length and brim rules are orientation-level (first layers), so compute them in the orientation ranking, not per iteration.

7. **[note] Section 5.1 stage 3 `fdmgen orient` "PC, minutes".** Fine for the geometric table. The interlayer column needs one FE solve first: today 5 s at 1.6 mm and 25 s at 0.8 mm with Jacobi-CG (measured), faster with multigrid. State the resolution and keep the column PROVISIONAL.

8. **[note] Section 5.1 stage 4 `--budget 20m`.** With the planned solver, 20 minutes buys about 20-40 orientations at 1.6 mm, or only about 3-5 at 0.8 mm (legolas.md, estimates). The CLI should print an estimated cost (cells x iterations x solves per iteration) before starting, since users cannot judge it.

9. **[note] PROC-001 and `fdmgen selftest`.** Both cost one slice (about 3 s). Cheap and valuable. Also record parse seconds in the selftest receipt so Orca-version changes that slow parsing are caught.

## 3. Keep
- The V/M/T/P levels per rule and "report the highest level actually reached": expensive T checks run only on finalists, cheap V/M checks on everything.
- Tiers on every value and the PROVISIONAL banner; compute results inherit the same honesty requirement.
- Rules in units of w and h, and one angle convention (alpha from horizontal) shared with Sauron section 4.6. The two shell-thickness formulas agree (Frodo SHELL-001 with phi = 90 - alpha; Sauron t(alpha)); only the assumed w differs (0.45 vs 0.42), so give the catalog a single w source.
- Repair deltas reported (T10) and per-layer sampling instead of 10 Z samples (T5): per-layer checks cost seconds, so there is no performance excuse for sampling.
- The inventory that points at existing code (`selfsupport`, `bore_td`, `verify_mixed_plate`, the `gpu_demo_slice` effective-settings check): reuse over rewrite.
