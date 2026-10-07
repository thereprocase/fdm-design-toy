"""CPU known-answer regression for the first Galerkin level's dense solve."""
import numpy as np
import pytest
wp = pytest.importorskip("warp")
from fdmgen.fem import element, galerkin, reference
from fdmgen.fem.mgpcg import MGPCG


@pytest.mark.parametrize("masked", [False, True])
def test_first_galerkin_level_dense_solve_is_its_operator(masked):
    nx, ny, nz = 8, 4, 4
    Ke = element.box_ke(element.isotropic_C(1, 0.3), 1, 1, 1)
    E = np.random.default_rng(81).uniform(0.1, 1, nx * ny * nz)
    if masked:
        field = E.reshape(nx, ny, nz)
        field[2:, 1:3, 1:3] = 0  # thin shell with a connected clamp plate
    fixed, _ = reference.cantilever(nx, ny, nz)
    solver = MGPCG(nx, ny, nz, Ke, E, fixed, device="cpu", coarsest_dofs=200, lmax_iters=2)
    assert len(solver.levels) == 2
    c = solver.levels[-1]
    assert c.Ef is not None
    K = galerkin.first_coarse(E, Ke, nx, ny, nz, dtype=np.float64)
    A = galerkin.assemble_dense(K, c.nx, c.ny, c.nz, c.fixed_np)
    residual = A @ solver.coarse_inv - np.eye(c.ndof)
    assert np.linalg.norm(residual, ord=np.inf) < 1e-10
