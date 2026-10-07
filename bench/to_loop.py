"""Minimal SIMP compliance topology optimisation on the structured MG-PCG (P0-H in-loop measurement).

    python bench/to_loop.py [--n 128] [--iters 30] [--emin 1e-6] [--out receipt.json]

Cantilever 2:1:1 (x = 0 clamped, -z edge load), isotropic E = 1, nu = 0.3, SIMP p = 3, density filter
(radius 1.5 cells), OC update (move 0.2), volume fraction 0.3. Each optimiser iteration solves cold
and warm (from the previous displacement) to compare CG iterations and time; the warm solution is used.
Element energies and the filter run on the host (numpy/scipy): this measures the solver, not a tuned TO code.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fdmgen.fem import element, reference  # noqa: E402
from fdmgen.fem.mgpcg import MGPCG  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=128)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--emin", type=float, default=1e-6)
    ap.add_argument("--vol", type=float, default=0.3)
    ap.add_argument("--tol", type=float, default=1e-6)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    nx, ny, nz = a.n, a.n // 2, a.n // 2
    Ke = element.box_ke(element.isotropic_C(1.0, 0.3), 1.0, 1.0, 1.0)
    fixed, b = reference.cantilever(nx, ny, nz)
    dofs = reference.element_dofs(nx, ny, nz)
    x = np.full((nx, ny, nz), a.vol)
    rmin = 1.5
    k = np.zeros((3, 3, 3))
    for i, j, l in np.ndindex(3, 3, 3):
        k[i, j, l] = max(0.0, rmin - np.sqrt((i - 1) ** 2 + (j - 1) ** 2 + (l - 1) ** 2))
    norm = ndimage.convolve(np.ones_like(x), k, mode="constant")
    filt = lambda f: ndimage.convolve(f, k, mode="constant") / norm
    u = None
    rows = []
    for it in range(1, a.iters + 1):
        xp = filt(x)
        E = a.emin + xp.ravel() ** 3 * (1 - a.emin)
        t0 = time.perf_counter()
        s = MGPCG(nx, ny, nz, Ke, E, fixed)
        setup = time.perf_counter() - t0
        _, cold = s.solve(b, tol=a.tol, maxiter=1500)
        uw, warm = s.solve(b, tol=a.tol, maxiter=1500, x0=u)
        u = uw
        ue = u[dofs]
        ce = np.einsum("ij,jk,ik->i", ue, Ke, ue)
        c = float((E * ce).sum())
        dc = (-3 * xp.ravel() ** 2 * (1 - a.emin) * ce).reshape(nx, ny, nz)
        dc = filt(dc)
        lo, hi = 0.0, 1e9
        while (hi - lo) / (hi + lo + 1e-30) > 1e-4:
            mid = 0.5 * (lo + hi)
            xn = np.clip(x * np.sqrt(np.maximum(-dc, 0) / mid), np.maximum(0, x - 0.2), np.minimum(1, x + 0.2))
            lo, hi = (mid, hi) if filt(xn).mean() > a.vol else (lo, mid)
        change = float(np.abs(xn - x).max())
        x = xn
        row = {"iter": it, "compliance": c, "change": change, "setup_s": round(setup, 3),
               "cold_its": cold["iterations"], "cold_s": round(cold["seconds"], 3),
               "warm_its": warm["iterations"], "warm_s": round(warm["seconds"], 3),
               "grey": float(((xp > 0.05) & (xp < 0.95)).mean())}
        rows.append(row)
        print(f"it {it:3d}  c={c:.5e}  change={change:.3f}  setup={setup:5.2f}s  cold {cold['iterations']:4d} it "
              f"{cold['seconds']:6.2f}s  warm {warm['iterations']:4d} it {warm['seconds']:6.2f}s", flush=True)
    if a.out:
        import warp as wp
        Path(a.out).write_text(json.dumps({"device": wp.get_device("cuda:0").name, "grid": [nx, ny, nz],
                                           "emin": a.emin, "tol": a.tol, "rows": rows}, indent=1))
        np.save(Path(a.out).with_suffix(".npy"), filt(x).astype(np.float32))


if __name__ == "__main__":
    main()
