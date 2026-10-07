"""Mixed-precision geometric multigrid-preconditioned CG for structured-grid elasticity (Warp).

Outer: FP64 conjugate gradient (FP64 operator, residuals, dot products).
Preconditioner: one FP32 V-cycle per outer iteration:
  - levels by 2x coarsening of an (nx, ny, nz) element grid; coarse operators are exact Galerkin
    (R A P) built element by element (galerkin.py), the default; `coarse="rediscretize"` keeps the
    mean-of-children re-discretisation (fails on high-contrast designs: 53-225 iterations measured);
  - Chebyshev smoothing preconditioned by Jacobi, degree `cheb_degree`, same polynomial pre and post
    (keeps the V-cycle symmetric, so CG stays valid);
  - trilinear prolongation, restriction = its transpose; fixed DOFs injected to coarse levels;
  - coarsest level: dense inverse on the host (FP64), applied once per V-cycle.
PLAN P0-H: the mixed solve must match a pure-FP64 solve to <= 1e-6 relative; see bench/p0h_gate.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import warp as wp

from . import galerkin, reference
from .warp_structured import (HELPERS, cast_32_64, cast_64_32, diag_elem_f32, dot64,
                              matvec_elem_f32, operator_module)

H32, H64 = HELPERS[np.float32], HELPERS[np.float64]


@dataclass
class Level:
    nx: int
    ny: int
    nz: int
    scale: float
    E: wp.array
    fixed: wp.array
    fixed_np: np.ndarray
    dinv: wp.array = None
    Kel: wp.array = None      # Galerkin element matrices (levels >= 1), flat n*576 FP32
    Kel_np: np.ndarray = None
    lmax: float = 0.0
    work: dict = field(default_factory=dict)

    @property
    def nnode(self):
        return (self.nx + 1) * (self.ny + 1) * (self.nz + 1)

    @property
    def ndof(self):
        return 3 * self.nnode


class MGPCG:
    def __init__(self, nx, ny, nz, Ke, E, fixed, device="cuda:0", coarsest_dofs=3000, cheb_degree=3,
                 lmax_iters=12, lmin_ratio=30.0, coarse="galerkin"):
        self.dev = wp.get_device(device)
        self.mod = operator_module(Ke)
        self.Ke = Ke
        self.deg = cheb_degree
        self.lmin_ratio = lmin_ratio
        self.coarse = coarse
        E = np.asarray(E, np.float64)
        fixed = np.asarray(fixed, np.int32)
        self.fine64 = (wp.array(E, dtype=wp.float64, device=self.dev),
                       wp.array(fixed, dtype=wp.int32, device=self.dev))
        self.levels: list[Level] = []
        lv = Level(nx, ny, nz, 1.0, wp.array(E.astype(np.float32), dtype=wp.float32, device=self.dev),
                   wp.array(fixed, dtype=wp.int32, device=self.dev), fixed)
        self.levels.append(lv)
        while lv.ndof > coarsest_dofs and lv.nx % 2 == 0 and lv.ny % 2 == 0 and lv.nz % 2 == 0 \
                and min(lv.nx, lv.ny, lv.nz) >= 4:
            nxc, nyc, nzc = lv.nx // 2, lv.ny // 2, lv.nz // 2
            Ec = wp.zeros(nxc * nyc * nzc, dtype=wp.float32, device=self.dev)
            wp.launch(H32["coarsen_E"], dim=nxc * nyc * nzc, inputs=[nxc, nyc, nzc, lv.E, Ec], device=self.dev)
            fc = lv.fixed_np.reshape(lv.nx + 1, lv.ny + 1, lv.nz + 1, 3)[::2, ::2, ::2].reshape(-1).copy()
            prev = lv
            lv = Level(nxc, nyc, nzc, lv.scale * 2.0, Ec, wp.array(fc, dtype=wp.int32, device=self.dev), fc)
            if coarse == "galerkin":
                if prev.Kel_np is None:
                    lv.Kel_np = galerkin.first_coarse(E, Ke, prev.nx, prev.ny, prev.nz)
                else:
                    lv.Kel_np = galerkin.next_coarse(prev.Kel_np, prev.nx, prev.ny, prev.nz)
                lv.Kel = wp.array(lv.Kel_np.reshape(-1), dtype=wp.float32, device=self.dev)
            self.levels.append(lv)
        for lv in self.levels:
            for name in ("x", "r", "d", "t", "z"):
                lv.work[name] = wp.zeros(lv.ndof, dtype=wp.float32, device=self.dev)
            dg = wp.zeros(lv.ndof, dtype=wp.float32, device=self.dev)
            if lv.Kel is not None:
                wp.launch(diag_elem_f32, dim=lv.nnode, inputs=[lv.nx, lv.ny, lv.nz, lv.Kel, lv.fixed, dg], device=self.dev)
            else:
                wp.launch(self.mod.diag_float32, dim=lv.nnode,
                          inputs=[lv.nx, lv.ny, lv.nz, wp.float32(lv.scale), lv.E, lv.fixed, dg], device=self.dev)
            lv.dinv = wp.zeros_like(dg)
            wp.launch(H32["inv"], dim=lv.ndof, inputs=[dg, lv.dinv], device=self.dev)
        for lv in self.levels[:-1]:
            lv.lmax = self._power(lv, lmax_iters) * 1.1
        c = self.levels[-1]
        if c.Kel_np is not None:
            A = galerkin.assemble_dense(c.Kel_np.astype(np.float64), c.nx, c.ny, c.nz, c.fixed_np)
        else:
            A = reference.assemble(c.nx, c.ny, c.nz, Ke, c.E.numpy().astype(np.float64), c.fixed_np, c.scale).toarray()
        for lv in self.levels:
            lv.Kel_np = None  # host copies no longer needed
        self.coarse_inv = np.linalg.inv(A)  # small (<= coarsest_dofs); one host matvec per V-cycle
        n = self.levels[0].ndof
        self.v64 = {k: wp.zeros(n, dtype=wp.float64, device=self.dev) for k in ("x", "r", "z", "p", "q")}
        self.buf = wp.zeros(1, dtype=wp.float64, device=self.dev)

    # ── primitives ──
    def _A32(self, lv, x, y):
        if lv.Kel is not None:
            wp.launch(matvec_elem_f32, dim=lv.nnode, inputs=[lv.nx, lv.ny, lv.nz, lv.Kel, lv.fixed, x, y],
                      device=self.dev)
            return
        wp.launch(self.mod.matvec_float32, dim=lv.nnode,
                  inputs=[lv.nx, lv.ny, lv.nz, wp.float32(lv.scale), lv.E, lv.fixed, x, y], device=self.dev)

    def _A64(self, x, y):
        lv = self.levels[0]
        wp.launch(self.mod.matvec_float64, dim=lv.nnode,
                  inputs=[lv.nx, lv.ny, lv.nz, wp.float64(1.0), self.fine64[0], self.fine64[1], x, y], device=self.dev)

    def _axpby32(self, n, a, x, b, y, out):
        wp.launch(H32["axpby"], dim=n, inputs=[wp.float32(a), x, wp.float32(b), y, out], device=self.dev)

    def _power(self, lv, iters):
        """Largest eigenvalue of D^-1 A by power iteration (FP32, random start, masked)."""
        rng = np.random.default_rng(0)
        v = wp.array(rng.standard_normal(lv.ndof).astype(np.float32), dtype=wp.float32, device=self.dev)
        wp.launch(H32["mask"], dim=lv.ndof, inputs=[lv.fixed, v], device=self.dev)
        w = lv.work["t"]
        lam = 1.0
        for _ in range(iters):
            nv = float(np.linalg.norm(v.numpy()))
            self._axpby32(lv.ndof, 1.0 / nv, v, 0.0, v, v)
            self._A32(lv, v, w)
            wp.launch(H32["mul"], dim=lv.ndof, inputs=[lv.dinv, w, w], device=self.dev)
            wp.launch(H32["mask"], dim=lv.ndof, inputs=[lv.fixed, w], device=self.dev)
            lam = float(np.dot(w.numpy(), v.numpy()))
            wp.copy(v, w)
        return lam

    def _smooth(self, lv, x, b):
        """Chebyshev(Jacobi) on D^-1 A over [lmax/lmin_ratio, lmax]; x updated in place."""
        lmax = lv.lmax
        lmin = lmax / self.lmin_ratio
        theta, delta = (lmax + lmin) / 2, (lmax - lmin) / 2
        sigma = theta / delta
        rho = 1.0 / sigma
        r, d, t = lv.work["r"], lv.work["d"], lv.work["t"]
        n = lv.ndof
        self._A32(lv, x, t)
        self._axpby32(n, 1.0, b, -1.0, t, r)                         # r = b - A x
        wp.launch(H32["mul"], dim=n, inputs=[lv.dinv, r, d], device=self.dev)
        self._axpby32(n, 1.0 / theta, d, 0.0, d, d)                 # d = D^-1 r / theta
        for _ in range(self.deg):
            self._axpby32(n, 1.0, x, 1.0, d, x)                     # x += d
            self._A32(lv, d, t)
            self._axpby32(n, 1.0, r, -1.0, t, r)                    # r -= A d
            rho_new = 1.0 / (2 * sigma - rho)
            wp.launch(H32["mul"], dim=n, inputs=[lv.dinv, r, t], device=self.dev)
            self._axpby32(n, rho_new * rho, d, 2 * rho_new / delta, t, d)
            rho = rho_new
        wp.launch(H32["mask"], dim=n, inputs=[lv.fixed, x], device=self.dev)

    def _vcycle(self, l, b, x):
        lv = self.levels[l]
        x.zero_()
        if l == len(self.levels) - 1:
            x.assign((self.coarse_inv @ b.numpy().astype(np.float64)).astype(np.float32))
            return
        self._smooth(lv, x, b)
        r, t = lv.work["r"], lv.work["t"]
        self._A32(lv, x, t)
        self._axpby32(lv.ndof, 1.0, b, -1.0, t, r)
        wp.launch(H32["mask"], dim=lv.ndof, inputs=[lv.fixed, r], device=self.dev)
        c = self.levels[l + 1]
        bc, xc = c.work["z"], c.work["x"]
        wp.launch(H32["restrict"], dim=c.nnode, inputs=[c.nx, c.ny, c.nz, r, bc], device=self.dev)
        wp.launch(H32["mask"], dim=c.ndof, inputs=[c.fixed, bc], device=self.dev)
        self._vcycle(l + 1, bc, xc)
        wp.launch(H32["prolong_add"], dim=lv.nnode, inputs=[c.nx, c.ny, c.nz, xc, x], device=self.dev)
        wp.launch(H32["mask"], dim=lv.ndof, inputs=[lv.fixed, x], device=self.dev)
        self._smooth(lv, x, b)

    def _precond(self, r64, z64, use_mg=True):
        lv = self.levels[0]
        if not use_mg:  # Jacobi in FP64-cast form, for comparison
            r32 = lv.work["t"]
            wp.launch(cast_64_32, dim=lv.ndof, inputs=[r64, r32], device=self.dev)
            wp.launch(H32["mul"], dim=lv.ndof, inputs=[lv.dinv, r32, lv.work["z"]], device=self.dev)
            wp.launch(cast_32_64, dim=lv.ndof, inputs=[lv.work["z"], z64], device=self.dev)
            return
        b32 = lv.work["z"]
        wp.launch(cast_64_32, dim=lv.ndof, inputs=[r64, b32], device=self.dev)
        x32 = lv.work["x"]
        self._vcycle(0, b32, x32)
        wp.launch(cast_32_64, dim=lv.ndof, inputs=[x32, z64], device=self.dev)

    def solve(self, b, tol=1e-6, maxiter=500, use_mg=True, verbose=False):
        """Solve A u = b (b zero at fixed DOFs). Returns (u, info)."""
        lv = self.levels[0]
        n = lv.ndof
        x, r, z, p, q = (self.v64[k] for k in ("x", "r", "z", "p", "q"))
        bb = np.asarray(b, np.float64).copy()
        bb[lv.fixed_np != 0] = 0.0
        r.assign(bb)
        x.zero_()
        H = H64
        bnorm = np.sqrt(dot64(r, r, self.buf))
        self._precond(r, z, use_mg)
        wp.copy(p, z)
        rz = dot64(r, z, self.buf)
        hist = []
        t0 = time.perf_counter()
        it = 0
        for it in range(1, maxiter + 1):
            self._A64(p, q)
            alpha = rz / dot64(p, q, self.buf)
            wp.launch(H["axpby"], dim=n, inputs=[wp.float64(alpha), p, wp.float64(1.0), x, x], device=self.dev)
            wp.launch(H["axpby"], dim=n, inputs=[wp.float64(-alpha), q, wp.float64(1.0), r, r], device=self.dev)
            rnorm = np.sqrt(dot64(r, r, self.buf))
            hist.append(rnorm / bnorm)
            if verbose:
                print(f"  it {it:4d}  rel res {rnorm / bnorm:.3e}", flush=True)
            if rnorm / bnorm <= tol:
                break
            self._precond(r, z, use_mg)
            rz_new = dot64(r, z, self.buf)
            wp.launch(H["axpby"], dim=n, inputs=[wp.float64(1.0), z, wp.float64(rz_new / rz), p, p], device=self.dev)
            rz = rz_new
        wp.synchronize()
        t_solve = time.perf_counter() - t0
        u = x.numpy()
        # true residual in FP64
        self._A64(x, q)
        true_res = float(np.linalg.norm(bb - q.numpy()) / np.linalg.norm(bb))
        info = {"iterations": it, "converged": hist[-1] <= tol if hist else False, "rel_res": hist[-1] if hist else None,
                "true_rel_res": true_res, "seconds": t_solve, "levels": [(l.nx, l.ny, l.nz) for l in self.levels],
                "compliance": float(np.dot(bb, u)), "max_disp": float(np.abs(u).max()), "history": hist}
        return u, info
