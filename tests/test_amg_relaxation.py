"""Known-answer controls for explicit residual-form relaxation."""
import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import bsr_array
sys.path.insert(0, str(Path(__file__).parents[1] / 'bench'))
from amg_relaxation import residual_block_jacobi


def test_singular_block_preserves_exact_solution_and_corrects_range():
    A = bsr_array(np.diag([1., 0.]), blocksize=(2, 2))
    inverse = np.array([[[1., 0.], [0., 0.]]])
    b = np.array([1., 0.])
    x = np.array([1., 7.])
    residual_block_jacobi(A, x, b, Dinv=inverse, omega=1., iterations=3)
    np.testing.assert_array_equal(x, [1., 7.])
    x = np.array([0., 7.])
    residual_block_jacobi(A, x, b, Dinv=inverse, omega=1.)
    np.testing.assert_array_equal(x, [1., 7.])
    np.testing.assert_array_equal(A @ x, b)


def test_nonsingular_blocks_agree_with_compiled_jacobi_from_nonzero_iterate():
    pytest.importorskip('pyamg')
    from pyamg.relaxation.relaxation import block_jacobi
    dense = np.array([[4., 1., .1, 0.], [1., 3., 0., .1], [.1, 0., 3., .5], [0., .1, .5, 2.]])
    A = bsr_array(dense, blocksize=(2, 2))
    inverse = np.stack([np.linalg.inv(dense[:2, :2]), np.linalg.inv(dense[2:, 2:])])
    b = np.array([1., -2., 3., -4.]); x = np.array([2., 1., -3., 4.]); expected = x.copy()
    block_jacobi(A, expected, b, Dinv=inverse, omega=.5, iterations=2, blocksize=2)
    residual_block_jacobi(A, x, b, Dinv=inverse, omega=.5, iterations=2, blocksize=2)
    np.testing.assert_allclose(x, expected, rtol=1e-13, atol=1e-13)
