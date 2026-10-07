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
B4/B5 hierarchy VRAM and B10 orientation covariance remain open in #10.

The solver regression in `tests/test_coarse_operator.py` uses CPU Warp and checks
that the dense coarsest inverse actually inverts the first Galerkin operator,
including a masked thin-shell domain. It does not measure bracket convergence.
