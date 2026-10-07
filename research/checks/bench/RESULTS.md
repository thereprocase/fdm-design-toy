# Matvec benchmark: compute box (CPU) vs GPUs, FP32 and FP64

**What:** the matrix-free hex-elasticity matrix-vector product, the inner kernel of CG and of
multigrid smoothing (well over 90 % of solver time). Structured n³ grid of 8-node hexes, 24×24
element stiffness inlined as literals, SIMP-like per-element density scale, node-based gather (one
thread per node, no atomics). Identical generated maths on every machine (`gen_kernels.py`).
Correctness: every backend matches an element-by-element numpy reference (relative error 7e-8
FP32, 2e-16 FP64), and result norms agree across machines to all printed digits.
Timing: 2 s warm-up, 200 repetitions (GPU) / 20 (CPU), result re-verified after timing.
Measured 2026-10-07. Warp 1.18.0, Numba 0.68.0.

| Machine (role) | Backend | FP32, M cells/s | FP64, M cells/s | FP32 / FP64 |
|---|---|---:|---:|---:|
| **Second workstation, RTX 3080 Ti 12 GB** (WSL2) | Warp (CUDA) | **≈ 4,500** (flat 1–14 M cells) | **≈ 416** (≈ card FP64 peak) | 10.8× |
| Laptop GPU workstation, RTX 3500 Ada laptop 11.5 GB | Warp (CUDA) | ≈ 1,400 (≈ 2,000 at 1 M cells) | ≈ 238 | 5.9× |
| Compute box, 40 threads of 2× Xeon E5-2698 v4 | Numba, parallel, fastmath | ≈ 61 (at 14 M cells) | ≈ 63 | 1.0× |

Ratios: the 3080 Ti in FP32 is **≈ 74×** the compute box and **≈ 3.2×** the laptop GPU; in FP64
it is ≈ 6.8× the compute box and ≈ 1.75× the laptop.

**Caveats (what this does and doesn't establish):**
- The CPU kernel is straightforward Numba and runs at ~5 % of the CPU's arithmetic peak (it is
  scalar; FP32 gives no gain). A hand-vectorised CPU kernel might be several times faster
  (estimate, not measured). It would still trail the 3080 Ti in FP32 by more than an order of magnitude.
- One kernel, synthetic cube domain, random densities; not a full multigrid cycle, no masked
  real-part domain, no transfer/coarse-grid costs.
- The inlined-constant GPU kernel beats the existing spool-rack `gpu_hex` operator
  (FP64 238 vs 160–184 M cells/s on the same laptop GPU), so it is worth porting.
- During the CPU run the compute box's CFD solver ranks were paused (SIGSTOP/SIGCONT) so the
  benchmark had the cores.

**Implications for the plan:**
- The second workstation's 3080 Ti is the solver workhorse, using **mixed precision**: FP32
  smoothers and V-cycles inside an FP64 outer CG (FP64 residuals and finite-difference checks).
- Matrix-free FP32 needs only tens of bytes per cell, so 12 GB holds far beyond the 0.2 mm truth
  grids (≈ 37 M domain cells for the bracket).
- The compute box is not a useful solver machine for this kernel: it keeps slicing and parsing
  batches, RAM-heavy non-solver work, and CFD.
