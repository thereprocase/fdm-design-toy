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
from .warp_structured import (HELPERS, cast_32_64, cast_64_32, cg_p_64, cg_xr_64, copy_slot_64, dense_matvec_f32,
                              diag_elem_f32, dot64, dot_slot_64, matvec_elem_f32, operator_module, set_slot_64)

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
    Kel: wp.array = None      # Galerkin element matrices (levels >= 2), flat n*576 FP32
    Ef: wp.array = None       # level 1: fine element multipliers; operator generated on the fly
    Kel_np: np.ndarray = None
    lmax: float = 0.0
    work: dict = field(default_factory=dict)
    n_inactive: int = 0

    @property
    def nnode(self):
        return (self.nx + 1) * (self.ny + 1) * (self.nz + 1)

    @property
    def ndof(self):
        return 3 * self.nnode


class MGPCG:
    def __init__(self, nx, ny, nz, Ke, E, fixed, device="cuda:0", coarsest_dofs=3000, cheb_degree=3,
                 lmax_iters=12, lmin_ratio=30.0, coarse="galerkin", coarsest_degree=40):
        self.dev = wp.get_device(device)
        self.mod = operator_module(Ke)
        self.Ke = Ke
        self.deg = cheb_degree
        self.lmin_ratio = lmin_ratio
        self.coarse = coarse
        self.coarsest_degree = coarsest_degree
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
            # Dirichlet DOFs on the coarse level: any fixed fine DOF (same component) inside the coarse node's
            # interpolation support. Injection alone loses small clamps (bores) and leaves the coarse problem
            # floating in rigid-body modes (measured: singular coarsest operator on the spool bracket).
            mf = wp.array(lv.fixed_np.astype(np.float32), dtype=wp.float32, device=self.dev)
            mc = wp.zeros(3 * (nxc + 1) * (nyc + 1) * (nzc + 1), dtype=wp.float32, device=self.dev)
            wp.launch(H32["restrict"], dim=(nxc + 1) * (nyc + 1) * (nzc + 1), inputs=[nxc, nyc, nzc, mf, mc],
                      device=self.dev)
            fc = (mc.numpy() > 0).astype(np.int32)
            prev = lv
            lv = Level(nxc, nyc, nzc, lv.scale * 2.0, Ec, wp.array(fc, dtype=wp.int32, device=self.dev), fc)
            if coarse == "galerkin":
                if prev is self.levels[0]:
                    lv.Kel_np = None            # level 1 is generated on the fly from the fine multipliers
                elif prev is self.levels[1]:
                    lv.Kel_np = galerkin.second_coarse_from_fine(E, Ke, self.levels[0].nx, self.levels[0].ny,
                                                                 self.levels[0].nz)
                else:
                    lv.Kel_np = galerkin.next_coarse(prev.Kel_np, prev.nx, prev.ny, prev.nz)
                if lv.Kel_np is None:
                    lv.Ef = prev.E          # level 1: Galerkin on the fly from the 8 children
                else:
                    lv.Kel = wp.array(lv.Kel_np.reshape(-1), dtype=wp.float32, device=self.dev)
            self.levels.append(lv)
        for lv in self.levels:
            for name in ("x", "r", "d", "t", "z"):
                lv.work[name] = wp.zeros(lv.ndof, dtype=wp.float32, device=self.dev)
            dg = wp.zeros(lv.ndof, dtype=wp.float32, device=self.dev)
            if lv.Ef is not None:
                wp.launch(self.mod.diag_g1, dim=lv.nnode, inputs=[lv.nx, lv.ny, lv.nz, lv.Ef, lv.fixed, dg],
                          device=self.dev)
            elif lv.Kel is not None:
                wp.launch(diag_elem_f32, dim=lv.nnode, inputs=[lv.nx, lv.ny, lv.nz, lv.Kel, lv.fixed, dg], device=self.dev)
            else:
                wp.launch(self.mod.diag_float32, dim=lv.nnode,
                          inputs=[lv.nx, lv.ny, lv.nz, wp.float32(lv.scale), lv.E, lv.fixed, dg], device=self.dev)
            # masked domains: DOFs with no active element in their support (zero diagonal) become identity
            # rows on this level. Using the operator's own diagonal (Galerkin on coarse levels) never
            # over-constrains a coarse node that still touches material, unlike injecting fine fixed status.
            dgh = dg.numpy()
            inactive = (dgh == 0.0) & (lv.fixed_np == 0)
            if inactive.any():
                lv.fixed_np = (lv.fixed_np.astype(bool) | inactive).astype(np.int32)
                lv.fixed = wp.array(lv.fixed_np, dtype=wp.int32, device=self.dev)
                dgh[inactive] = 1.0
                dg = wp.array(dgh, dtype=wp.float32, device=self.dev)
                if lv is self.levels[0]:
                    self.fine64 = (self.fine64[0], lv.fixed)
            lv.n_inactive = int(inactive.sum())
            lv.dinv = wp.zeros_like(dg)
            wp.launch(H32["inv"], dim=lv.ndof, inputs=[dg, lv.dinv], device=self.dev)
        for lv in self.levels:
            lv.lmax = self._power(lv, lmax_iters) * 1.1
        c = self.levels[-1]
        self.coarse_inv_dev = None
        if c.ndof > coarsest_dofs:
            A = None  # too large to invert: high-degree Chebyshev on the coarsest level (linear, symmetric)
        elif c.Kel_np is not None:
            A = galerkin.assemble_dense(c.Kel_np.astype(np.float64), c.nx, c.ny, c.nz, c.fixed_np)
        else:
            A = reference.assemble(c.nx, c.ny, c.nz, Ke, c.E.numpy().astype(np.float64), c.fixed_np, c.scale).toarray()
        for lv in self.levels:
            lv.Kel_np = None  # host copies no longer needed
        if A is not None:
            A[c.fixed_np != 0, :] = 0.0
            A[:, c.fixed_np != 0] = 0.0
            A[c.fixed_np != 0, c.fixed_np != 0] = 1.0
            self.coarse_inv = np.linalg.inv(A)  # small (<= coarsest_dofs)
            self.coarse_inv_dev = wp.array(self.coarse_inv.astype(np.float32).reshape(-1), dtype=wp.float32,
                                           device=self.dev)
        self.scal = wp.zeros(4, dtype=wp.float64, device=self.dev)  # rz, pq, rz_new, rr
        n = self.levels[0].ndof
        self.v64 = {k: wp.zeros(n, dtype=wp.float64, device=self.dev) for k in ("x", "r", "z", "p", "q")}
        self.buf = wp.zeros(1, dtype=wp.float64, device=self.dev)

    # ── primitives ──
    def _A32(self, lv, x, y):
        if lv.Ef is not None:
            wp.launch(self.mod.matvec_g1, dim=lv.nnode, inputs=[lv.nx, lv.ny, lv.nz, lv.Ef, lv.fixed, x, y],
                      device=self.dev)
            return
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

    def _smooth(self, lv, x, b, degree=None):
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
        for _ in range(degree or self.deg):
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
            if self.coarse_inv_dev is not None:
                wp.launch(dense_matvec_f32, dim=lv.ndof, inputs=[lv.ndof, self.coarse_inv_dev, b, x], device=self.dev)
            else:
                self._smooth(lv, x, b, degree=self.coarsest_degree)
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

    def _dot_to(self, x, y, slot):
        n = x.shape[0]
        wp.launch(set_slot_64, dim=1, inputs=[self.scal, slot, wp.float64(0.0)], device=self.dev)
        wp.launch(dot_slot_64, dim=65536, inputs=[x, y, n, self.scal, slot], device=self.dev)

    def solve(self, b, tol=1e-6, maxiter=500, use_mg=True, verbose=False, x0=None, check_every=4):
        """Solve A u = b (b zero at fixed DOFs), optionally warm-started from x0. Returns (u, info).
        Tolerance is relative to ||b||."""
        lv = self.levels[0]
        n = lv.ndof
        x, r, z, p, q = (self.v64[k] for k in ("x", "r", "z", "p", "q"))
        bb = np.asarray(b, np.float64).copy()
        bb[lv.fixed_np != 0] = 0.0
        H = H64
        if x0 is None:
            r.assign(bb)
            x.zero_()
        else:
            xx = np.asarray(x0, np.float64).copy()
            xx[lv.fixed_np != 0] = 0.0
            x.assign(xx)
            self._A64(x, q)
            r.assign(bb)
            wp.launch(H["axpby"], dim=n, inputs=[wp.float64(-1.0), q, wp.float64(1.0), r, r], device=self.dev)
        bnorm = float(np.linalg.norm(bb))
        self._precond(r, z, use_mg)
        wp.copy(p, z)
        self._dot_to(r, z, 0)                       # rz
        hist = []
        t0 = time.perf_counter()
        it = 0
        for it in range(1, maxiter + 1):
            # all CG scalars stay on the device; the residual norm is read back every `check_every` iterations
            self._A64(p, q)
            self._dot_to(p, q, 1)                   # pq
            wp.launch(cg_xr_64, dim=n, inputs=[self.scal, p, q, x, r], device=self.dev)
            if it % check_every == 0 or it == maxiter:
                self._dot_to(r, r, 3)
                rnorm = float(np.sqrt(self.scal.numpy()[3]))
                hist.append(rnorm / bnorm)
                if verbose:
                    print(f"  it {it:4d}  rel res {rnorm / bnorm:.3e}", flush=True)
                if rnorm / bnorm <= tol:
                    break
            self._precond(r, z, use_mg)
            self._dot_to(r, z, 2)                   # rz_new
            wp.launch(cg_p_64, dim=n, inputs=[self.scal, z, p], device=self.dev)
            wp.launch(copy_slot_64, dim=1, inputs=[self.scal, 0, 2], device=self.dev)
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
