# Benchmark receipts (#5, #10, #4)

Run from the project root with the geometry/development dependencies installed.
GPU runs use pinned Warp 1.17.0. Compilation is excluded from matvec timings.

- `python bench/geometry.py --mesh body.stl --h 0.4 --out geometry.json`
  compares scanline and polygon-section occupancy hashes and timings, then times
  node coordinates on a 4 M-cell grid. Omit `--mesh` for a synthetic annulus.
- `python bench/matvec_benchmark.py --device cuda:0 --grid 128,128,128 --seconds 600 --out matvec.json`
  measures synchronized FP32/FP64 operator windows. A CUDA failure produces no GPU receipt.
  `--device cpu --grid 8,4,4 --seconds 1` is a smoke test only.

Long runs belong in named detached tmux sessions, with logs and exit-code files.
For example (choose unused session and output names):

```sh
tmux new-session -d -s solver-fdm-matvec \
  'python bench/matvec_benchmark.py --seconds 600 --out matvec.json > matvec.log 2>&1; result=$?; echo "$result" > matvec.exit'
```

Committed receipts establish local synthetic geometry parity/timing and a small
CPU operator smoke test. They do not establish the real bracket gate, GPU thermal
stability, peak hierarchy VRAM, physical accuracy, or print qualification.
The minimum/first throughput ratio is a diagnostic, not automatic thermal acceptance:
compare sustained 0.4 mm runs with a separately measured burst on the same device.
B4/B5 hierarchy VRAM and the sustained GPU thermal gate remain open in #10.
B10 FP64 reference covariance now passes all 24 proper grid rotations on a
masked non-cubic TI case; this does not establish production GPU rotation parity.

The solver regression in `tests/test_coarse_operator.py` uses CPU Warp and checks
that the dense coarsest inverse actually inverts the first Galerkin operator,
including a masked thin-shell domain. It does not measure bracket convergence.

Real-bracket receipt `receipts/geometry-bracket.json`: the hashed body at 0.4 mm
has exact scanline/section occupancy parity; three local scanline runs take
2.64–2.74 s (measured; this establishes #5 voxeliser timing for that fixture).
The local GPU smoke receipt identifies the actual Quadro T2000, not the larger
GPU described by the original handoff. It is a smoke measurement, not a thermal
gate or a full 0.4 mm hierarchy memory result.

`python bench/domain_audit.py --root <checkout> --out connectivity.json` audits
body connectivity and clamp/load membership. At 3.2 mm, a disconnected loaded
seven-cell island has no full clamp: that resolution is an invalid mechanical
repro. At 1.6 mm the body is node-connected but has five face-connected groups;
at 0.8 mm it is face-connected. Node connectivity does not prove absence of
hinge modes or full rigid-body restraint. See the hashed connectivity receipt.
The bracket runner stops optimisation after a failed true-residual check.

R1 masked-bracket comparison on the actual Quadro T2000 (one cold-start solve,
E_min=1e-6, 0.5 uniform density, h=1.6 mm): degree-40 Chebyshev at the coarsest
level takes 84 CG iterations / 2.90 s; dense solve with `--coarsest-dofs 4000`
takes 56 / 1.84 s. True residuals are 6.4e-7 and 2.4e-7; compliance agrees to
1.17e-10 relative. Setup timings are NOT a fair comparison: the first run
includes compilation (81.84 s), the second uses a warm cache (2.70 s).
This supports investigating the coarsest solve but does not meet the <=40 gate,
and neither R1 run establishes the 0.8 mm per-optimiser-iteration timing gate.
The receipts pin device, precision, inputs and solver settings. Full R2/R3,
E_min/TI sweeps, zero-ersatz gap and sustained/memory benchmarks remain open.

#5 mesh scaling: `--connectivity --node-grid 200,200,100` and
`--connectivity --node-grid 200,200,200` also build full 24-DOF element maps.
Committed local receipts measure node coordinates plus connectivity at 1.53 s
for 4 M cells and 3.20 s for 8 M cells, both below 30 s. They establish structured
mesh build performance for those grids, not imported-mesh repair or physical accuracy.

The 0.4 mm bracket grid cannot run the current full MG hierarchy on this actual
4 GiB GPU. An analytic lower bound from only fine work vectors plus the second
Galerkin level is 4.089 GiB, already above capacity, before masks, diagonals,
other levels and driver memory. See `bracket-04-memory-lower-bound.json`.
This is an allocation estimate, not measured peak VRAM; the requested #10 full
0.4 mm hierarchy and thermal benchmarks need a larger GPU or storage changes.

CPU aggregation pilot (#4): with optional `pyamg==5.3.0` installed, run
`python bench/amg_bracket.py --root <checkout> --out amg.json` in detached tmux.
Limit BLAS/OpenMP threads and wrap the command in an external timeout. The
pilot assembles active cells only, keeps homogeneous constrained rows as
identity, and validates against a sparse direct solve. It compares translation
candidates, six rigid-body candidates, and six candidates with energy-smoothed
interpolation. All use symmetric block Gauss–Seidel smoothing and FP64 CG.
A fixed random seed makes candidate setup reproducible within the same environment.
The diagnostic solve timings include an extra true-residual matvec per iteration.
This experiment tests interpolation on one uniform-density R1 design field;
it is not the mixed-precision GPU gate or an optimisation sweep. Candidate
construction follows the elasticity example in the
[PyAMG examples](https://github.com/pyamg/pyamg-examples/tree/main/linear_elasticity).
