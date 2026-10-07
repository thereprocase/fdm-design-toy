"""Matrix-free hex-elasticity matvec benchmark: the inner kernel of CG / multigrid smoothing.

    python bench_matvec.py warp  [sizes...]     # NVIDIA GPU via Warp
    python bench_matvec.py numba [sizes...]     # CPU, all cores, via Numba

Same algorithm on both, the node-based gather used by the spool-rack `gpu_hex` operator but on
a structured grid (no connectivity arrays): one thread per node computes its 3 rows of
y = sum_e rho_e K_e x_e over its (up to 8) incident elements, so there are no atomics or races.
Structured n^3 grid of 8-node hexes, 24x24 element stiffness (E=1, nu=0.3, 2x2x2 Gauss),
SIMP-like per-element density scale. FP32 and FP64. Reports cell-matvecs/s and ||y||.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time

import numpy as np


def hex_ke(E=1.0, nu=0.3):
    lam = E * nu / ((1 + nu) * (1 - 2 * nu)); mu = E / (2 * (1 + nu))
    D = np.zeros((6, 6)); D[:3, :3] = lam; D[np.arange(3), np.arange(3)] += 2 * mu; D[3:, 3:] = np.eye(3) * mu
    corners = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]], float)
    g = np.array([0.5 - 0.5 / np.sqrt(3), 0.5 + 0.5 / np.sqrt(3)])
    K = np.zeros((24, 24))
    for x in g:
        for y in g:
            for z in g:
                dN = np.zeros((8, 3))
                for a, (cx, cy, cz) in enumerate(corners):
                    fx = x if cx else 1 - x; fy = y if cy else 1 - y; fz = z if cz else 1 - z
                    sx = 1 if cx else -1; sy = 1 if cy else -1; sz = 1 if cz else -1
                    dN[a] = [sx * fy * fz, fx * sy * fz, fx * fy * sz]
                B = np.zeros((6, 24))
                for a in range(8):
                    B[0, 3 * a] = dN[a, 0]; B[1, 3 * a + 1] = dN[a, 1]; B[2, 3 * a + 2] = dN[a, 2]
                    B[3, 3 * a] = dN[a, 1]; B[3, 3 * a + 1] = dN[a, 0]
                    B[4, 3 * a + 1] = dN[a, 2]; B[4, 3 * a + 2] = dN[a, 1]
                    B[5, 3 * a] = dN[a, 2]; B[5, 3 * a + 2] = dN[a, 0]
                K += B.T @ D @ B / 8.0
    return K, corners.astype(np.int32)


KE, CORNERS = hex_ke()


def inputs(n, dtype):
    rng = np.random.default_rng(42)
    x = rng.standard_normal(3 * (n + 1) ** 3).astype(dtype)
    rho = (1e-3 + rng.random(n ** 3) ** 3).astype(dtype)  # SIMP-like contrast
    return x, rho


def reference(n, x, rho):
    """Element-by-element numpy reference (small n only)."""
    m = n + 1
    y = np.zeros(len(x), np.float64)
    for ex in range(n):
        for ey in range(n):
            for ez in range(n):
                nd = [((ex + c[0]) * m + ey + c[1]) * m + ez + c[2] for c in CORNERS]
                dof = np.array([3 * a + k for a in nd for k in range(3)])
                y[dof] += rho[(ex * n + ey) * n + ez] * (KE @ x[dof].astype(np.float64))
    return y


def run_warp(sizes, reps):
    import warp as wp
    wp.config.quiet = True
    wp.init()
    dev = wp.get_device("cuda:0")
    out = {"device": dev.name, "backend": f"warp {wp.config.version}"}

    def make(dt):
        @wp.kernel
        def mv(n: int, ke: wp.array2d(dtype=dt), cor: wp.array2d(dtype=int), rho: wp.array(dtype=dt),
               x: wp.array(dtype=dt), y: wp.array(dtype=dt)):
            i = wp.tid()
            m = n + 1
            ix = i // (m * m); iy = (i // m) % m; iz = i % m
            a0 = dt(0.0); a1 = dt(0.0); a2 = dt(0.0)
            for a in range(8):
                ex = ix - cor[a, 0]; ey = iy - cor[a, 1]; ez = iz - cor[a, 2]
                if ex >= 0 and ex < n and ey >= 0 and ey < n and ez >= 0 and ez < n:
                    r = rho[(ex * n + ey) * n + ez]
                    s0 = dt(0.0); s1 = dt(0.0); s2 = dt(0.0)
                    for b in range(8):
                        nb = ((ex + cor[b, 0]) * m + (ey + cor[b, 1])) * m + (ez + cor[b, 2])
                        for d in range(3):
                            xv = x[3 * nb + d]
                            col = 3 * b + d
                            s0 = s0 + ke[3 * a, col] * xv
                            s1 = s1 + ke[3 * a + 1, col] * xv
                            s2 = s2 + ke[3 * a + 2, col] * xv
                    a0 = a0 + r * s0; a1 = a1 + r * s1; a2 = a2 + r * s2
            y[3 * i] = a0; y[3 * i + 1] = a1; y[3 * i + 2] = a2
        return mv

    for name, npdt, wdt in (("fp32", np.float32, wp.float32), ("fp64", np.float64, wp.float64)):
        k = make(wdt)
        ke = wp.array(KE.astype(npdt), dtype=wdt, device=dev)
        cor = wp.array(CORNERS, dtype=int, device=dev)
        for n in sizes:
            xh, rh = inputs(n, npdt)
            x = wp.array(xh, dtype=wdt, device=dev); rho = wp.array(rh, dtype=wdt, device=dev)
            y = wp.zeros(len(xh), dtype=wdt, device=dev)
            nodes = (n + 1) ** 3
            wp.launch(k, dim=nodes, inputs=[n, ke, cor, rho, x, y], device=dev); wp.synchronize()
            yh = y.numpy().astype(np.float64)
            t = time.perf_counter()
            for _ in range(reps):
                wp.launch(k, dim=nodes, inputs=[n, ke, cor, rho, x, y], device=dev)
            wp.synchronize()
            dt_s = (time.perf_counter() - t) / reps
            rec = {"cells": n ** 3, "ms": dt_s * 1e3, "Mcell_s": n ** 3 / dt_s / 1e6, "norm": float(np.linalg.norm(yh))}
            if n <= 24:
                ref = reference(n, xh, rh); rec["rel_err"] = float(np.linalg.norm(yh - ref) / np.linalg.norm(ref))
            out[f"{name}_{n}"] = rec
            print(f"warp  {name} n={n:4d} cells={n**3:>12,}  {dt_s*1e3:9.3f} ms  {n**3/dt_s/1e6:9.1f} Mcell/s  |y|={rec['norm']:.8e}"
                  + (f"  relerr={rec['rel_err']:.1e}" if "rel_err" in rec else ""), flush=True)
    return out


def run_numba(sizes, reps):
    import numba as nb
    out = {"device": platform.processor() or platform.machine(), "threads": nb.get_num_threads(),
           "backend": f"numba {nb.__version__}"}

    def make(npdt):
        @nb.njit(parallel=True, fastmath=True)
        def mv(n, ke, cor, rho, x, y):
            m = n + 1
            for i in nb.prange(m ** 3):
                ix = i // (m * m); iy = (i // m) % m; iz = i % m
                a0 = npdt(0.0); a1 = npdt(0.0); a2 = npdt(0.0)
                for a in range(8):
                    ex = ix - cor[a, 0]; ey = iy - cor[a, 1]; ez = iz - cor[a, 2]
                    if ex >= 0 and ex < n and ey >= 0 and ey < n and ez >= 0 and ez < n:
                        r = rho[(ex * n + ey) * n + ez]
                        s0 = npdt(0.0); s1 = npdt(0.0); s2 = npdt(0.0)
                        for b in range(8):
                            nbb = ((ex + cor[b, 0]) * m + (ey + cor[b, 1])) * m + (ez + cor[b, 2])
                            for d in range(3):
                                xv = x[3 * nbb + d]
                                col = 3 * b + d
                                s0 += ke[3 * a, col] * xv
                                s1 += ke[3 * a + 1, col] * xv
                                s2 += ke[3 * a + 2, col] * xv
                        a0 += r * s0; a1 += r * s1; a2 += r * s2
                y[3 * i] = a0; y[3 * i + 1] = a1; y[3 * i + 2] = a2
        return mv

    for name, npdt in (("fp32", np.float32), ("fp64", np.float64)):
        k = make(npdt)
        ke = KE.astype(npdt)
        for n in sizes:
            x, rho = inputs(n, npdt)
            y = np.zeros_like(x)
            k(n, ke, CORNERS, rho, x, y)
            yh = y.astype(np.float64)
            t = time.perf_counter()
            for _ in range(reps):
                k(n, ke, CORNERS, rho, x, y)
            dt_s = (time.perf_counter() - t) / reps
            rec = {"cells": n ** 3, "ms": dt_s * 1e3, "Mcell_s": n ** 3 / dt_s / 1e6, "norm": float(np.linalg.norm(yh))}
            if n <= 24:
                ref = reference(n, x, rho); rec["rel_err"] = float(np.linalg.norm(yh - ref) / np.linalg.norm(ref))
            out[f"{name}_{n}"] = rec
            print(f"numba {name} n={n:4d} cells={n**3:>12,}  {dt_s*1e3:9.3f} ms  {n**3/dt_s/1e6:9.1f} Mcell/s  |y|={rec['norm']:.8e}"
                  + (f"  relerr={rec['rel_err']:.1e}" if "rel_err" in rec else ""), flush=True)
    return out


def run_gen(backend, sizes, reps):
    """Kernels from gen_kernels.py: Ke inlined as literals."""
    out = {}
    if backend == "warpgen":
        import warp as wp
        wp.config.quiet = True
        wp.init()
        import genk_warp as G
        dev = wp.get_device("cuda:0")
        out.update(device=dev.name, backend=f"warp {wp.config.version} (inlined Ke)")
    else:
        import numba as nb
        import genk_numba as G
        out.update(device=platform.processor() or platform.machine(), threads=nb.get_num_threads(),
                   backend=f"numba {nb.__version__} (inlined Ke)")
    for name, npdt in (("fp32", np.float32), ("fp64", np.float64)):
        k = getattr(G, f"mv_{name}")
        for n in sizes:
            xh, rh = inputs(n, npdt)
            nodes = (n + 1) ** 3
            if backend == "warpgen":
                wdt = wp.float32 if name == "fp32" else wp.float64
                x = wp.array(xh, dtype=wdt, device=dev); rho = wp.array(rh, dtype=wdt, device=dev)
                y = wp.zeros(len(xh), dtype=wdt, device=dev)
                call = lambda: wp.launch(k, dim=nodes, inputs=[n, rho, x, y], device=dev)
                sync = wp.synchronize
                call(); sync(); yh = y.numpy().astype(np.float64)
            else:
                y = np.zeros_like(xh)
                call = lambda: k(n, rh, xh, y)
                sync = lambda: None
                call(); yh = y.astype(np.float64)
            _ = 0
            t_warm = time.perf_counter()
            while time.perf_counter() - t_warm < float(os.environ.get("WARM_S", "0")) or _ < 2:
                call(); sync(); _ += 1
            t = time.perf_counter()
            for _ in range(reps):
                call()
            sync()
            dt_s = (time.perf_counter() - t) / reps
            after = float(np.linalg.norm((y.numpy() if backend == "warpgen" else y).astype(np.float64)))
            assert abs(after - np.linalg.norm(yh)) <= 1e-5 * after, ("result changed during timing", after)
            rec = {"cells": n ** 3, "ms": dt_s * 1e3, "Mcell_s": n ** 3 / dt_s / 1e6, "norm": float(np.linalg.norm(yh))}
            if n <= 24:
                ref = reference(n, xh, rh); rec["rel_err"] = float(np.linalg.norm(yh - ref) / np.linalg.norm(ref))
            out[f"{name}_{n}"] = rec
            print(f"{backend:8s} {name} n={n:4d} cells={n**3:>12,}  {dt_s*1e3:9.3f} ms  {n**3/dt_s/1e6:9.1f} Mcell/s  |y|={rec['norm']:.8e}"
                  + (f"  relerr={rec['rel_err']:.1e}" if "rel_err" in rec else ""), flush=True)
    return out


if __name__ == "__main__":
    backend = sys.argv[1]
    sizes = [int(a) for a in sys.argv[2:]] or [20, 100, 160, 200]
    reps = int(os.environ.get("REPS", "20"))
    if backend in ("warpgen", "numbagen"):
        res = run_gen(backend, sizes, reps)
    else:
        res = run_warp(sizes, reps) if backend == "warp" else run_numba(sizes, reps)
    res["host"] = "redacted"
    print("RESULT " + json.dumps(res), flush=True)
