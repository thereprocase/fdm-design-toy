"""MG-PCG against a direct solve on small grids (needs a CUDA GPU and scipy)."""
import numpy as np
import pytest

wp = pytest.importorskip("warp")
sp = pytest.importorskip("scipy.sparse.linalg")

from fdmgen.fem import element, reference
from fdmgen.fem.mgpcg import MGPCG


def _case(nx, ny, nz, C, contrast, seed=1):
    Ke = element.box_ke(C, 1.0, 1.0, 1.0)
    rng = np.random.default_rng(seed)
    E = np.where(rng.random(nx * ny * nz) < 0.35, contrast, 1.0)
    fixed, b = reference.cantilever(nx, ny, nz)
    return Ke, E, fixed, b


@pytest.mark.parametrize("C", [element.isotropic_C(1.0, 0.3), element.ti_C(1.0, 0.87, 0.35, 0.3, 0.33)])
@pytest.mark.parametrize("contrast", [1.0, 1e-3])
def test_matches_direct(C, contrast):
    nx, ny, nz = 16, 8, 8
    Ke, E, fixed, b = _case(nx, ny, nz, C, contrast)
    A = reference.assemble(nx, ny, nz, Ke, E, fixed)
    bb = b.copy(); bb[fixed != 0] = 0
    u_ref = sp.spsolve(A.tocsc(), bb)
    s = MGPCG(nx, ny, nz, Ke, E, fixed, coarsest_dofs=200)
    assert len(s.levels) >= 2
    u, info = s.solve(b, tol=1e-10, maxiter=300)
    assert info["converged"], info["rel_res"]
    assert np.linalg.norm(u - u_ref) / np.linalg.norm(u_ref) < 1e-8
    assert abs(info["compliance"] - bb @ u_ref) / abs(bb @ u_ref) < 1e-9


def test_operator_matches_assembled():
    nx, ny, nz = 6, 4, 5
    Ke, E, fixed, b = _case(nx, ny, nz, element.isotropic_C(1.0, 0.3), 1e-2)
    A = reference.assemble(nx, ny, nz, Ke, E, fixed)
    s = MGPCG(nx, ny, nz, Ke, E, fixed, coarsest_dofs=10**9)  # single level
    x = np.random.default_rng(3).standard_normal(A.shape[0]); x[fixed != 0] = 0
    xw = wp.array(x, dtype=wp.float64, device=s.dev); yw = wp.zeros_like(xw)
    s._A64(xw, yw)
    assert np.linalg.norm(yw.numpy() - A @ x) / np.linalg.norm(A @ x) < 1e-13


def test_galerkin_element_matrices_equal_rap():
    """Element-wise Galerkin coarse operator == R A P with the solver's restriction/prolongation."""
    import scipy.sparse as sps
    from fdmgen.fem import galerkin
    nx, ny, nz = 4, 4, 2
    Ke = element.box_ke(element.isotropic_C(1.0, 0.3), 1, 1, 1)
    E = np.random.default_rng(5).random(nx * ny * nz) + 0.1
    A = reference.assemble(nx, ny, nz, Ke, E)
    # dense trilinear P from coarse (2x2x1 elements) to fine
    nxc, nyc, nzc = 2, 2, 1
    def node(i, j, k, my, mz): return (i * my + j) * mz + k
    P = np.zeros((A.shape[0], 3 * (nxc + 1) * (nyc + 1) * (nzc + 1)))
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                for I in range(nxc + 1):
                    for J in range(nyc + 1):
                        for K in range(nzc + 1):
                            w = np.prod([max(0, 1 - abs(f / 2 - c)) for f, c in ((i, I), (j, J), (k, K))])
                            if w:
                                for c in range(3):
                                    P[3 * node(i, j, k, ny + 1, nz + 1) + c, 3 * node(I, J, K, nyc + 1, nzc + 1) + c] = w
    RAP = P.T @ A.toarray() @ P
    Kc = galerkin.first_coarse(E, Ke, nx, ny, nz, dtype=np.float64)
    Ac = galerkin.assemble_dense(Kc, nxc, nyc, nzc, np.zeros(P.shape[1]))
    assert np.allclose(Ac, RAP, rtol=1e-12, atol=1e-12)
