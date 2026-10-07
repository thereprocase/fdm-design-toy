"""Cell-centre hex stress recovery; stress Voigt order xx yy zz yz xz xy."""
import numpy as np
from .element import CORNERS


def centre_stress(displacements, C, h):
    """Recover constant-point stress from (..., 8, 3) nodal displacement.

    Coordinates and displacement use mm; C in MPa yields stress in MPa.
    This is a centre sample, not a corner maximum or a nodal extrapolation.
    """
    u = np.asarray(displacements, dtype=float)
    h = np.asarray(h, dtype=float)
    C = np.asarray(C, dtype=float)
    if u.shape[-2:] != (8, 3) or not np.isfinite(u).all():
        raise ValueError('expected finite (..., 8, 3) displacement')
    if h.shape != (3,) or not np.isfinite(h).all() or (h <= 0).any():
        raise ValueError('expected three positive finite cell lengths')
    if C.shape != (6, 6) or not np.isfinite(C).all():
        raise ValueError('expected finite 6x6 stiffness')
    derivatives = (2*CORNERS-1) / (4*h)
    grad = np.einsum('...ai,aj->...ij', u, derivatives)
    strain = np.stack([grad[..., 0, 0], grad[..., 1, 1], grad[..., 2, 2],
                       grad[..., 1, 2]+grad[..., 2, 1],
                       grad[..., 0, 2]+grad[..., 2, 0],
                       grad[..., 0, 1]+grad[..., 1, 0]], axis=-1)
    return strain @ C.T


def rotate_stress(stress, R):
    """Rotate symmetric stress into frame x_new = R @ x_old (proper rotation)."""
    s, R = np.asarray(stress, float), np.asarray(R, float)
    if s.shape[-1:] != (6,) or not np.isfinite(s).all():
        raise ValueError('expected finite (..., 6) stress')
    if R.shape != (3, 3) or not np.allclose(R@R.T, np.eye(3), atol=1e-12, rtol=0) or not np.isclose(np.linalg.det(R), 1):
        raise ValueError('expected proper orthogonal rotation')
    T = np.empty(s.shape[:-1]+(3, 3))
    T[..., 0, 0], T[..., 1, 1], T[..., 2, 2] = s[..., 0], s[..., 1], s[..., 2]
    T[..., 1, 2] = T[..., 2, 1] = s[..., 3]
    T[..., 0, 2] = T[..., 2, 0] = s[..., 4]
    T[..., 0, 1] = T[..., 1, 0] = s[..., 5]
    T = R @ T @ R.T
    return np.stack([T[..., 0, 0], T[..., 1, 1], T[..., 2, 2], T[..., 1, 2], T[..., 0, 2], T[..., 0, 1]], axis=-1)
