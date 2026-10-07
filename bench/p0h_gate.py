"""P0-H solver gate on synthetic domains (PLAN §5 P0-H, issue #4).

    python bench/p0h_gate.py [--sizes 64,128,256] [--out receipt.json]

Cantilever (x = 0 fixed, edge load) on 2:1:1 grids, design fields:
  solid            E = 1 everywhere
  topo(E_min)      a TO-like binary field (smoothed random field, 50 % volume) with void stiffness E_min
materials: isotropic and transversely isotropic (E_z/E_p = 0.87). Mixed precision MG-PCG to 1e-6
(gate) and to 1e-10 (reference); the outer CG is FP64 with FP64 true-residual check, so the 1e-10
solution is FP64-accurate whatever the preconditioner precision. Gate: <= 40 iterations to 1e-6,
compliance and max displacement within 1e-6 relative of the reference.
Real-bracket domain and the <= 3 s per optimiser iteration at 0.8 mm come with the bracket adapter (#7).
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fdmgen.fem import element, reference  # noqa: E402
from fdmgen.fem.mgpcg import MGPCG  # noqa: E402


def topo_field(nx, ny, nz, emin, seed=7):
    """A connected TO-like design: smoothed random field at ~50 % volume, plus a bottom chord that
    carries the load to the clamp, keeping only solid connected to the clamped face (an optimised
    design has no floating islands; islands add ~6 near-free rigid modes each, which no multigrid
    resolves and no real design contains)."""
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    f = np.fft.rfftn(rng.standard_normal((nx, ny, nz)))
    kx = np.fft.fftfreq(nx)[:, None, None]; ky = np.fft.fftfreq(ny)[None, :, None]; kz = np.fft.rfftfreq(nz)[None, None, :]
    k2 = kx ** 2 + ky ** 2 + kz ** 2
    g = np.fft.irfftn(f * np.exp(-k2 * (nx / 6.0) ** 2), s=(nx, ny, nz), axes=(0, 1, 2))
    solid = g > np.median(g)
    solid[:2] = True                                   # clamp plate
    solid[:, :, : max(2, nz // 8)] = True              # bottom chord to the loaded edge
    lab, _ = ndimage.label(solid)
    keep = np.unique(lab[0][lab[0] > 0])
    solid = np.isin(lab, keep)
    return np.where(solid, 1.0, emin).ravel(), float(solid.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="64,128,256")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    import warp as wp
    dev = wp.get_device("cuda:0")
    mats = {"iso": element.isotropic_C(1.0, 0.3), "ti0.87": element.ti_C(1.0, 0.87, 0.35, 0.3, 0.33)}
    rows = []
    for n in [int(s) for s in a.sizes.split(",")]:
        nx, ny, nz = n, n // 2, n // 2
        fixed, b = reference.cantilever(nx, ny, nz)
        fields = [("solid", np.ones(nx * ny * nz), 1.0)]
        for emin in (1e-3, 1e-4, 1e-6):
            E, vol = topo_field(nx, ny, nz, emin)
            fields.append((f"topo_Emin{emin:g}", E, vol))
        for mname, C in mats.items():
            Ke = element.box_ke(C, 1.0, 1.0, 1.0)
            for fname, E, vol in fields:
                t0 = time.perf_counter()
                s = MGPCG(nx, ny, nz, Ke, E, fixed)
                setup = time.perf_counter() - t0
                u6, i6 = s.solve(b, tol=1e-6, maxiter=400)
                u10, i10 = s.solve(b, tol=1e-10, maxiter=1000)
                dc = abs(i6["compliance"] - i10["compliance"]) / abs(i10["compliance"])
                dd = abs(i6["max_disp"] - i10["max_disp"]) / abs(i10["max_disp"])
                row = {"cells": nx * ny * nz, "grid": [nx, ny, nz], "material": mname, "field": fname,
                       "solid_fraction": round(vol, 3), "levels": len(s.levels), "setup_s": round(setup, 2),
                       "iters_1e-6": i6["iterations"], "s_1e-6": round(i6["seconds"], 3),
                       "true_res_1e-6": i6["true_rel_res"], "iters_1e-10": i10["iterations"],
                       "true_res_1e-10": i10["true_rel_res"], "compliance_rel_diff": dc, "maxdisp_rel_diff": dd,
                       "gate_iters": i6["iterations"] <= 40, "gate_accuracy": dc <= 1e-6 and dd <= 1e-6}
                rows.append(row)
                print(f"{nx}x{ny}x{nz} {mname:7s} {fname:16s} lv={len(s.levels)} setup={setup:6.2f}s "
                      f"it6={i6['iterations']:4d} t6={i6['seconds']:7.3f}s tres6={i6['true_rel_res']:.1e} "
                      f"it10={i10['iterations']:4d} dC={dc:.1e} dU={dd:.1e} "
                      f"{'PASS' if row['gate_iters'] and row['gate_accuracy'] else 'FAIL'}", flush=True)
                del s
    receipt = {"what": "P0-H solver gate, synthetic cantilever", "device": dev.name, "warp": wp.config.version,
               "numpy": np.__version__, "python": platform.python_version(), "rows": rows}
    if a.out:
        Path(a.out).write_text(json.dumps(receipt, indent=1))
    print("SUMMARY", sum(r["gate_iters"] and r["gate_accuracy"] for r in rows), "/", len(rows), "pass")


if __name__ == "__main__":
    main()
