"""Constitutive matrices and the 8-node box (hex) element stiffness.

Conventions (PLAN D2, frames table):
- Voigt order (xx, yy, zz, yz, xz, xy) with engineering shear strains (gamma = 2 eps).
- Design-stage material is transversely isotropic (TI) about the print axis z of the grid.
- Element: trilinear 8-node box with edge lengths (dx, dy, dz), full 2x2x2 Gauss integration.
- Corner order: index a has offsets CORNERS[a] = (cx, cy, cz) in {0,1}^3, x slowest varying
  is NOT assumed anywhere; every consumer reads CORNERS.
"""
from __future__ import annotations

import numpy as np

CORNERS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
                    [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]], dtype=np.int32)


def isotropic_C(E: float, nu: float) -> np.ndarray:
    """6x6 isotropic stiffness, Voigt (xx, yy, zz, yz, xz, xy), engineering shear."""
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    C = np.zeros((6, 6))
    C[:3, :3] = lam
    C[[0, 1, 2], [0, 1, 2]] += 2 * mu
    C[[3, 4, 5], [3, 4, 5]] = mu
    return C


def ti_C(E_p: float, E_z: float, nu_p: float, nu_pz: float, G_pz: float) -> np.ndarray:
    """Transversely isotropic about z (the print axis).

    E_p: in-plane (layer) modulus; E_z: across-layer modulus; nu_p: in-plane Poisson ratio;
    nu_pz: Poisson ratio for contraction along z under in-plane stress (eps_z = -nu_pz/E_p * sigma_x);
    G_pz: shear modulus in the yz and xz planes. In-plane shear G_p = E_p / (2 (1 + nu_p)).
    Built as the inverse of the compliance, so symmetry holds by construction.
    """
    S = np.zeros((6, 6))
    S[0, 0] = S[1, 1] = 1 / E_p
    S[2, 2] = 1 / E_z
    S[0, 1] = S[1, 0] = -nu_p / E_p
    S[0, 2] = S[2, 0] = S[1, 2] = S[2, 1] = -nu_pz / E_p
    S[3, 3] = S[4, 4] = 1 / G_pz
    S[5, 5] = 2 * (1 + nu_p) / E_p
    C = np.linalg.inv(S)
    C = 0.5 * (C + C.T)
    if np.linalg.eigvalsh(C).min() <= 0:
        raise ValueError("TI card is not positive definite")
    return C


def box_ke(C: np.ndarray, dx: float, dy: float, dz: float) -> np.ndarray:
    """24x24 stiffness of a trilinear box element; DOF order (a, component) -> 3a + c."""
    g = np.array([0.5 - 0.5 / np.sqrt(3.0), 0.5 + 0.5 / np.sqrt(3.0)])
    h = np.array([dx, dy, dz], float)
    K = np.zeros((24, 24))
    for xi in g:
        for eta in g:
            for zeta in g:
                q = (xi, eta, zeta)
                dN = np.zeros((8, 3))
                for a, c in enumerate(CORNERS):
                    f = [q[k] if c[k] else 1 - q[k] for k in range(3)]
                    s = [1.0 if c[k] else -1.0 for k in range(3)]
                    dN[a] = [s[0] * f[1] * f[2], f[0] * s[1] * f[2], f[0] * f[1] * s[2]]
                dN = dN / h  # physical derivatives
                B = np.zeros((6, 24))
                for a in range(8):
                    nx_, ny_, nz_ = dN[a]
                    B[0, 3 * a] = nx_
                    B[1, 3 * a + 1] = ny_
                    B[2, 3 * a + 2] = nz_
                    B[3, 3 * a + 1] = nz_; B[3, 3 * a + 2] = ny_   # yz
                    B[4, 3 * a] = nz_;     B[4, 3 * a + 2] = nx_   # xz
                    B[5, 3 * a] = ny_;     B[5, 3 * a + 1] = nx_   # xy
                K += B.T @ C @ B * (dx * dy * dz / 8.0)
    return 0.5 * (K + K.T)
