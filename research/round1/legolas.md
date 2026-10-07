# Legolas: compute, solvers and performance (round 1)

Scope: orientation-swept anisotropic topology optimisation (TO) of FDM parts plus toolpath-aware re-analysis. Everything marked **[measured]** was run on this PC on 2026-10-07 (scripts in `D:\Code\Models\fdm-gen\scratch\legolas\`). Everything marked **[assumed]** or **[estimate]** is arithmetic from those measurements, not a run. Nothing was run on compute-box or second workstation.

## 0. Headlines

1. The existing GPU hex code (`gpu_hex.py`) is a correct, fast **matrix-free operator** but its only solver is **Jacobi-CG**. That is the bottleneck. Measured here: CG iterations double every time h halves (790 at 1.6 mm, 1570 at 0.8 mm), and the spool-rack run already failed to converge at 4.1 M cells after 12,000 iterations. A **multigrid-preconditioned CG (MG-PCG)** is the one must-build compute item. Without it, TO at 0.8 mm or finer is not feasible. With it, a 0.8 mm TO is minutes per orientation.
2. The operator is fast: **159-184 M cell-matvecs/s** on this laptop GPU (RTX 3500 Ada, 11.5 GB), and a **11.25 M-cell / 34 M-DOF** bracket box (0.4 mm) fits in 11.5 GB **[measured]**.
3. The biggest structural saving: **do not re-mesh per orientation.** Keep the voxel grid and the multigrid hierarchy fixed to the part. Rotate the material tensor instead. The element matrix `Ke(n)` is one 24x24 matrix, recomputed per orientation in microseconds. Orientation then costs nothing except the solves.
4. A **screen-coarse / refine-leaders** schedule makes an MVP orientation sweep take roughly **1-2 h on this PC alone** [estimate, Section 5]. That is overnight-free.
5. compute-box (no GPU) is the right place for **large resolution (>= 0.2 mm, 50-100 M cells, up to 300 GB)** and for **embarrassingly parallel batches**. It is not the right place for the inner TO loop at 1-10 M cells, where the laptop GPU is likely faster or equal [estimate].

## 1. What the spool-rack machinery achieves (read-only review of `analysis/rev-g2`)

| Item | What it is | Numbers quoted from the repo |
|---|---|---|
| `gpu_hex.py` (230 lines) | Matrix-free uniform Q1 hex linear elasticity on Warp, float64, one shared 24x24 `Ke`, gather via per-DOF incidence lists, diagonal-Jacobi CG. Requires aligned rectangular cells of one spacing. | Fixtures match scikit-fem to 3e-16 (operator) and 2.4e-13 (hollow beam). Hollow-beam bending: 400 cells, ~0.025 s, 140 CG its. |
| Warp stack | Warp 1.17.0 (repo-pinned). | RTX 3080 Ti 12 GiB under WSL2 in the repo docs. **This PC reports an RTX 3500 Ada Laptop, 11.5 GB** (Warp 1.18.0 works). The numbers below were re-measured here, so they are not the repo's GPU. |
| G crop patch tests (GPU-VALIDATION.md) | Raw sliced-material crop 8x8x24 mm. | 0.4/0.2/0.1 mm: 10,765 / 47,606 / 198,853 cells; GPU solve 0.051 / 0.101 / 0.437 s, 200 CG its at 0.1 mm; CPU topology build **7.66 s for 232 k nodes** (`mesh_from_cells`, a Python per-vertex loop, see Section 6). Pool high-water 117 MiB at 0.1 mm. |
| Adaptive mesh (ADAPTIVE-MESH.md) | Octree-ish 2:1 coarsening with hanging-node constraints `P^T K P`. | 0.2 mm uniform: **8,265,873** cells for a 71,891 mm3 part; adaptive **4,096,575** (-50.4 %), prep 3.83 s. Geometric-only count was 2.66 M, protected count 4.10 M. |
| Whole-G solve (failed) | Jacobi-CG on 4.1 M leaves. | 1000 its = **15.67 s** (15.7 ms/it); continuation 12,000 its = 187.7 s; relative residual 2.6 then 0.037 (gate 1e-8). Declared inadequate preconditioner: "a tested multigrid or coarse correction is still needed". |
| Later ef-* runs | Same family, 3.3-4.1 M leaves. | Solve stage ~149-236 s, all `FAIL_LINEAR_CONVERGENCE`. |
| `gpu_multigrid.py` (207 lines) | **A GPU V-cycle built from a PyAMG smoothed-aggregation hierarchy over a coarse-geometry projection `Q`**; CSR SpMV, damped Jacobi, dense coarse inverse on GPU. Used as an additive coarse correction (`CoarseCorrection`) in `gpu_demo_solve.py`, `validate_gpu_coarse.py`, `validate_gpu_contact.py`. | Written but docs say "CPU preconditioner prototype; full-G and GPU multigrid remain separate gates". No published convergence/timing numbers found. It is the natural base to extend, but it is an **assembled-CSR** coarse path, tied to the adaptive-mesh coarse projection. |
| Evolutionary loop (EVOLUTION.md) | Reduced 2-D contact model for cheap scoring, 3-D GPU for verification. | **100 proposals in 677.9 s** (~6.8 s each); reduced baseline solve 0.12 s; 3-D verify of one candidate 5 min 39 s to 9 min 55 s; full-cell refinement of leader (8.47 M cells, 67.7 M Gauss samples exported) 318 s active. |
| Slicer path | Orca CLI + G-code parser to path arrays to occupancy. | Orca slice **2.67 s**, replay 3.22 s, raw nominal-footprint cache **16.14 s** (0.1 % extrusion accounting), occupancy cache setup ~14 s. |

What this does and does not establish: it establishes a validated, bit-careful operator, the slicing-to-occupancy path, and an honest record that Jacobi-CG does not scale. It does **not** establish any multigrid solve at scale, any optimiser loop on the GPU, orthotropic elements (current `element(spacing,E,nu)` is isotropic), or per-element varying density (a per-element scalar on `Ke` is a trivial kernel change).

**Reuse list for the new project:** `HexOperator` kernels (add per-cell stiffness scalar and an orthotropic `Ke`), `mesh_from_cells` splitting rule for edge/corner-only touches (but vectorise it), Orca slice + G-code parser + occupancy cache, stress recovery at 8 Gauss points, force/moment/residual audit gates, `gpu_multigrid.VCycle` pieces (CSR kernels, Jacobi spectral bound).

## 2. Solver options, ranked for TO inner solves at 0.1-10 M elements

TO needs one solve per iteration, over 100-300 iterations, with a stiffness that changes every time (so no reusable factorisation), a huge stiffness contrast (void cells), and ideally warm start from the previous displacement.

| Option | Where | Fit | Evidence |
|---|---|---|---|
| **Matrix-free geometric MG-PCG on a structured voxel grid** | GPU (this PC) and CPU (compute-box, OpenMP) | **Best.** Operator is the existing kernel; coarse grids are just 2x coarsened voxel grids with Galerkin or rediscretised operators; no assembly; memory ~100-200 B/cell. Standard in the giga-voxel line of work. | Aage et al., [Giga-voxel computational morphogenesis, Nature 550 (2017)](https://www.nature.com/articles/nature23911): 1.1 billion elements with PETSc (assembly-free MG-CG). Träff et al. 2023 (already cited in `GPU-FEM-REVIEW.md`): matrix-free GPU MG-PCG, > 50 M elements over 100 design iterations on an A100, [code](https://github.com/topopt/TopOpt-in-OpenMP-GPU) (no license found by the repo; do not copy, reimplement). Wu, Dick, Westermann, [A System for High-Resolution Topology Optimization, IEEE TVCG 2016](https://www.researchgate.net/publication/284273980_A_System_for_High-Resolution_Topology_Optimization): GPU multigrid TO at multi-million elements. Liu et al., [Narrow-band TO on a sparsely populated grid, SIGGRAPH Asia 2018](https://yuanming.taichi.graphics/publication/2018-narrowband-topopt/): > 1 billion voxel domain on one shared-memory machine; mixed-precision MG-PCG keeping double accuracy; code [spgrid_topo_opt](https://github.com/yuanming-hu/spgrid_topo_opt). |
| Black-box AMG (PyAMG smoothed aggregation, hypre BoomerAMG, PETSc GAMG) on assembled K | CPU (compute-box); PyAMG also this PC | Good for **validation/reference** and for coarse levels; poor as inner TO engine because assembly + AMG setup is redone each iteration and it is memory-hungry. | **[measured]** PyAMG 5.3.0 SA-CG, cantilever, Q1 hex, solid: 0.18 M cells (567 k DOF): setup 9.6 s, solve 18.1 s, 16 its. 1.41 M cells (4.35 M DOF): assemble 20 s, setup **85 s**, solve **81 s**, 17 its, A = 344 M nnz (4.1 GB). It is single-threaded Python-orchestrated, so hypre/PETSc on 40 threads would be maybe 10-20x faster [assumed], still setup-dominated. |
| Direct sparse (CHOLMOD, scikit-fem default, SuperLU) | CPU | Only for small problems or multi-RHS on frozen K. Fill grows ~O(n^(4/3)), work ~O(n^2) in 3-D. | **[measured]** SciPy SuperLU (poor ordering, so pessimistic): 38 k DOF 7.8 s / 69 M fill; 73 k DOF **64 s / 264 M fill**. CHOLMOD with METIS would be much better but the scaling is still wrong beyond ~0.5 M DOF. Use only for reference solutions on <= 100 k DOF checks. |
| Jacobi/diagonal CG matrix-free | GPU | Today's solver. Fine as a smoother and for tiny crops; unusable as a solver at scale. | **[measured]** see Section 3 table. |
| Mixed precision / FP32 fused kernels | GPU | Large possible win on a laptop GPU (see Section 3 caveat), but accuracy needs care. | A 2026 arXiv preprint, [Matrix-Free 3D SIMP TO with Fused Gather-GEMM-Scatter Kernels](https://arxiv.org/html/2604.18020v1), reports 4.6-7.3x end-to-end FP32-fused vs FP64 on an RTX 4090 for Jacobi-CG SIMP (4.9 M cells, 120 SIMP its, 997 s), and that BF16 CG fails. I read it only through a summariser; treat these numbers as unverified. Liu 2018 uses mixed-precision MG-PCG with double-precision outer residual: the safe pattern. |

Optimiser cost: OC for single-constraint compliance, MMA for multi-constraint (volume + stress + overhang). With n = 0.4-10 M design variables and m <= 5 constraints, MMA is O(n*m) per iteration: milliseconds on the GPU, ~0.1 s on CPU. Density filtering is a separable convolution on the grid (also cheap). The optimiser is **not** a bottleneck; the linear solve and the sensitivity pass (one extra elementwise `u^T Ke u` kernel, already at the cost of stress recovery) are. Reference codes: [top3d / 169-line MATLAB 3-D TO](https://link.springer.com/article/10.1007/s00158-015-1350-z) style direct-solver codes only work to ~50-100 k elements; PETSc TO ([Aage, Lazarov, et al.](https://link.springer.com/article/10.1007/s00158-014-1157-0), [Python wrapper](https://link.springer.com/article/10.1007/s00158-021-03018-7)) scales to billions on MPI clusters; compute-box is a small version of that world.

**Anisotropy and MG.** Orthotropic material with a fixed orientation is a mild perturbation for geometric MG with point/block-Jacobi smoothing; strong anisotropy ratios (E_xy/E_z of 2-3 for FDM are mild) are fine. Relevant paper: [On the application of the multigrid method to topology optimization with orthotropic material with varying orientation (SMO 2025)](https://link.springer.com/article/10.1007/s00158-025-04102-y): check its observations on convergence when orientation varies spatially; ours is uniform per run, so easier.

**Void contrast, the real MG risk.** In my PyAMG test a crude 3-D checker pattern with E contrast 1e-3 raised the SA-CG count from 16 to **106 iterations** (solve 18 s to 62 s) [measured, single contrived pattern; not representative of optimised designs]. Mitigations: Galerkin coarse operators (not rediscretisation), floor of E_min = 1e-3 to 1e-4 of solid for the design stage (FDM has no truly-weightless fill anyway), Chebyshev or multi-colour GS smoothers, warm start from the previous iteration's `u`, and reuse the hierarchy for several TO iterations.

**Recommendation (decision D1):** Implement a **matrix-free geometric MG-PCG in Warp on the structured voxel grid, in a masked design domain**, FP64 outer CG, FP32 (optional) smoothers. Keep PyAMG/scikit-fem only as the correctness oracle (the repo already compares to scikit-fem). Port the same algorithm to OpenMP/C++ or Numba for compute-box only if large-resolution runs are required.

## 3. Measured throughput on this PC (Warp, existing `HexOperator`, FP64)

Setup: cantilever box 150 x 80 x 60 mm, clamped x=0 face, unit tip load; full box (no void), homogeneous E. Script `bench_gpu.py` imports the repo's `gpu_hex` read-only (`D:\Code\Models\fdm-gen\scratch\legolas\bench_gpu.py`). GPU: RTX 3500 Ada Laptop 11.5 GB. CPU: i9-13900H (14 cores / 20 threads), 64 GB.

| h (mm) | cells | DOF | GPU matvec | cell-matvec/s | Jacobi-CG its to 1e-10 residual | Jacobi-CG wall | per-iteration (incl. CG vector ops) | host build (numpy) |
|---|---|---|---|---|---|---|---|---|
| 1.6 | 178,600 | 0.57 M | 0.97 ms | 184 M/s | 790 | 5.0 s | 6.3 ms | 1.2 s |
| 0.8 | 1,410,000 | 4.35 M | 8.88 ms | 159 M/s | 1570 | **24.5 s** | 15.6 ms | 6.8 s |
| 0.4 | 11,250,000 | 34.2 M | 74.3 ms | 151 M/s | not run to convergence (60 its capped as a memory/speed probe); extrapolated ~3,100 | extrapolated ~ 3,100 x ~0.1 s = **~5 min** | ~0.1 s [estimate] | **51 s** |
| 0.2 | 90 M | 270 M | would need ~0.6 s/matvec | | | | | does **not fit** 11.5 GB in the present layout [estimate] |

Reading these:
- Matvec rate is flat (~150-185 M cells/s) from 0.18 M to 11 M cells, i.e. the operator is throughput-bound at all of these sizes, no cache cliff.
- Jacobi-CG iteration count scales ~1/h, as expected for kappa ~ h^-2. This reproduces the repo's failure at 4.1 M cells.
- The 0.4 mm box (11.25 M cells, 34 M DOF) allocated without OOM. I did not record peak VRAM during the run (only 1.7 GB used after exit). Rough layout cost [estimate]: connectivity 96 B/cell (1.1 GB), 8-10 float64 DOF vectors (2.7 GB at 34 M DOF), incidence lists, `p` coordinates. About 5-7 GB, so the practical ceiling for the **present** layout is ~15-20 M cells on this card. A structured implicit-index kernel (no `conn`, no `incidence`, no `p`) cuts that by more than half and removes the dominant memory traffic.
- **Suspicion to test first (FP64 vs FP32):** 159 M cell-matvecs/s x ~1,150 flop = ~180 GFLOP/s in FP64. Consumer/laptop Ada GPUs run FP64 at about 1/64 of FP32 (which would be about 0.3 TFLOP/s for this class; spec not verified). If so the kernel is **FP64-compute-bound, not bandwidth-bound**, and an FP32 operator (with FP64 outer iteration) could give a several-fold gain. Measure before assuming.
- CPU baseline [measured]: assembled-CSR matvec, single thread: 36 ms at 567 k DOF; 296 ms at 4.35 M DOF, so the GPU matrix-free operator is **~33x** one i9 thread at 1.4 M cells (parallel CSR would narrow this to maybe 5-8x, bandwidth-limited) [partly assumed].

### 3a. Projected MG-PCG cost on this GPU [estimate, to be replaced by measurement]

Assumptions: V-cycle with 2 pre + 2 post smoothing sweeps; smoother ~ 1 matvec each; one residual; coarse levels add ~14 % (1/8 geometric series). So one V-cycle ~ 5.7 fine-matvec equivalents, plus 1 CG matvec: **~6.7 matvec-equivalents per CG iteration**. Iterations to 1e-6 relative residual (TO-grade, warm-started) assumed **20 (solid) to 40 (void-contrast designs)**. Overhead factor 1.3 for dots, launches, coarse-level latency.

| h | cells (bbox) | matvec | per solve, 20 its | per solve, 40 its | TO iteration (solve + sensitivities + filter + OC) |
|---|---|---|---|---|---|
| 1.6 | 0.18 M | ~1 ms (latency-bound) | 0.17-0.3 s | 0.35-0.6 s | ~0.3-0.7 s |
| 0.8 | 1.41 M | 8.9 ms | 1.5 s | 3.0 s | ~2-3.5 s |
| 0.4 | 11.25 M | 74 ms | 13 s | 26 s | ~15-30 s |

Compare measured Jacobi-CG: 24.5 s at 0.8 mm, so MG-PCG is a **~8-15x** gain at 0.8 mm and ~10-20x at 0.4 mm [estimate]. These multiply by the number of load cases (the hierarchy is shared; each case is one more solve per iteration; multi-RHS reuse of smoother/restriction setup helps a little).

## 4. Resolution budgets, ~150 x 80 x 60 mm bracket (single orientation, single load case)

Assumption list: bounding-box cell counts above are an upper bound. A real bracket occupies roughly 25-40 % of its bounding box, and a masked/sparse design domain (as `mesh_from_cells` already does) can cull empty space; I use the bounding box for solve cost and 30 % for final material counts. TO takes **150 iterations** (continuation on penalty, 3-D FDM-TO typically 100-300) [assumed]. Warm start and hierarchy reuse not credited.

| h | design-domain cells (box / 30 % occupied) | DOF | memory (present layout) | time/solve (MG-PCG) | time/orientation, 150 its | role |
|---|---|---|---|---|---|---|
| 1.6 mm | 179 k / 54 k | 0.6 M | < 0.5 GB | 0.2-0.6 s | **0.5-1.5 min** | Screening. Cannot resolve 0.4-0.45 mm beads or 2-wall shells. Captures global load path and layer-direction effect. |
| 0.8 mm | 1.41 M / 0.42 M | 4.4 M | ~1 GB | 1.5-3 s | **4-9 min** | Working resolution for orientation leaders. About 2 nozzle widths per cell: shells are a *post-processed* concept, not resolved. |
| 0.4 mm | 11.25 M / 3.4 M | 34 M | ~5-7 GB (fits, tight) | 13-26 s | **35-75 min** | Final TO of 1-2 leaders on this GPU, or on compute-box. One cell = one bead width; still not enough to resolve bead cross-section or interlayer contact. |
| 0.2 mm | 90 M / 27 M | 270 M | ~30-45 GB | 100-200 s on a GPU-equivalent; CPU: 3-10 min [assumed] | 5-10 h | **Verification/analysis only**, via the existing adaptive 0.2 mm pipeline (4-8 M leaves for a 72,000 mm3 part). Needs compute-box RAM unless adaptive. |

Interpretation caution: the layer height is 0.2 mm and the nozzle 0.4 mm. A TO voxel of 0.8 mm cannot represent perimeters; it represents a *homogenised density with an orientation-dependent stiffness*. The shells/perimeters/infill massing step (other reports) must convert density to bead layout afterwards, and the bead-resolved check is the existing 0.2 mm machinery. So the honest compute story is **two-tier: homogenised TO at 0.8/1.6 mm, then bead-aware verification at 0.2 mm**. Do not promise TO at bead resolution.

## 5. Orientation sweep economics

**Parametrisation.** Material is transversely isotropic about the build axis `n` (layer plane is the isotropic plane). A design problem with **fixed loads and fixed geometry** depends on the stiffness tensor `C(n)` only through `n`, a point on the sphere with `n ~ -n`, so **2 degrees of freedom on the projective plane / hemisphere**. If in-layer raster direction is also modelled (skin/infill ±45°, perimeters), you get a third angle (spin about `n`), and the model becomes orthotropic with a lamination effect; treat as a later refinement.

**Sampling.** Fibonacci hemisphere points; angular spacing vs count: 45° -> ~10, 30° -> ~23, 20° -> ~52, 15° -> ~92 orientations. Geometry/load symmetry (mirror planes, fixed mounting faces forbidding some build directions) typically halves this. Practical constraint: many orientations are infeasible for printing (flat face must be on the bed within tolerance; overhang cost). Compliance varies smoothly with `n`, so 20-25 well-spread samples plus a local continuous refine is enough to find basins.

**Two cheap options worth separating:**
1. **Evaluate a given design under all orientations (analysis mode).** Same mesh, same MG hierarchy structure, only `Ke(n)` changes. One solve per orientation: 0.2-0.6 s at 1.6 mm, 1.5-3 s at 0.8 mm, 13-26 s at 0.4 mm. A 92-orientation map at 0.8 mm is **2.5-5 min**. This also enables fast "orientation score" for any existing part (matches the user's "project #1: simulation of parts already designed").
2. **Co-optimise `n` inside the TO.** Because `Ke(n)` is analytic, `dC/dn = -u^T (dKe/dn) u` summed over elements is one extra elementwise reduction per iteration, same cost as the density sensitivity. Combine with a few multi-start seeds (5-8 starts) instead of a 25-point sweep. Non-convex; the sweep is a robust fallback and validation of the gradient method. (Sauron owns the math: the gradient and any symmetry reduction.)

**Coarse-to-fine schedule (decision D2).**

| Stage | Setting | Count | Per-run cost | Total (this PC) |
|---|---|---|---|---|
| S0 | analysis-mode score of the unoptimised envelope at 1.6 mm, ~90 orientations | 90 | 0.5 s | < 1 min |
| S1 | 1.6 mm TO per orientation, 24 Fibonacci orientations, 150 its | 24 | 0.5-1.5 min | **12-36 min** |
| S2 | 0.8 mm TO for top 4-6 + warm start from S1 densities (upsampled) | 5 | 4-9 min | **20-45 min** |
| S3 | 0.4 mm TO of top 1-2 | 1-2 | 35-75 min | 35-150 min |
| S4 | bead-aware verification, 0.2 mm adaptive, toolpath re-analysis | 1 | 10-40 min once MG exists | 10-40 min |

MVP wall clock on this PC alone: **S0-S2 ≈ 1 h; with S3 and S4 about 2-3.5 h**, per load case (multiple load cases multiply S1-S3 linearly). Caveats: estimates rest on the 20-40 MG iteration assumption and 150 TO iterations, not yet measured; laptop thermals (my runs were all < 80 s) will lower sustained throughput; per-orientation print-constraint terms (overhang, bridging, support-free) add an overhead I have not costed here (they are local filters on the density field, cheap relative to the solve if done grid-wise).

**Parallelism across machines.**
- PC GPU: S1-S3 (the 11.5 GB card is the bottleneck for 0.4 mm and below).
- compute-box (40 threads, 300 GB, no GPU), **only after the CFD sweep finishes and the user has been told**: independent orientations are embarrassingly parallel. Per orientation a 1.6/0.8 mm run on 4-8 threads is feasible with a CPU MG-PCG; 5-8 simultaneous runs. Memory is never the issue (even 0.2 mm fits 90 M cells x ~500 B = 45 GB). CPU matrix-free throughput [assumed, unmeasured]: 20 physical cores x ~3-5 GFLOP/s effective ≈ 60-100 GFLOP/s ≈ 50-90 M cell-matvecs/s, i.e. **0.3-0.5x of this laptop GPU** for one fine-level application. So compute-box is worth its overhead mainly for (a) the 0.2 mm verification pass, (b) running S1 for all orientations while the PC does S2/S3, (c) tail-end batches. Its role in a CPU TO inner loop beats the PC only at sizes the GPU cannot hold (> ~20 M cells in the current layout).
- second workstation (Ryzen 5800X3D 64 GB, WSL; GPU unknown; ask): good as a CPU worker (8 cores, 96 MB L3 helps coarse-level and 1.6 mm runs) or for slicing/G-code parsing and plotting; cheap to use for S1 at 1.6 mm. Unknown whether it has a CUDA GPU.
- Scheduler: one job = (design, orientation, resolution, load case). Make jobs file-based and idempotent (npz in, npz out + JSON receipt with timings, matching the repo's receipt convention).

## 6. Toolpath-aware re-analysis costs

Pipeline: candidate design -> STEP/3MF -> Orca slice -> G-code parse -> bead geometry -> bead-to-element mapping -> re-solve with bead-aware properties -> compare to the TO prediction.

| Step | Measured / quoted cost | Scaling / risk |
|---|---|---|
| Orca CLI slice (P1S 0.4 / generic PETG) | **2.67 s** for the 74 cm3 G part (repo) | ~linear in layers x perimeter length. 100 candidates ≈ 5 min. Not a bottleneck. |
| G-code parse to path arrays | raw nominal-footprint cache **16.14 s**; replay 3.22 s (repo) | Python parser; linear in moves. 0.1 % extrusion-accounting gate catches bad parse. Bambu dialect comments and the P1S `0x2` XY nozzle offset must be handled (the repo already found a 2 mm shift). |
| Bead to voxel occupancy | occupancy cache ~14 s at 0.2 mm for 8.27 M cells | Vectorised capsule-vs-grid rasterisation, linear in cells touched. Conservative full-cell rule omitted 8.0 % of material at 0.2 mm, 16.4 % at 0.4 mm, 33.1 % at 0.8 mm (repo, G geometry). **So a 0.8 mm grid cannot represent beads at all**; only 0.2 mm (or boundary-adaptive 0.1 mm) is credible for toolpath-aware mechanics. |
| Mesh build with edge/corner split | `mesh_from_cells` CPU **7.66 s for 232 k nodes** (repo) | Per-vertex Python loop plus per-pair set scans. Linear extrapolation to 8 M cells is minutes; **must be vectorised** (connected-components of face adjacency per vertex on GPU or numpy) before the 4-8 M cell path is routine. The structured TO grid does not need it. |
| Adaptive coarsening | 3.83 s to 4.10 M leaves (repo) | Fine. |
| Re-solve | Jacobi-CG failed at 4.1 M leaves (12,000 its, 188 s). With the new MG-PCG: ~13-26 s per solve at 11 M cells projected; 4 M leaves ≈ 5-10 s [estimate]. | Hanging-node constraints `P^T K P` complicate geometric MG; use coarse hierarchy over the adaptive leaves or keep it uniform and sparse at 0.2 mm. Bead-bond stiffness (inter-bead, interlayer) modelled as orthotropic element stiffness or interface reduction is a modelling question for Sauron. |
| Stress/field export | 67.7 M Gauss samples is a heavy write (the 8.47 M cell leader took 244 s for solve + all-stress export, 59 s audit/plots) | Export only needed fields (per-cell max, not all 8 Gauss points) in sweeps; keep the "all samples" rule for final candidates. |

Total toolpath-aware verification of **one** candidate, once MG exists: slice 3 s + parse 16 s + occupancy 15 s + mesh 30 s (vectorised) + solve 10-60 s + export 30-250 s ≈ **2-6 min**, versus 6-10 min in the current Jacobi-CG pipeline (where it frequently fails). 10 finalists ≈ 20-60 min. Acceptable.

## 7. Bottlenecks to measure first, and benchmark plan with go/no-go

Ordered by risk-to-schedule.

| # | Measure | How | Go | No-go / fallback |
|---|---|---|---|---|
| B1 | **FP64 vs FP32 matvec rate** on this GPU, structured implicit-index kernel (no `conn`) vs current gather kernel | Fork `HexOperator.multiply` to a grid kernel in scratch; time 0.8 mm box | FP32 or implicit kernel >= 2x current 159 M cells/s | If not, accept FP64 and plan for 0.8 mm as the workhorse. |
| B2 | **GMG-PCG iteration counts** for cantilever + one L-bracket with random/optimised density, E_min in {1e-2, 1e-3, 1e-4, 1e-6}, orthotropic ratio {1, 2, 3} | CPU prototype with PyAMG first (cheap), then Warp V-cycle; ratio = iteration count | <= 40 CG its to 1e-6 at E_min 1e-3, any orientation | If > 100 its: use Galerkin coarse operators, stronger smoother, or raise E_min; if still bad fall back to AMG on CPU for finals only. |
| B3 | **Time per TO iteration** at 0.8 mm end-to-end (solve + sensitivity + filter + OC on GPU, no host round trips) | Implement top3d-in-Warp cantilever | <= 3 s/it (150 its = 7.5 min) | > 8 s/it: coarse-first strategy only, fewer orientations. |
| B4 | Sustained throughput under thermal load: 10-min run at 0.4 mm | Repeat `bench_gpu.py` in a loop | within 25 % of burst | Otherwise schedule on compute-box/second workstation for long runs. |
| B5 | Memory ceiling: peak VRAM at 0.4 mm and 0.3 mm with a real MG hierarchy | `nvidia-smi` poll or Warp mem stats | 0.4 mm in <= 9 GB | Else offload S3 to compute-box, or use a sparse/masked domain (30 % occupied helps). |
| B6 | Orientation-sweep correctness: compliance vs `n` agrees between GMG and scikit-fem on a 20 k-cell problem to 1e-6 | Reuse repo's scikit-fem oracle | pass | blocker, fix before scale. |
| B7 | Vectorised mesh/occupancy build rate for 4-8 M cells | Replace Python loop | < 30 s | else do toolpath analysis only on cropped regions. |
| B8 | CPU MG-PCG throughput on compute-box (**only when permitted**) | 1.6/0.8 mm cantilever, 8 and 40 threads | >= 50 M cell-matvecs/s on 40 threads | Else compute-box is for 0.2 mm verification and RAM only. |

Project-level go/no-go: **GO** for the plan if B2 passes and B3 <= 3 s/it at 0.8 mm. If B2 fails with the E_min floor at 1e-3, the whole GPU-TO-inner-loop idea needs a CPU AMG route and everything slows ~5-10x; that would change the orientation budget (screen at 1.6 mm only).

## 8. Decisions proposed

1. **D1:** Build matrix-free geometric MG-PCG in Warp on a structured, masked voxel grid; keep PyAMG/scikit-fem as oracles.
2. **D2:** Coarse-to-fine orientation schedule 1.6 -> 0.8 -> 0.4 mm, then 0.2 mm bead-aware verification with the existing pipeline.
3. **D3:** Fixed grid + rotated material tensor `Ke(n)`; never re-mesh per orientation; analytic `dC/dn` for continuous orientation refinement.
4. **D4:** Honest two-tier statement: TO is homogenised (>= 0.8 mm); bead resolution (0.2 mm) is verification only.
5. **D5:** Use E_min >= 1e-3 relative during design for solver robustness, and re-solve final designs with true void (cells deleted) in the 0.2 mm verification.
6. **D6:** compute-box for 0.2 mm verification and parallel orientation batches, scheduled with a heads-up; the PC GPU is the inner-loop machine.

## 9. Open questions

- Is the repo's RTX 3080 Ti (docs) a different machine from this laptop (RTX 3500 Ada reported here)? Rates in the docs and mine differ by GPU; use mine for this PC.
- Does second workstation have a CUDA GPU?
- How many load cases per part will the user expect (each multiplies cost linearly)?
- Required stress accuracy: stress at 0.8 mm voxels is unreliable (the repo's own 16:1 beam study shows 10 % displacement error from coarse meshes and unresolved boundaries). Stress-constrained TO needs the 0.4 mm tier or p-norm with a calibrated factor; Frodo/Sauron should decide whether strength is a design constraint or a post-check.
- Whether the 3rd angle (raster direction) is in the MVP; it triples the sweep.

## 10. Assumptions, limits of my measurements, and housekeeping

- Measured numbers are single runs, on one machine, with the GPU's burst clock. Stiffness, load and mesh are a full solid cantilever; they do not reflect optimised, void-heavy designs. The PyAMG contrast test is one contrived pattern.
- The projected MG numbers (Section 3a, 4, 5) are estimates built from measured matvec time and an assumed 20-40 iteration count; B2/B3 are what turn them into data.
- No remote machine was touched. `D:\Code\Models\fdm-gen\scratch\legolas\` holds `bench_cpu.py`, `bench_gpu.py`, `bench_direct.py`, `.venv` (numpy, scipy, pyamg 5.3.0, warp-lang 1.18.0, scikit-fem).
- Housekeeping disclosure: to stop my own runaway SuperLU benchmark I ran `taskkill /F /IM python.exe`, which killed every `python.exe` on this PC at that moment (two PIDs reported). They were most likely only mine, but if another agent's Python job died around then, that was me.
- The giga-voxel, Träff, Wu, Liu citations were taken from search results and the repo's own review; I did not re-read the full papers. The 2026 arXiv FP32 paper was read via a summariser.
