"""Exact Galerkin coarse operators for 2:1 vertex-centred trilinear multigrid, element by element.

Trilinear prolongation from a coarse element is local to that element: every fine node inside or
on a coarse element is interpolated from that element's 8 corners only. Hence
    R A P = sum over coarse elements of  sum_{k=0..7} P_k^T A_child(k) P_k
where P_k (24x24) maps the parent's 24 DOFs to child k's 24 DOFs. Coarse levels therefore keep
one 24x24 matrix per element (no assembly), and the coarse matrix is linear in the children's
element matrices. Child k sits at offset CORNERS[k] inside the parent; element order and DOF
order follow element.CORNERS (k = cx + 2 cy + 4 cz).
"""
from __future__ import annotations

import numpy as np

from .element import CORNERS


def child_prolongations() -> np.ndarray:
    """P[k] (24x24): fine DOF 3b+c of child k <- coarse DOF 3a+c of the parent."""
    P = np.zeros((8, 24, 24))
    for k, ck in enumerate(CORNERS):
        for b, cb in enumerate(CORNERS):
            t = (ck + cb) / 2.0  # fine corner position in parent coordinates, in {0, 0.5, 1}^3
            for a, ca in enumerate(CORNERS):
                w = np.prod(np.where(ca == 1, t, 1 - t))
                if w:
                    for c in range(3):
                        P[k, 3 * b + c, 3 * a + c] = w
    return P


P_CHILD = child_prolongations()


def _children(arr: np.ndarray, nxc: int, nyc: int, nzc: int, k: int) -> np.ndarray:
    """View of per-element data for child position k of every coarse element: (nc, ...)."""
    cx, cy, cz = CORNERS[k]
    tail = arr.shape[1:]
    a6 = arr.reshape(nxc, 2, nyc, 2, nzc, 2, *tail)
    return a6[:, cx, :, cy, :, cz].reshape(nxc * nyc * nzc, *tail)


def first_coarse(E: np.ndarray, Ke: np.ndarray, nx: int, ny: int, nz: int, dtype=np.float32) -> np.ndarray:
    """Level-1 element matrices from fine element multipliers: Kc = sum_k E_child(k) * (P_k^T Ke P_k)."""
    M = np.einsum("kba,bc,kcd->kad", P_CHILD, Ke, P_CHILD).reshape(8, 576).astype(dtype)
    nxc, nyc, nzc = nx // 2, ny // 2, nz // 2
    E = np.asarray(E, dtype).reshape(-1, 1)
    Ech = np.concatenate([_children(E, nxc, nyc, nzc, k) for k in range(8)], axis=1)  # (nc, 8)
    return (Ech @ M).reshape(-1, 24, 24)


def next_coarse(K: np.ndarray, nx: int, ny: int, nz: int) -> np.ndarray:
    """Level l+1 element matrices from level-l element matrices K (n, 24, 24)."""
    nxc, nyc, nzc = nx // 2, ny // 2, nz // 2
    out = np.zeros((nxc * nyc * nzc, 24, 24), K.dtype)
    for k in range(8):
        Pk = P_CHILD[k].astype(K.dtype)
        out += Pk.T @ _children(K, nxc, nyc, nzc, k) @ Pk
    return out


def assemble_dense(K: np.ndarray, nx: int, ny: int, nz: int, fixed: np.ndarray) -> np.ndarray:
    """Dense matrix from element matrices, identity rows/cols at fixed DOFs (coarsest level)."""
    from .reference import element_dofs

    dofs = element_dofs(nx, ny, nz)
    n = 3 * (nx + 1) * (ny + 1) * (nz + 1)
    A = np.zeros((n, n))
    for e in range(len(dofs)):
        A[np.ix_(dofs[e], dofs[e])] += K[e]
    f = np.asarray(fixed) != 0
    A[f, :] = 0.0
    A[:, f] = 0.0
    A[f, f] = 1.0
    return A
