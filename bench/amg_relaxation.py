"""Experimental residual-form block relaxation for the CPU AMG harness."""
from functools import partial
import numpy as np

RELAXATIONS = ('block_gauss_seidel', 'block_jacobi', 'residual_block_jacobi')


def residual_block_jacobi(A, x, b, *, Dinv, omega, iterations=1, blocksize=None):
    """Add a residual correction, retaining an exact solution's null component.

    Unlike overwriting a block with a pseudoinverse solution, this leaves x
    unchanged when b-Ax is zero, including for singular diagonal blocks.
    It does not by itself certify an SPD cycle or adequate convergence.
    """
    size = Dinv.shape[1]
    if blocksize is not None and blocksize != size:
        raise ValueError('block size must match the supplied inverse blocks')
    for _ in range(iterations):
        residual = (b-A @ x).reshape(-1, size)
        x += omega*np.einsum('ijk,ik->ij', Dinv, residual).ravel()


def configure_relaxation(ml, name):
    """Keep hierarchy construction fixed; replace relaxation after construction."""
    if name not in RELAXATIONS:
        raise ValueError('unknown relaxation')
    if name == 'block_gauss_seidel':
        return  # The harness constructs symmetric block GS, one pre/post sweep.
    from pyamg.relaxation.smoothing import change_smoothers
    options = ('block_jacobi', {'iterations': 1, 'omega': 1., 'withrho': True})
    change_smoothers(ml, options, options)
    if name == 'residual_block_jacobi':
        for level in ml.levels[:-1]:
            # Reuse precisely the installed Jacobi inverses, damping and counts.
            for attr in ('presmoother', 'postsmoother'):
                original = getattr(level, attr)
                setattr(level, attr, partial(residual_block_jacobi, **original.keywords))
