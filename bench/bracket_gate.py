"""P0-H gate on the real spool bracket body (masked domain), plus a first SIMP run inside it.

    python bench/bracket_gate.py --root <spool-wall-rack checkout> [--h 0.503,0.503,0.6] [--iters 40] [--out run.json]

Domain: the E+F handoff body (body-only.stl, print frame), voxelised layer by layer; cells outside the
body have E = 0 (inactive). Design field: SIMP density inside the whole body (PLAN P2 restricts it to
100 % helper volumes; this gate measures the solver on the real geometry).
SOLVER-GATE RESTRAINTS (not the truth model): mounting-bore nodes clamped, wall-face nodes u_x = 0
(bilateral), seat forces from the ported interface loads spread over seat nodes on the bearing side.
Gate: <= 40 CG iterations to 1e-6 and <= 3 s per optimiser iteration (solve + setup) at 0.8 mm.
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
from fdmgen.adapters import spool_bracket as sb  # noqa: E402
from fdmgen.fem import element, reference  # noqa: E402
from fdmgen.fem.mgpcg import MGPCG  # noqa: E402
from fdmgen.geom.voxel import voxelise  # noqa: E402


def build(root, h):
    br = sb.Bracket.load(root)
    occ, g = voxelise(br.mesh(), h=h, multiple=16)
    nx, ny, nz = g.shape
    P = g.node_coords()
    # node activity (any incident body cell)
    act = np.zeros((nx + 1, ny + 1, nz + 1), bool)
    for c in element.CORNERS:
        act[c[0]:c[0] + nx, c[1]:c[1] + ny, c[2]:c[2] + nz] |= occ
    act = act.ravel()
    fixed = np.zeros(3 * len(P), np.int32)
    tol = max(h)
    # mounting bores: axes along installed X at (Y, Z); clamp nodes within the bore radius band over the wall plate
    for name, (Y, Z) in sb.MOUNT_AXES_I.items():
        a0 = br.to_print([0.0, Y, Z]); a1 = br.to_print([sb.WASHER_PLANE_X + 2 * tol, Y, Z])
        d = a1 - a0; L = np.linalg.norm(d); d = d / L
        rel = P - a0; s = rel @ d
        r = np.linalg.norm(rel - np.outer(s, d), axis=1)
        sel = act & (s >= -tol) & (s <= L) & (r <= sb.MOUNT_BORE_R + tol)
        for c in range(3):
            fixed[3 * np.nonzero(sel)[0] + c] = 1
    # wall face: installed X = 0 plane -> roller along the installed X direction (print axis of R row)
    xw = br.to_print([0.0, 0.0, 0.0]); nI = br.vec_to_print([1.0, 0.0, 0.0])
    ax = int(np.argmax(np.abs(nI)))
    wall = act & (np.abs(P[:, ax] - xw[ax]) <= tol / 2)
    fixed[3 * np.nonzero(wall)[0] + ax] = 1
    # seat loads
    b = np.zeros(3 * len(P))
    loads = br.loads_print()
    seats = {}
    for name, (X, Y) in sb.ROD_AXES_I.items():
        c0 = br.to_print([X, Y, 0.0]); dz = br.vec_to_print([0.0, 0.0, 1.0])
        rel = P - c0; s = rel @ dz
        radial = rel - np.outer(s, dz); r = np.linalg.norm(radial, axis=1)
        F = loads[name]; fdir = F / np.linalg.norm(F)
        sel = act & (r >= sb.SEAT_RADIUS[0] - tol) & (r <= sb.SEAT_RADIUS[1] + tol) & \
            ((radial @ fdir) > 0.3 * r) & (fixed[0::3] == 0)
        idx = np.nonzero(sel)[0]
        if len(idx) == 0:
            raise RuntimeError(f"no seat nodes found for {name}")
        for c in range(3):
            b[3 * idx + c] += F[c] / len(idx)
        seats[name] = int(len(idx))
    return br, occ, g, fixed, b, {"seat_nodes": seats, "clamped_nodes": int(fixed[0::3].sum()),
                                  "wall_nodes": int(wall.sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\Code\Models\spool-wall-rack")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--maxiter", type=int, default=2000)
    ap.add_argument("--h", default="0.503,0.503,0.6")
    ap.add_argument("--iters", type=int, default=40)
    ap.add_argument("--vol", type=float, default=0.5)
    ap.add_argument("--emin", type=float, default=1e-6)
    ap.add_argument("--out", default="")
    ap.add_argument("--coarsest-degree", type=int, default=40)
    ap.add_argument("--coarsest-dofs", type=int, default=3000)
    a = ap.parse_args()
    h = tuple(float(v) for v in a.h.split(","))
    t0 = time.perf_counter()
    br, occ, g, fixed, b, info = build(a.root, h)
    nx, ny, nz = g.shape
    print(f"grid {nx}x{ny}x{nz} = {nx*ny*nz:,} cells, body {occ.sum():,} cells ({occ.mean():.1%}), "
          f"body volume {occ.sum()*np.prod(h):.0f} mm3 vs mesh {br.mesh().volume:.0f}; {info}; build {time.perf_counter()-t0:.1f}s",
          flush=True)
    C = element.isotropic_C(1.0, 0.3)
    Ke = element.box_ke(C, *h)
    body = occ.ravel()
    ids = np.nonzero(body)[0]
    dofs = reference.element_dofs(nx, ny, nz)[ids]
    # density filter on the body only (physical radius 1.5 cells of dx)
    r = 1.5 * h[0]
    k = np.zeros((3, 3, 3))
    for i, j, l in np.ndindex(3, 3, 3):
        k[i, j, l] = max(0.0, r - np.sqrt(((i - 1) * h[0]) ** 2 + ((j - 1) * h[1]) ** 2 + ((l - 1) * h[2]) ** 2))
    norm = ndimage.convolve(occ.astype(float), k, mode="constant")
    norm[norm == 0] = 1
    filt = lambda f: ndimage.convolve(f * occ, k, mode="constant") / norm * occ
    x = np.where(occ, a.vol, 0.0)
    u = None
    rows = []
    for it in range(1, a.iters + 1):
        ti = time.perf_counter()
        xp = filt(x)
        E = np.where(body, a.emin + xp.ravel() ** 3 * (1 - a.emin), 0.0)
        t0 = time.perf_counter()
        s = MGPCG(nx, ny, nz, Ke, E, fixed, device=a.device, coarsest_degree=a.coarsest_degree, coarsest_dofs=a.coarsest_dofs)
        setup = time.perf_counter() - t0
        u, sv = s.solve(b, tol=1e-6, maxiter=a.maxiter, x0=u)
        if not sv["converged"] or not np.isfinite(sv["true_rel_res"]) or sv["true_rel_res"] > 1e-6:
            rows.append({"iter": it, "status": "solver_failed", **sv,
                         "setup_s": setup, "total_s": time.perf_counter() - ti})
            print(f"solver failed: true residual {sv['true_rel_res']:.3e}; optimisation stopped", flush=True)
            break
        ue = u[dofs]
        ce = np.einsum("ij,jk,ik->i", ue, Ke, ue)
        c = float((E[ids] * ce).sum())
        dc = np.zeros(nx * ny * nz); dc[ids] = -3 * xp.ravel()[ids] ** 2 * (1 - a.emin) * ce
        dc = filt(dc.reshape(nx, ny, nz))
        lo, hi = 0.0, 1e12
        target = a.vol * occ.sum()
        while (hi - lo) / (hi + lo + 1e-30) > 1e-4:
            mid = 0.5 * (lo + hi)
            xn = np.where(occ, np.clip(x * np.sqrt(np.maximum(-dc, 0) / mid), np.maximum(0, x - 0.2), np.minimum(1, x + 0.2)), 0)
            lo, hi = (mid, hi) if filt(xn).sum() > target else (lo, mid)
        change = float(np.abs(xn - x).max())
        x = xn
        tot = time.perf_counter() - ti
        row = {"iter": it, "compliance": c, "cg_its": sv["iterations"], "solve_s": round(sv["seconds"], 3),
               "setup_s": round(setup, 3), "total_s": round(tot, 2), "inactive_dofs_fine": int(3 * s.levels[0].n_inactive / 3),
               "levels": len(s.levels), "true_res": sv["true_rel_res"], "change": change}
        rows.append(row)
        print(f"it {it:3d} c={c:.5e} cg={sv['iterations']:4d} solve={sv['seconds']:6.2f}s setup={setup:5.2f}s "
              f"total={tot:6.2f}s levels={len(s.levels)} tres={sv['true_rel_res']:.1e}", flush=True)
        del s
    if a.out:
        import warp as wp
        Path(a.out).write_text(json.dumps({"device": wp.get_device(a.device).name, "grid": [nx, ny, nz], "h_mm": h,
                                           "evidence": "measured design-solver gate investigation",
                                           "does_not_establish": "truth-model strength or physical qualification; coarse repros do not establish the 0.8 mm gate",
                                           "warp": wp.__version__, "emin": a.emin,
                                           "coarsest_degree": a.coarsest_degree, "coarsest_dofs": a.coarsest_dofs,
                                           "body_cells": int(occ.sum()), "bc": info, "rows": rows, "gate_converged": all(r.get("status") != "solver_failed" for r in rows),
                                           "problem": sb.problem_dict(br)}, indent=1, default=str))
        np.save(Path(a.out).with_suffix(".npy"), filt(x).astype(np.float32))


if __name__ == "__main__":
    main()
