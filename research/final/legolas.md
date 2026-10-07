# Legolas final: compute, solvers and performance for `fdm-gen` (round 3, integrated)

This replaces `legolas.md` (kept untouched as the round-1 record). It integrates the reviews by Gandalf, Sauron and Frodo. Where a correct fact conflicts with my round-1 text, the fact wins and the change is listed in the disposition table (section 11).

Tags: **[measured]** = run on this PC (RTX 3500 Ada Laptop 11.5 GB, i9-13900H 14c/20t, 64 GB), scripts in `D:\Code\Models\fdm-gen\scratch\legolas\`. **[repo]** = quoted from `spool-wall-rack/analysis/rev-g2`. **[estimate]** = arithmetic from measured numbers with stated assumptions; not a run. Nothing was run on compute-box or second workstation. Process hygiene: I killed nothing in round 2 or 3; no background processes were started this round (all runs were foreground with timeouts). The round-1 `taskkill /F /IM python.exe` must not recur; only PIDs started by the agent itself may be killed.

Vocabulary: **R1-R4 = resolution tiers** (renamed from my round-1 S0-S4 so they do not collide with Gandalf's pipeline stages S0-S8).

---

## 0. Headlines (changed from round 1)

1. **Multigrid-preconditioned CG (MG-PCG) is still the one must-build compute item, and the evidence is stronger.** On the real bracket body (below) Jacobi-CG needs **9,620 iterations at 1.6 mm** (vs 790 for a solid box) and **fails to converge in 6,000 at 0.8 mm** [measured, arbitrary clamp/load, see 3.3].
2. **The part is the 207.5 x 233.5 x 24 mm G2 bracket, not a 150x80x60 box.** Body volume 171,778 mm3 = **14.8 %** of its bounding box [measured from `designs/rev-g2/print-controls/ef-core-asa-4w-1p6/body-only.stl`]. All budgets are redone for it (section 4). Frodo was right on every number.
3. **The optimiser re-voxelises in the print frame per orientation** (Gandalf, Sauron and Frodo all objected to my fixed grid + rotated tensor). My fixed-grid trick survives only as **analysis mode** for scoring a frozen design. Re-voxelisation is cheap, but my numpy/trimesh voxeliser is not (12-50 s); a faster one is a deliverable.
4. **Compliance does not discriminate orientation** (E_z/E_xy = 0.85-0.92, so E_xy/E_z = 1.09-1.18, not "2-3"). Orientation ranking comes from the **inter-layer traction prescreen plus printability** (overhang/support area, bed contact, bed fit). Compliance is a secondary column and has a noise floor.
5. **Full sphere, not hemisphere**, for anything involving printability. The hemisphere is valid only for pure-stiffness analysis mode.
6. **Cost model now counts solves per iteration**: K load cases (the bracket has two: 12 kg and the one-spool delta), adjoint solves for strength constraints, the robust triple, and contact. Multipliers are tabulated (section 4.3). "1-2 h overnight-free" is withdrawn; ranges per stage are given with excluded items named.
7. **The existing matvec is FP64-compute-bound, now measured:** FP64 peak 207 GFLOP/s vs FP32 14.2 TFLOP/s on this GPU (ratio 69) [measured, `fma.py`]; the operator reaches ~180 GFLOP/s (87 % of FP64 peak). FP32 smoothers are therefore the biggest single speed lever once MG exists.

---

## 1. What the existing spool-rack machinery achieves (unchanged facts, tightened)

| Item | Result [repo unless tagged] |
|---|---|
| `gpu_hex.py` | Matrix-free uniform Q1 hex elasticity on Warp, float64, one shared 24x24 `Ke`, per-DOF incidence gather, **Jacobi-CG only**, face-connected node splitting, 8-Gauss-point stress recovery, contact active set on CPU. Fixtures: operator vs scikit-fem 3e-16; hollow beam 2.4e-13; 400-cell hollow bending ~0.025 s / 140 CG its. |
| Crop patch tests | 0.4 / 0.2 / 0.1 mm: 10,765 / 47,606 / 198,853 cells; GPU solve 0.051 / 0.101 / 0.437 s (200 CG its at 0.1 mm); CPU topology build **7.66 s for 232 k nodes**. |
| Adaptive mesh | 0.2 mm uniform 8,265,873 cells; adaptive 4,096,575 (-50.4 %), prep 3.83 s. Whole-G conservative-voxel omission **8.02 % (0.2 mm), 16.38 % (0.4 mm), 33.09 % (0.8 mm)** (`ADAPTIVE-MESH.md`, "Full-G trials" section; Sauron could not find it by grep, it is in that file's prose). These apply to the *conservative binary voxel rule on sliced material*, not to a density-field TO. |
| Whole-G Jacobi-CG | 4.1 M leaves: 1000 its = 15.67 s (15.7 ms/it); 12,000 its = 187.7 s; residual 2.6 then 0.037 vs gate 1e-8. Rejected. Later `ef-*` runs 149-236 s, all `FAIL_LINEAR_CONVERGENCE`. |
| `gpu_multigrid.py` | PyAMG smoothed-aggregation hierarchy over an adaptive-mesh coarse projection; GPU CSR V-cycle; additive coarse correction. No published timings or convergence numbers; treat as unproven. |
| Evolutionary loop | 100 proposals in 677.9 s (~6.8 s each, reduced 2-D model, baseline solve 0.12 s); 3-D verification of one candidate 5 min 39 s to 9 min 55 s; leader full-cell refinement 318 s active (8.47 M cells, 67.7 M Gauss samples exported). |
| Slicer path | Orca slice 2.67 s; footprint cache 16.14 s; occupancy cache ~14 s; replay 3.22 s. |
| Warp pin | Repo pins **Warp 1.17.0** (`requirements-gpu.txt`), fixtures accepted on that version, on an RTX 3080 Ti under WSL2. My runs used **Warp 1.18.0 on native Windows**. |

What this establishes: a validated operator, a slicing-to-occupancy path, and an honest record that Jacobi-CG does not scale. It does not establish any multigrid result, optimiser loop on GPU, orthotropic elements, or per-cell stiffness scaling.

Reuse list: `HexOperator` kernels (add a class-indexed `Ke` library and per-cell scalar), face/edge/corner splitting rule (vectorise), Orca slice + G-code parser + occupancy cache, 8-point stress recovery, force/moment/residual gates, `gpu_multigrid` CSR kernels and Jacobi spectral-bound code.

---

## 2. Solver options for TO inner solves at 0.1-10 M elements

| Option | Verdict | Evidence |
|---|---|---|
| **Matrix-free geometric MG-PCG, structured masked voxel grid, Warp** | **Build.** Best fit; operator exists. | Giga-voxel TO (Aage et al., [Nature 550, 2017](https://www.nature.com/articles/nature23911), 1.1 billion elements, PETSc); Träff et al. 2023 matrix-free GPU MG-PCG (> 50 M elements over 100 iterations on an A100; [code](https://github.com/topopt/TopOpt-in-OpenMP-GPU), no licence found by the repo, reimplement); Wu, Dick, Westermann, [IEEE TVCG 2016](https://www.researchgate.net/publication/284273980_A_System_for_High-Resolution_Topology_Optimization); Liu et al., [SIGGRAPH Asia 2018](https://yuanming.taichi.graphics/publication/2018-narrowband-topopt/) (mixed-precision MG-PCG keeping double accuracy). |
| Black-box AMG (PyAMG, hypre, PETSc GAMG) on assembled K | Oracle and reference only. | **[measured]** PyAMG SA-CG, solid cantilever box: 0.18 M cells 9.6 s setup + 18.1 s solve (16 its); 1.41 M cells 85 s setup + 81 s solve (17 its), 4.1 GB matrix. Void contrast (striped test pattern, h = 3.2 mm, 22 k cells, tol 1e-8): **15 / 33 / 69 / 142 iterations at E contrast 1 / 1e-2 / 1e-3 / 1e-6**. |
| Direct sparse | Not for inner loop. | **[measured]** SciPy SuperLU: 38 k DOF 7.8 s (69 M fill); 73 k DOF 64 s (264 M fill). CHOLMOD would be better, scaling still wrong beyond ~0.5 M DOF. |
| Jacobi-CG | Smoother and tiny crops only. | Section 3. |
| FP32 / mixed precision | Yes, as smoother/preconditioner with FP64 outer CG and FP64 for gradient checks. | Liu 2018 pattern. A 2026 preprint ([arXiv 2604.18020](https://arxiv.org/html/2604.18020v1)) reports 4.6-7.3x FP32-fused speedup on an RTX 4090 for Jacobi-CG SIMP and BF16 failure; I read it only through a summariser, so unverified. |

Optimiser cost: OC (single constraint) or MMA (multi-constraint) is O(n*m) per iteration, milliseconds on GPU; density filtering is separable convolution. Neither is a bottleneck. The solve(s), adjoint solve(s) and stress recovery are.

Anisotropy and MG: realistic stiffness anisotropy for these materials is **E_xy/E_z = 1.09-1.18** (Bambu TDS via Sauron section 2.2). Ratios of 2-3 are kept only as a stress case for filled/CF materials. The harder case is the **truth stage**: spatially varying C (per-element wall-tangent angle, bond-fraction scaling, class changes, +/-45 alternation resolved at 0.2 mm). B2 must include random per-element angles and a +/-50 % inter-layer stiffness field (see [SMO 2025 multigrid with varying orthotropic orientation](https://link.springer.com/article/10.1007/s00158-025-04102-y)). Coarse operators must be Galerkin or laminate-homogenised (Sauron 2.6), not rediscretised.

**E_min.** Decision changed (Sauron 7, Gandalf 6, Frodo 6/8): the physical justification "FDM has no weightless fill" is **withdrawn**; base infill is 0 % and voids are real. E_min is a solver device only. Default **1e-6** (Sauron), raised only if B2 shows more than 40 MG-CG iterations, with the value recorded in every receipt and the design-vs-zero-ersatz compliance ratio (Sauron I19) as a gate. My measured black-box AMG counts (15/33/69/142 for 1/1e-2/1e-3/1e-6) show the trade is real for AMG; it is untested for geometric MG with Galerkin coarse operators.

---

## 3. Measured throughput on this PC

### 3.1 Solid cantilever box (round-1 data, kept)
Box 150 x 80 x 60 mm, clamped x = 0, tip load, full box, existing `HexOperator`, FP64 [measured, `bench_gpu.py`]:

| h | cells | DOF | matvec | Mcell/s | Jacobi-CG its to 1e-10 | wall | build |
|---|---|---|---|---|---|---|---|
| 1.6 mm | 178,600 | 0.57 M | 0.97 ms | 184 | 790 | 5.0 s | 1.2 s |
| 0.8 mm | 1,410,000 | 4.35 M | 8.88 ms | 159 | 1570 | 24.5 s | 6.8 s |
| 0.4 mm | 11,250,000 | 34.2 M | 74.3 ms | 151 | capped at 60 (probe) | extrapolated ~5 min | 51 s |

The 11.25 M-cell box allocated without OOM in the present layout; I did not log peak VRAM. Estimated layout cost ~5-7 GB, ceiling ~15-20 M cells.

### 3.2 The actual bracket body, masked [measured, `bench_bracket.py`]
`body-only.stl`: extents 207.5 x 233.5 x 24 mm, watertight, volume 171,778 mm3, 14.77 % of box. Voxelised with trimesh (slow), masked cell list into `HexOperator` (arbitrary connectivity is supported):

| h | grid | cells (share of box) | DOF | matvec | Mcell/s | voxelise (trimesh) | unique+build |
|---|---|---|---|---|---|---|---|
| 0.8 mm | 260x292x31 | 376,923 (16.0 %) | 1.28 M | 2.22 ms | 170 | 12.6 s | 1.3 s |
| 0.8 mm, body dilated 4 cells | same | 540,248 (23.0 %) | 1.77 M | 3.20 ms | 169 | 12.6 s | 2.1 s |
| 0.4 mm | 520x585x61 | 2,866,392 (15.4 %) | 9.17 M | 18.1 ms | 158 | 49.4 s | 11.0 s |
| 0.4 mm, body dilated 8 cells | same | 4,179,930 (22.5 %) | 13.1 M | 26.6 ms | 157 | 52.8 s | 16.4 s |

Masked domains keep the full 157-170 M cell/s rate. Voxelisation (trimesh `voxelized().fill()`) is **12-53 s** and is therefore the dominant per-orientation re-voxelisation cost today; a GPU ray-parity or analytic voxeliser must be a P0/P1 deliverable (target under 5 s at 0.4 mm). Dilation was clipped to the original bounding grid, so the "dilated" rows approximate a design domain of ~23 %.

### 3.3 Jacobi-CG on the bracket body [measured, arbitrary BCs]
Clamp: nodes within 3 mm of the lowest-y end; load: -x on the highest-y 1 mm nodes. These are **not** the G2 load cases; they are a stress case for solver behaviour on this geometry.

| h | cells | result |
|---|---|---|
| 1.6 mm | ~47 k | **9,620 iterations**, 4.2 s; recursive residual 1e-11 but true relative residual 4.7e-8 > 1e-8 gate, so `HexOperator.solve` rejects it |
| 0.8 mm | 376,923 | **not converged in 6,000 iterations** (recursive 0.38, true 13.0), 19 s (~3.2 ms/it) |

Relative to the solid box (790 its at 1.6 mm) this long, plate-like, thin-membered body needs ~12x more Jacobi iterations. This mirrors the repo's whole-G failure. It also shows the prescreen's one required FE solve can run **today at 1.6 mm in ~4 s** (the residual gate caveat aside), before MG exists.

### 3.4 FP64 vs FP32 [measured, `fma.py`]
Warp kernel with four independent FMA chains: **FP64 207 GFLOP/s, FP32 14,213 GFLOP/s** (ratio 69, consistent with 1:64). The `HexOperator` matvec does ~1,152 flop/cell x 159-170 M cell/s = 183-196 GFLOP/s, i.e. **~90 % of FP64 peak**: the kernel is FP64-compute-bound. Consequence (estimate): in an MG-PCG with FP64 outer CG (1 FP64 matvec per iteration) and FP32 smoothers/coarse levels (~5.7 matvec-equivalents), per-iteration time falls from 6.7 FP64-equivalents to ~1 + 5.7/(3-6) = 2-3, a **2.2-3.3x** gain; the FP32 limit would be memory-bandwidth. Bandwidth spec of this GPU not verified (action B1).

### 3.5 Rule-check costs [measured, `bench_checks.py`]
2-D Euclidean distance transform 750 x 400 layer: 13 ms (x300 layers = 3.9 s); 3-D EDT on 11.25 M voxels 1.3 s (~11 s at 90 M, extrapolated); 4-cell disc binary erosion 3.3 ms/layer. Negligible beside any solve.

---

## 4. Budgets for the actual bracket

### 4.1 Assumptions
- Bounding box 207.5 x 233.5 x 24 mm (the part is printed with the 24 mm in Z in its natural flat pose; other orientations change the box, see 5.4). Body 14.8 % of box. **Design domain** (the envelope the optimiser may fill) is unknown; I use **25 %** of the box as a planning number (my dilated test gave 22-23 %), range 15-40 %.
- Matvec rate 160 M cell/s [measured]. MG-PCG per solve = 20-40 CG iterations x 6.7 matvec-equivalents x 1.3 overhead = **175-350 FP64 matvec-equivalents** [estimate; unmeasured MG]. FP32 smoothers (3.4) would divide this by ~2-3 [estimate].
- 150-300 optimiser iterations (continuation). Warm start and hierarchy reuse not credited.
- Domain cells at 25 %: 1.6 mm ~0.07 M; 0.8 mm ~0.59 M; 0.6 mm ~1.4 M; 0.4 mm ~4.6 M; 0.4x0.4x0.2 mm ~9.3 M; 0.2 mm ~37 M.

### 4.2 Per-solve cost at 25 % domain (FP64 MG-PCG, estimate)
| Tier | cell size | cells | memory (present layout) | one MG solve |
|---|---|---|---|---|
| R1 | 1.6 mm cubes | 0.07 M | < 0.3 GB | 0.1-0.3 s (latency-bound) |
| R2 | 0.8 mm cubes | 0.59 M | ~0.7 GB | 0.6-1.3 s |
| R3 | 0.4 x 0.4 x 0.2 mm (minimum resolution for the directional shell model, section 7) | 9.3 M | ~5-7 GB (fits tight) | 10-22 s |
| R3' | 0.4 mm cubes | 4.6 M | ~3 GB | 5-11 s |
| R4 | 0.2 mm | 37 M domain / ~22 M body | ~15+ GB | does not fit the present layout; verification uses the existing adaptive 0.2 mm path (4-8 M leaves) |

### 4.3 Solves per optimiser iteration (new; Gandalf 5, Sauron 5, Frodo 5)
| Problem variant | Solves / iteration | Notes |
|---|---|---|
| v1a: compliance + volume + AM filter, non-robust, K = 2 load cases (12 kg, one-spool delta) | **2** | compliance is self-adjoint |
| + wall contact | x1 if contact state is frozen (closed/open from an initial solve, refreshed every 20-30 iterations and checked in R4); **x3-6** if the active set is iterated each design step | repo contact solves took minutes; only the frozen variant is affordable |
| v1b: + two aggregated strength constraints (F_L, F_P), K = 2 | **2 + 2x2 = 6** | one adjoint per aggregated constraint per load case |
| v1b robust (eroded/nominal/dilated) | **18** | robust only in the last continuation stage, or never |
| AM-filter sweep | not a solve: N dependent layer launches forward + adjoint (100-250 layers at 0.6 mm, 300-750 at 0.2 mm), few ms/iteration; must not be one giant kernel | Sauron 4 |

### 4.4 Time per orientation (single GPU, FP64, optimiser iterations 200 for v1a / 300 for v1b) [estimate]
| Tier | v1a (2 solves/it) | v1b non-robust (6/it) | v1b robust (18/it) |
|---|---|---|---|
| R1 1.6 mm | 1-3 min | 4-9 min | 12-27 min |
| R2 0.8 mm | 4-9 min | 18-40 min | 1-2 h |
| R3 0.4x0.4x0.2 mm | 1.2-2.5 h | 6-12 h | not feasible on the laptop |

With FP32 smoothers divide the solve-dominated terms by ~2-3. All of this assumes MG-PCG reaches 20-40 iterations on **this plate-like geometry with void contrast** and per-class Ke; B2 exists to test exactly that. The Jacobi evidence in 3.3 is why that is not a given.

---

## 5. Orientation sweep economics (rewritten)

### 5.1 Parametrisation and sampling
- Stiffness and the inter-layer failure index depend on `n` only through `n (x) n`, so C(n) = C(-n). **Printability does not:** overhang, support, bed contact, internal ceilings and bridges all flip under up/down. Hence **sample the full sphere** for anything with printability (Sauron 1). The hemisphere is valid only for pure-stiffness analysis mode, labelled as such.
- Full-sphere counts (Fibonacci): ~200 for prescreen (about 14 degree spacing); 30 degree spacing ~ 46; for TO only 10-16 directions are expected to survive the prescreen.
- **Spin about the build axis** is a discrete feasibility check at candidate generation (0 and 90 degrees at least, optionally 45), not a solve variable (Frodo 7, Sauron 14): this part's footprint diagonal (~312 mm) exceeds the 256 mm P1S bed, so bed fit and the 18x28 mm exclusion zone can decide the orientation. The raster-angle-like third degree of freedom stays out of the TO sweep.
- Continuous co-optimisation of `n` via analytic `dc/dn` (compliance `c`, self-adjoint: `dc/dn = -sum_e u_e^T (dK_e/dn) u_e`, projected on the tangent plane) is **moved to later research** (Gandalf 7, Sauron 3). It optimises a nearly flat compliance landscape and is incompatible with the layer-wise filters.

### 5.2 Why compliance is not the ranking criterion
Directional modulus varies only ~15 % (Sauron 2.5), and optimised compliance differences between orientations are of the order of the TO local-minimum scatter. Add a noise floor (3-5 perturbed-start repeats per orientation, 3-5x cost of one TO) before reporting any ordering. Ranking columns, in order: (1) printability hard fails and support/overhang area, bed fit and contact; (2) aggregated inter-layer failure index from the traction prescreen; (3) compliance with its noise band.

### 5.3 Tiered schedule (R-tiers), costs for the bracket [estimate unless stated]
| Tier | What | Count | Cost each | Total |
|---|---|---|---|---|
| R0 | Printability prescreen from the mesh normals: overhang/support-area estimate, bed contact, bed fit per spin, ~200 directions | 200 | ms to s | < 1 min |
| R1a | **One isotropic FE solve per load case** on the design domain (1.6 mm; Jacobi-CG works today, ~4 s [measured] but fails the 1e-8 true-residual gate at 9,620 its, so use MG when it exists), then the **analytic inter-layer traction map** over all ~200 directions (Sauron 4.7) | 2 solves + 1 sweep | seconds | < 1 min |
| R1b | v1a TO at 1.6 mm, print-frame voxelisation per orientation | 10-16 survivors | 1-3 min + voxelise 5-15 s | 15-50 min |
| R2 | v1a TO at 0.8 mm (warm-started from R1b densities) | 3-5 | 4-9 min | 12-45 min |
| R3 | v1b (strength aggregates) at 0.8 mm on top 2-3, then 0.4x0.4x0.2 mm v1a on the leader | 1-3 | 18-40 min / 1.2-2.5 h | 1-5 h |
| R4 | Extraction, Orca slice, toolpath rules, PROC-001, 0.2 mm adaptive truth solve with contact and both load cases | 1-3 finalists | slice 3 s + parse 16 s + occupancy ~14 s + mesh (vectorised) ~30 s + solve 10-60 s per case with MG (repo today: 5-10 min, often failing) + export 30-250 s | 10-60 min per finalist |

MVP wall-clock on this PC alone, for the bracket with two load cases: **R0-R2 about 0.5-1.5 h; with R3 and R4 for one leader about 3-8 h** (range reflects MG iteration counts, contact handling and FP32 smoothers). Items excluded from the lower bound: MG development time, contact active-set iteration beyond the frozen variant, thermal throttling (my runs were all under 80 s), user-visible slicing/visualisation. The runner must write a live `progress.json` with an ETA recomputed from measured iteration times so early drift is visible (Frodo 5).

Prescreen acceptance test (Sauron 6): the eventual best TO orientation must lie in the prescreen's top K on the benchmark problems; this costs K full TOs (~1 h at 0.8 mm), schedule it in P1.

### 5.4 Re-voxelisation per orientation
- Required (print-frame layers on grid planes): AM filter, layer erosion for walls, z-erosion for skins, bond fractions, Z quantisation, bed plane as support. A rotated box has a larger bounding grid (up to ~1.5-2x the cells for oblique poses), so budget on the masked design domain, not the box.
- Cost today: trimesh voxelisation 12.6 s at 0.8 mm and 49 s at 0.4 mm; index build 1-16 s. Target under 5 s via a GPU/analytic voxeliser. Geometric MG hierarchy is pure grid coarsening, so rebuilding it per orientation is cheap (seconds).
- The fixed-grid + `Ke(n)` path remains for **analysis mode**: scoring an existing design across orientations at one solve each (R1a numbers). It removes voxelisation noise, which matters because stiffness differences are only a few percent. The 90-orientation analysis map at 0.8 mm costs 90 x ~1 s (MG) = 1.5 min per load case [estimate].

### 5.5 Machines
- **PC GPU**: R1-R3 inner loops (11.5 GB card; masked domains fit up to ~15-20 M cells in the present layout).
- **second workstation**: open whether it has a CUDA GPU (also Gandalf Q1, same question). If it has the RTX 3080 Ti the repo used, it is a second GPU worker and the truth stage can run there; if not, it is a CPU worker (slicing, parsing, plotting, orientation-batch CPU runs at R1) and the PC does both stages.
- **compute-box** (40 threads, 300 GB, no GPU), only after the CFD job ends and the owner is told: **no CPU solver is required for the MVP.** The 0.2 mm adaptive truth solve (4-8 M leaves) fits the 11.5 GB GPU, as it did on the repo's 12 GB card. compute-box becomes useful for (a) RAM-heavy cases beyond ~20 M cells, (b) many independent orientation jobs if a CPU MG-PCG exists. Build that CPU MG-PCG only after the GPU gates pass and only if a measured need appears. My throughput guess for it (0.3-0.5x of this GPU, 50-90 M cell-matvec/s on 40 threads) is **unmeasured**; B8 measures it when permitted. Black-box AMG is not an inner-loop option (section 2).
- Jobs are file-based and idempotent (design, orientation, tier, load case), with receipts recording the Warp version, E_min, solver iterations and seconds.

---

## 6. Toolpath-aware re-analysis costs

| Step | Cost | Note |
|---|---|---|
| Orca slice | 2.67 s [repo] | 100 candidates ~5 min |
| G-code parse to path arrays | footprint cache 16.1 s [repo] | arcs (G2/G3) not handled by the repo parser; the 0.1 % footer gate catches dropped arcs |
| Mapper to per-cell class/angle/bond (Sauron 5.3) | est. 1-3 min for a 74 cm3 part | must be vectorised or Warp-atomics: ~1e8 supersamples (4x4) would take hours in Python loops; bond fraction = per-layer-pair 2-D mask AND (ms) |
| Mesh build with edge/corner splitting | `mesh_from_cells` 7.66 s per 232 k nodes (Python loop; minutes at 8 M cells) | port-and-rewrite; **P0/P1 deliverable** (Gandalf 9), target under 30 s for 4-8 M cells |
| Re-solve | needs MG; with it ~10-60 s per load case at 4 M leaves [estimate], today failing | fractional occupancy needs partial-volume stiffness (E_min or area fraction) in the solver |
| Export | all 8 Gauss samples is a heavy write (67.7 M samples) | sweeps export per-cell maxima; finalists keep all samples (house rule) |
| PROC-001 effective-settings and modifier-role checks | seconds | add to the per-candidate cost (Frodo 9) |
| Rule checks, every layer | M: 4-15 s per candidate (EDT, erosion, voxelise) [measured]; shapely sectioning not measured | cheap enough that no check needs Z-sampling |

Total per finalist once MG exists: ~2-6 min for one load case, ~4-12 min with two load cases and contact; three finalists per generation ~15-40 min (round-1's "2-6 min" was for one case, no contact).

**Solver detail for the truth stage:** a class-indexed Ke library (theta bin 5 degrees, class, bond bin; 4.6 kB each; a 5 degree bin changes C by at most 0.63 % per Sauron's computation) with a 1-byte index per cell beats per-cell C 21 numbers (~2,600 FMA vs ~576 MAC per cell, ~4.5x the work on an FP64-bound kernel). Per-cell C only in stress recovery. Bin the bond fraction (e.g. 8 levels).

---

## 7. What each tier can and cannot enforce (Frodo 3, Gandalf 4, Sauron 8)

| Tier | Cell | Enforces inside the solve | Does not | Output semantics |
|---|---|---|---|---|
| R1 | 1.6 mm | OVH-001 (45 degrees via 1-cell AM stencil on the print-frame grid), frozen interfaces and keep-outs, volume | WALL/GAP/SHELL (features are sub-cell), bridges, bead counts | "printed-solid placement" only |
| R2 | 0.8 mm | same; 2w (0.84 mm) is one cell, so length scale is not resolved | WALL/GAP/SHELL | "printed-solid placement": body = helper (100 %) at handoff |
| R3 | 0.4 x 0.4 x 0.2 mm | **minimum resolution for the directional coating** (2 walls = 2 cells, skins = whole layers); WALL-001/GAP-001 at ~2 cells | bead resolution; robust triple unaffordable | hollow shell massing decided here, leaders only; "massing-aware TO is a leaders-only tier" |
| R4 | 0.2 mm adaptive | nothing (verification); true voids, no ersatz, contact, both load cases | | truth numbers |

At coarse tiers a density-1 cell is faithful only if the handoff to Orca makes every body cell a 100 % helper (0 % sparse infill prints thick regions as a hollow 2-wall shell otherwise). The 16.38 % / 33.09 % omission figures belong to conservative binary voxelisation of sliced material, not to density-field TO, but they confirm the resolution message. The OVH-001 design target is alpha >= 50 degrees from horizontal (45 degree stencil plus margin): the 45 degree filter is the only angle the voxel stencil enforces; the 5 degree margin is an M/T-level check with repair (Frodo-reviewed).

Strength (STR-001): at R1 it is the prescreen field (no extra solve); in design only from R2/R3 as aggregated constraints in v1b (Frodo 10, Sauron D7, Gandalf's roadmap): enforced as a *relative* aggregate at the tiers that can carry it, with absolute strength claims remaining PROVISIONAL post-checks at R4 (raw per-Gauss peaks only at 0.2 mm).

---

## 8. Bottlenecks to measure first: benchmark plan with go/no-go

| # | Measure | How | Go | No-go / fallback |
|---|---|---|---|---|
| B0 | **Warp version parity**: repo fixtures pass on pinned Warp 1.17.0 before any new kernel; 1.18.0 upgrade is a separate re-baseline | run `validate_gpu_hex.py` on both | identical within the repo's tolerances | stay on 1.17.0 (Gandalf 8) |
| B1 | FP64 vs FP32 operator and **bandwidth**: structured implicit-index kernel (no `conn`/incidence/`p`) in FP32 and FP64; actual memory bandwidth of this GPU (not yet fetched) | fork `multiply`, time at 0.8 mm | FP32 or implicit kernel >= 2x current 159 M cell/s | stay FP64, R2 workhorse |
| B2 | **MG-PCG iteration counts** on (i) solid cantilever, (ii) **the bracket body** with its real load cases, (iii) void contrast E_min in {1e-2,1e-3,1e-4,1e-6}, (iv) orthotropic ratio {1.0, 1.15 (realistic), 2-3 (stress)}, (v) random per-element angles and +/-50 % inter-layer stiffness (truth-stage case), (vi) +/-45 layer alternation. Also the **compliance gap to a zero-ersatz re-solve** at each E_min | CPU prototype with PyAMG first, then the Warp V-cycle | <= 40 CG its to 1e-6 at E_min 1e-6 (or 1e-3 with gap documented) on the bracket | > 100 its: Galerkin coarse operators/stronger smoother/raise E_min; else CPU AMG for finals only |
| B3 | Time per TO iteration, end to end on the GPU, bracket at 0.8 mm, 2 load cases | top3d-in-Warp | <= 3 s/it (v1a) | > 8 s/it: coarse-first only, fewer orientations |
| B4 | Sustained throughput under thermal load: 10-min run at 0.4 mm | loop `bench_gpu.py` | within 25 % of burst | move long runs off the laptop |
| B5 | Peak VRAM at 0.4 and 0.4x0.4x0.2 mm with a real hierarchy | Warp memory stats | <= 9 GB | masked domain / offload |
| B6 | Orientation correctness: compliance vs `n` agrees with scikit-fem (20 k cells, 1e-6); **covariance test**: rotate domain, loads and TI axis together by 90 degrees about a grid axis, compliance identical to ~1e-10 (catches R vs R^T bugs that share-the-same-R oracles miss); Mandel/Voigt permutation test (Sauron I9) | | pass | blocker |
| B7 | Vectorised voxeliser (target < 5 s at 0.4 mm) and mesh/occupancy build (< 30 s for 4-8 M cells) | replace trimesh path and Python loops | meets targets | do toolpath analysis on cropped regions |
| B8 | CPU MG-PCG throughput on compute-box | **only when permitted** | >= 50 M cell-matvec/s on 40 threads | compute-box for RAM and batches only |
| B9 | Prescreen validity: eventual best TO orientation within prescreen top K; repeat-run noise floor | 10 TOs at 0.8 mm | holds on benchmark | widen K |
| B10 | FP64 for all finite-difference gradient checks (Sauron I14) and patch tests (I11); FP32 only inside smoothers/preconditioners | policy test | enforced | |

Project gate: **GO** if B2 passes on the bracket and B3 <= 3 s/it at 0.8 mm. If B2 fails at E_min >= 1e-3, the GPU-inner-loop idea slows 5-10x and the plan screens at R1 only. This becomes P0's exit criterion.

---

## 9. Open disputes for the merge (recommended resolution and evidence)

1. **Design-grid resolution ladder** (Sauron D4 0.2 mm; Gandalf 0.6 mm; mine 0.8/1.6/0.4). Resolution: R1 1.6 mm, R2 0.8 mm (relaxed to 0.6 mm if B3 allows), R3 0.4x0.4x0.2 mm for leaders only, R4 0.2 mm adaptive as verification. Evidence: 0.2 mm is 148 M bbox / ~37 M domain cells for this part and does not fit 11.5 GB in the present layout; 0.8 mm cannot represent the 0.84 mm shell; 0.4x0.4x0.2 is the minimum at which the coating is meaningful (2 cells for two walls, whole layers for skins).
2. **E_min.** Resolution: 1e-6 default, raise only if B2 demands, record in receipts, gate with I19. Evidence: black-box AMG counts 15/33/69/142 at contrast 1/1e-2/1e-3/1e-6 (measured, striped pattern); geometric MG untested.
3. **Which machine runs which stage.** PC GPU: R1-R3 and R4 truth (fits 4-8 M leaves). second workstation: GPU truth worker only if it has a CUDA GPU (Q1 unresolved), otherwise CPU worker. compute-box: after CFD and a heads-up; RAM and batches only.
4. **Does compute-box need a CPU solver?** Recommended: no for MVP; build CPU MG-PCG only if B8-gated need appears. Evidence: truth stage fits on GPU; black-box AMG setup alone was 85 s at 1.4 M cells single-threaded; the matrix-free CPU throughput is a guess.
5. **Solves per iteration / problem scope.** Resolution: P1 = v1a, non-robust, frozen contact; strength aggregates (v1b) only on top 2-3 orientations at R2/R3; robust triple at most in the last continuation stage. Evidence: 2 vs 6 vs 18 solves per iteration (4.3).
6. **Per-orientation re-voxelisation vs fixed grid.** Resolution: print-frame voxelisation for all TO; fixed grid + `Ke(n)` only in analysis mode. Evidence: AM filter and coating need layers on grid planes; re-voxelisation is cheap once the voxeliser is fixed.
7. **Orientation ranking.** Prescreen + printability; compliance only with a noise floor. Gandalf's P1-B ("flat ranks first as E3/E1 falls") is a plumbing test of the anisotropy code only.
8. **Hemisphere vs full sphere.** Full sphere for printability; hemisphere only for stiffness analysis mode.
9. **Contact in TO.** Recommended: frozen contact state refreshed every 20-30 iterations, verified in R4. Contested only by cost: iterating the active set inside the design loop multiplies cost 3-6x.
10. **Warp version.** Stay on the pinned 1.17.0 until B0 passes; my 1.18.0 numbers may differ slightly.
11. **Sweep-tier vocabulary.** R1-R4 (resolution tiers) vs Gandalf's S0-S8 (pipeline stages).

---

## 10. Assumptions and limits

- Measured numbers are single runs on one machine at burst clocks. Box/bracket cases use arbitrary clamp/load (not the G2 load cases) and have no contact. The PyAMG contrast test is one contrived pattern at h = 3.2 mm. The MG-PCG numbers are estimates until B2/B3.
- Design-domain occupancy (25 %) is a planning assumption; only the 14.8 % body fraction is measured.
- GPU bandwidth, MG behaviour on the plate-like bracket, CPU matrix-free throughput on compute-box, and shapely sectioning cost are unmeasured.
- Citations (Aage 2017, Träff 2023, Wu 2016, Liu 2018) come from search results and the repo's review; I did not re-read the papers. The 2026 arXiv FP32 paper was read via a summariser.
- New scratch files this round: `bench_bracket.py`, `stlvol.py`, `fma.py`, `bench_checks.py` (round 2) under `D:\Code\Models\fdm-gen\scratch\legolas\`; `.venv` now also has trimesh and numpy-stl.

---

## 11. Review disposition

Legend: A = accepted, P = partly, R = rejected.

### Gandalf on Legolas
| # | Finding | Disposition | Reason / where |
|---|---|---|---|
| 1 | D3 fixed grid vs print-frame layers [critical] | A | Section 5.4, 9.6; fixed grid only for analysis mode |
| 2 | Compliance does not discriminate orientations [critical] | A | 5.2, 5.3 (R0/R1a prescreen first), noise floor |
| 3 | "E_xy/E_z of 2-3" wrong | A | Section 2: realistic 1.09-1.18, 2-3 only as stress case |
| 4 | Minimum resolution for coating; resolution table row | A | Section 7 and 4.2 R3 (0.4x0.4x0.2 mm), "leaders-only tier". Caveat added: omission figures apply to binary conservative voxels |
| 5 | Robust x K multiplier not costed | A | Section 4.3 and 4.4 |
| 6 | D5 E_min vs Sauron 1e-6 | A | Section 2 E_min paragraph, 9.2 |
| 7 | Analytic dC/dn is scope creep | A | 5.1: moved to later research, removed from decisions |
| 8 | Warp version drift | A | B0, dispute 10 |
| 9 | B7 vectorisation not in a phase | A | Section 6 and B7 flagged P0/P1 deliverable |
| 10 | Hardware facts / second workstation GPU open question | A | 5.5, 9.3 (merged Q1) |
| 11 | Stage numbering collides | A | R1-R4 vocabulary throughout |
| 12 | taskkill disclosure | A | Preamble; no recurrence; PIDs only |
| 13 | Fetch actual FP64 spec | P | Measured the FP64:FP32 ratio instead (207 vs 14,213 GFLOP/s, section 3.4); bandwidth spec still to fetch (B1) |

### Sauron on Legolas
| # | Finding | Disposition | Reason / where |
|---|---|---|---|
| 1 | Hemisphere reduction wrong for printability [critical] | A | 5.1, dispute 8 |
| 2 | Fixed grid incompatible with print constraints [critical] | A | 5.4, dispute 6 |
| 3 | dC/dn notation, tangent projection, non-smooth | A | Notation fixed to `c`, tangent-plane note, moved to later research (5.1) |
| 4 | S0 compliance will not discriminate; use inter-layer index | A | 5.2, 5.3 R1a |
| 5 | Cost model omits adjoints and AM sweep | A | 4.3, 4.4 |
| 6 | Realistic ratio 1.09-1.18; truth stage varying C in B2 | A | Section 2; B2 items (iv), (v) |
| 7 | E_min physical justification wrong | P | Justification withdrawn and 1e-6 default adopted; "keep 1e-3 only if B2 needs it" kept as conditional (measured AMG counts) |
| 8 | Coarse-tier semantics: body = helper | A | Section 7 |
| 9 | 16.4 % / 33.1 % omission not found | R | Present in `ADAPTIVE-MESH.md` ("The 0.4 and 0.8 mm whole-G preparations omit 16.38% and 33.09%"); Gandalf also confirmed it in the adaptive-validation JSON. Cited exactly in section 1, with a scope caveat |
| 10 | FP32 only as smoother; FP64 for checks | A | Section 2, B10 |
| 11 | Mandel/Voigt traps; Ke library with bins | A | Section 6 solver detail, B6 |
| 12 | B6 covariance test | A | B6 |
| 13 | taskkill hygiene | A | Preamble |
| 14 | Strength as aggregated constraint; third angle not needed in TO | P | Accepted for third angle (discrete feasibility only, 5.1) and for aggregate at coarse tiers (7); cost of v1b kept explicit in 4.3 and restricted to top 2-3 orientations |

### Frodo on Legolas
| # | Finding | Disposition | Reason / where |
|---|---|---|---|
| 1 | D3 conflicts with printability catalog [critical] | A | 5.4, 7, dispute 6 |
| 2 | taskkill incident; process fix; ask user | A | Preamble (no image-name kills; foreground runs with timeouts); asking the user whether any job died is left to the coordinator |
| 3 | Tier-by-rule enforcement column; hybrid with analytic t(alpha) | A | Section 7 table |
| 4 | Budget was for a box, not the 207.5x233.5x24 bracket | A | Re-measured: 14.77 % body, 376,923 cells at 0.8 mm, Mcell/s 157-170 masked (3.2); sections 4-5 redone |
| 5 | "1 h" omits two load cases, contact, slicing, thermals | A | 4.3, 5.3 (3-8 h MVP, exclusions named, progress.json ETA) |
| 6 | E_min 1e-3 vs 1e-6; measure compliance gap | A | B2 includes the gap; section 2 |
| 7 | Spin about n is not later | A | 5.1 discrete 0/90 feasibility; bed diagonal 312 mm > 256 mm bed |
| 8 | "No weightless fill" not true for MVP | A | Section 2 withdrawn |
| 9 | Add PROC-001 and role checks to per-candidate cost | A | Section 6 |
| 10 | Strength as constraint in design solve at carrying tier | P | Yes as relative aggregate from R2/R3 (v1b), prescreen at R1; absolute claims stay PROVISIONAL post-checks. Cost multiplier is the reason for not putting it in v1a |
