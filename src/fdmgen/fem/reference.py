"""Assembled reference operator for structured box grids (tests, coarsest multigrid level).

Node (ix, iy, iz) -> (ix * (ny + 1) + iy) * (nz + 1) + iz;  DOF = 3 * node + component.
Element (ex, ey, ez) -> (ex * ny + ey) * nz + ez.  Element stiffness = E[e] * scale * Ke.
Fixed DOFs: rows and columns replaced by identity (homogeneous Dirichlet).
"""
from __future__ import annotations

import numpy as np

from .element import CORNERS


def element_dofs(nx: int, ny: int, nz: int) -> np.ndarray:
    ex, ey, ez = np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij")
    ex, ey, ez = ex.ravel(), ey.ravel(), ez.ravel()
    nodes = np.stack([((ex + c[0]) * (ny + 1) + (ey + c[1])) * (nz + 1) + (ez + c[2]) for c in CORNERS], axis=1)
    return (3 * nodes[:, :, None] + np.arange(3)).reshape(-1, 24)


def assemble(nx, ny, nz, Ke, E, fixed=None, scale=1.0):
    """scipy.sparse CSR of the masked operator."""
    import scipy.sparse as sp

    dofs = element_dofs(nx, ny, nz)
    n = 3 * (nx + 1) * (ny + 1) * (nz + 1)
    rows = np.repeat(dofs, 24, axis=1).ravel()
    cols = np.tile(dofs, (1, 24)).ravel()
    vals = (np.asarray(E, float)[:, None] * (scale * Ke).ravel()[None, :]).ravel()
    K = sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    if fixed is not None and np.any(fixed):
        f = np.asarray(fixed, bool)
        keep = sp.diags((~f).astype(float))
        K = keep @ K @ keep + sp.diags(f.astype(float))
    return K.tocsr()


def cantilever(nx, ny, nz):
    """Fixed x = 0 face (all components); unit total load -z spread on the x = nx, z = 0 edge."""
    n_nodes = (nx + 1) * (ny + 1) * (nz + 1)
    fixed = np.zeros(3 * n_nodes, np.int32)
    b = np.zeros(3 * n_nodes)
    idx = np.arange(n_nodes).reshape(nx + 1, ny + 1, nz + 1)
    for c in range(3):
        fixed[3 * idx[0].ravel() + c] = 1
    edge = idx[nx, :, 0].ravel()
    b[3 * edge + 2] = -1.0 / len(edge)
    return fixed, b
