# Legolas on Gandalf (compute / performance review, round 2)

## 1. Verdict
The architecture is sound and its reuse inventory matches what I read in `rev-g2` and measured. It underspecifies compute in three places that decide whether P1 is feasible: the design-grid size, the number of solves per optimiser iteration, and GPU placement of the truth stage. None needs a redesign; each needs numbers, and one decision (per-orientation re-voxelisation) should be accepted in place of my round-1 D3. Evidence: my round-1 benchmarks in `D:\Code\Models\fdm-gen\scratch\legolas\` and `bench_checks.py`.

## 2. Findings

1. **[critical] Section 0 item 5 / S2 (re-voxelise per orientation) vs my round-1 D3 (fixed grid, rotated tensor). I concede most of it.** The AM filter, layer erosion for walls and skins, and z skin erosion all need layers on grid planes; a part-frame grid with a rotated tensor would force non-axis-aligned overhang stencils. Re-voxelising is cheap if vectorised (my numpy host build: 1.2 s at 0.18 M cells, 6.8 s at 1.4 M, 51 s at 11 M). Requested changes: (a) budget on the masked design domain, because a rotated box needs a larger bounding grid (oblique poses up to roughly 1.5-2x cells); (b) record that my fixed-grid plus `Ke(n)` trick survives only as a fast analysis-mode path for a frozen design (Sauron's traction prescreen does the same more cheaply), not as the architecture.

2. **[critical] The design grid size is never stated, and the numbers in the three reports disagree.** Gandalf's schema example has `grid_mm: 0.6` and R3 says "0.6 mm or coarser", but S2 only says z is a multiple of h and XY a fraction or multiple of w. Sauron D4 says 0.2 mm cubes. For a 150x80x60 mm box, 0.2 mm is 90 M cells (about 27 M at 30 % occupancy), roughly 5-10 h per orientation even with a working multigrid (legolas.md section 4, an estimate). Requested change: fix the P1 design grid at 0.6 mm (z = 3 layers). That is 3.3 M bbox cells, about 21 ms per matvec by my measured 159 M cell/s, about 3-8 s per MG solve, and about 10-20 min per orientation per load case (estimates). Use 0.3-0.4 mm for finalists only. Also state that 0.6 mm cannot resolve a 0.84 mm two-wall shell, so the emulator in S3 must be a sub-cell or homogenised shell fraction, not voxel erosion.

3. **[critical] R3 "multigrid before the optimiser" is right but unpriced, and `gpu_multigrid.py` is not the answer yet.** Measured here (RTX 3500 Ada, 11.5 GB, existing `HexOperator`): Jacobi-CG took 790 iterations / 5.0 s at 1.6 mm and 1570 iterations / 24.5 s at 0.8 mm, so iterations double per halving of h. Matvec rate is flat at 159-184 M cell/s from 0.18 M to 11 M cells. The repo's `gpu_multigrid.py` is an assembled-CSR PyAMG coarse correction tied to the adaptive-mesh projection, with no published timings. Requested change: add a P0 acceptance test "MG-PCG at most 40 iterations to 1e-6, structured grid, E_min = 1e-3, orthotropic ratio 0.7-1", and say the structured-grid GMG is new code, not a port. Thresholds are in legolas.md section 7 (B2, B3).

4. **[warning] Solves per optimiser iteration are not stated, and Sauron's D7 conflicts with Gandalf's roadmap.** Compliance with K load cases is K solves per iteration (self-adjoint). Sauron's problem v1 (minimax, two aggregated stress constraints, robust triple design) is 3 x (K + 2) = 12 solves at K = 2, which is 3-6x what the sweep economics assume. Gandalf defers stress to P3. Requested change: P1 states compliance + volume + AM filter only, non-robust (filter and projection for length scale), K solves per iteration; the inter-layer index is evaluated post hoc and in the prescreen.

5. **[warning] Machine placement in S3/S6 rests on the open Q1.** S6 puts the truth stage on "second workstation GPU", yet the brief lists second workstation as a Ryzen 5800X3D with no GPU stated. If second workstation has no CUDA GPU, truth and design both land on this PC's 11.5 GB card. That is feasible (4.1 M adaptive leaves; I ran an 11.25 M-cell box) but serialises the machine. Requested change: resolve Q1 first; default placement meanwhile is PC GPU for both, second workstation and compute-box for CPU batches.

6. **[warning] S3 "compute-box CPU, one orientation per process" has no CPU solver behind it.** The plan lists `[cpu]` as scipy/pyamg. Measured: PyAMG smoothed-aggregation CG on 1.41 M cells took 85 s setup + 81 s solve (single-threaded, 17 iterations, 4.1 GB matrix), and a void-contrast 1e-3 test needed 106 iterations versus 16 for solid. Assembled black-box AMG is not an inner-loop solver. Requested change: either specify a matrix-free CPU MG-PCG (Numba/OpenMP/C++) or restrict compute-box to 0.2 mm verification and RAM-heavy cases (its 300 GB is the real asset), after the CFD job and with a heads-up. Its throughput is unmeasured; my 0.3-0.5x of the laptop GPU is an assumption.

7. **[warning] Section 1.1 `gpu_hex.py` row: a class-indexed `ke` stack is the right call.** Keep it that way. Per-cell full C with 8-Gauss-point B^T C B (Sauron 5.4 offers it) is about 2,600 FMA per cell versus about 576 MAC, around 4.5x the FLOPs, and the present kernel looks FP64-compute-bound (about 180 GFLOP/s achieved; laptop Ada FP64 is about 1/64 of FP32, spec unverified). Requested change: record "class-indexed Ke library" as the decision, with per-cell C only for stress recovery.

8. **[warning] Stage timings are absent from the pipeline table.** From the repo and my runs: Orca slice 2.67 s; raw footprint cache 16.1 s; occupancy cache about 14 s; `mesh_from_cells` 7.66 s per 232 k nodes (a per-vertex Python loop, minutes at 8 M cells); leader refinement 318 s active; full-G Jacobi-CG failed at 12,000 iterations / 188 s. Requested change: add a stage-time column and mark `mesh_from_cells` as port-and-rewrite (vectorised), not just port.

9. **[note] P0-C "bitwise-identical" is unrealistic** for a changed kernel and reduction order. Use the repo's own language (relative operator difference about 3e-16 against scikit-fem).

10. **[note] P1-B ordering test needs a noise floor.** Sauron's TDS data give E_z/E_xy of 0.85-0.92, so compliance differs by at most about 15 %, which is near TO local-minimum scatter. Add 3-5 repeat runs per orientation (under an hour at 0.6 mm) before claiming an ordering. The assumed E3/E1 <= 0.7 sweep is fine as a plumbing test.

11. **[note] Finalist throughput.** At 3 s slice + 16 s parse + about 15 s occupancy, three finalists per generation cost about 2 min before FE; FE (5-10 min today) dominates. This answers Frodo's Q3.

12. **[note] `[gpu]` extra "Warp under WSL".** Warp 1.18.0 imported and ran in a plain Windows venv here. If native Windows is acceptable, the WSL layer can be dropped for the inner loop. Check the repo's reason for WSL2 first (its runs were on the 3080 Ti).

## 3. Keep
- Two FEM roles (design vs truth) with different invariants and `Emin > 0` only in the design role.
- Content-addressed runs and per-stage receipts with failures preserved; they make the solves-per-iteration risk visible and cacheable.
- Port with parity tests, not import. The parity suite doubles as a performance regression suite (record seconds and iteration counts in receipts).
- The slicer generates toolpaths and truth reads G-code (minutes, not hours).
- A discrete orientation set optimised independently and in parallel, matching legolas.md section 5.
