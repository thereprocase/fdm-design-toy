"""Sauron scratch: verify the stiffness-rotation conventions claimed in research/sauron.md.

Pure numpy. Runs in < 1 s. Not production code; it exists so every formula in the
report has an executable check. Units: MPa, mm, radians.

Conventions (canonical order used here, "Mandel/Voigt canonical"):
    index 0..5 = (11, 22, 33, 23, 13, 12)
gpu_hex.py (spool-wall-rack) order is (xx, yy, zz, xy, yz, xz) with ENGINEERING shear strain.
"""
import numpy as np

PAIRS = [(0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1)]  # canonical
W = np.diag([1, 1, 1, np.sqrt(2), np.sqrt(2), np.sqrt(2)])
WINV = np.linalg.inv(W)
# gpu_hex row order expressed as canonical indices: xx,yy,zz,xy,yz,xz
GPU_HEX_ORDER = [0, 1, 2, 5, 3, 4]


def basis():
    """Orthonormal Mandel basis tensors B_I (B_I : B_J = delta_IJ)."""
    B = np.zeros((6, 3, 3))
    for I, (i, j) in enumerate(PAIRS):
        if i == j:
            B[I, i, i] = 1
        else:
            B[I, i, j] = B[I, j, i] = 1/np.sqrt(2)
    return B


BASIS = basis()


def q_mandel(R):
    """6x6 Mandel rotation: a' = Q a  <=>  A' = R A R^T. Q is orthogonal."""
    return np.einsum('Iij,ik,Jkl,jl->IJ', BASIS, R, BASIS, R)


def ortho_compliance_voigt(E1, E2, E3, nu12, nu13, nu23, G12, G13, G23):
    """Voigt (engineering shear) compliance, canonical order. nu_ij = -eps_j/eps_i under sigma_i."""
    S = np.zeros((6, 6))
    S[0, 0], S[1, 1], S[2, 2] = 1/E1, 1/E2, 1/E3
    S[0, 1] = S[1, 0] = -nu12/E1
    S[0, 2] = S[2, 0] = -nu13/E1
    S[1, 2] = S[2, 1] = -nu23/E2
    S[3, 3], S[4, 4], S[5, 5] = 1/G23, 1/G13, 1/G12
    return S


def voigt_to_mandel_C(Cv):
    return W @ Cv @ W


def mandel_to_voigt_C(Cm):
    return WINV @ Cm @ WINV


def mandel_to_tensor(Cm):
    return np.einsum('IJ,Iij,Jkl->ijkl', Cm, BASIS, BASIS)


def tensor_to_mandel(C4):
    return np.einsum('Iij,ijkl,Jkl->IJ', BASIS, C4, BASIS)


def rotate_tensor(C4, R):
    return np.einsum('ip,jq,kr,ls,pqrs->ijkl', R, R, R, R, C4)


def bond_stress_voigt(R):
    """Classical Bond matrix for Voigt stress (no sqrt2), canonical order: s' = T s."""
    T = np.zeros((6, 6))
    for I, (i, j) in enumerate(PAIRS):
        for J, (k, l) in enumerate(PAIRS):
            if k == l:
                T[I, J] = R[i, k]*R[j, l]
            else:
                T[I, J] = R[i, k]*R[j, l] + R[i, l]*R[j, k]
    return T


def rz(t):
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])


def rx(t):
    c, s = np.cos(t), np.sin(t)
    return np.array([[1., 0, 0], [0, c, -s], [0, s, c]])


def directional_modulus(Cm, n):
    """1/E(n) = (n x n) : S : (n x n), computed in Mandel space (no factor bookkeeping)."""
    Sm = np.linalg.inv(Cm)
    N = np.outer(n, n)
    nv = np.array([N[i, j]*(1 if i == j else np.sqrt(2)) for i, j in PAIRS])
    return 1/(nv @ Sm @ nv)


def main():
    rng = np.random.default_rng(0)
    out = {}
    # Illustrative PETG-HF-like bead-frame card. E1, E3 from Bambu TDS ratios; the rest ASSUMED.
    E1, E2, E3 = 1810., 1650., 1540.
    nu12, nu13, nu23 = .38, .36, .36
    G12, G13, G23 = 640., 600., 580.
    Sv = ortho_compliance_voigt(E1, E2, E3, nu12, nu13, nu23, G12, G13, G23)
    Cv = np.linalg.inv(Sv)
    Cm = voigt_to_mandel_C(Cv)
    out['C symmetric'] = np.abs(Cm - Cm.T).max()
    out['C min eigenvalue MPa (Mandel)'] = np.linalg.eigvalsh(Cm).min()

    # 1. Q orthogonal; Q C Q^T equals the 4th-order tensor rotation.
    for name, R in [('random', np.linalg.qr(rng.normal(size=(3, 3)))[0]), ('rx45 rz30', rx(np.pi/4) @ rz(np.pi/6))]:
        if np.linalg.det(R) < 0:
            R[:, 0] *= -1
        Q = q_mandel(R)
        out[f'{name}: |Q Q^T - I|'] = np.abs(Q @ Q.T - np.eye(6)).max()
        ref = tensor_to_mandel(rotate_tensor(mandel_to_tensor(Cm), R))
        out[f'{name}: |QCQ^T - tensor rotation|'] = np.abs(Q @ Cm @ Q.T - ref).max()
        # 2. Voigt Bond route agrees when done consistently.
        T = bond_stress_voigt(R)
        Cv_rot = T @ Cv @ T.T
        out[f'{name}: |Bond Voigt - Mandel route|'] = np.abs(Cv_rot - mandel_to_voigt_C(ref)).max()
        # 3. The common bug: applying the Mandel Q to a Voigt C.
        out[f'{name}: BUG Q Cv Q^T error, max MPa'] = np.abs(Q @ Cv @ Q.T - mandel_to_voigt_C(ref)).max()
        # 3b. Another common bug: using Bond T for stiffness but forgetting it is NOT orthogonal (T^-1 != T^T)
        out[f'{name}: BUG T^-1 C T^-T error, max MPa'] = np.abs(np.linalg.inv(T) @ Cv @ np.linalg.inv(T).T - mandel_to_voigt_C(ref)).max()

    # 4. Energy invariance: eps:C:eps in Mandel equals eps_v.Cv.eps_v with engineering shear.
    eps = rng.normal(size=(3, 3)); eps = (eps+eps.T)/2
    em = np.array([eps[i, j]*(1 if i == j else np.sqrt(2)) for i, j in PAIRS])
    ev = np.array([eps[i, j]*(1 if i == j else 2) for i, j in PAIRS])
    out['energy Mandel - Voigt'] = em @ Cm @ em - ev @ Cv @ ev

    # 5. Transverse isotropy about z is invariant under Rz; orthotropic bead card is not.
    Et, Ez = 1810., 1540.
    nut, nutz, Gtz = .38, .36, 580.
    Gt = Et/(2*(1+nut))
    Cti = voigt_to_mandel_C(np.linalg.inv(ortho_compliance_voigt(Et, Et, Ez, nut, nutz, nutz, Gt, Gtz, Gtz)))
    Q = q_mandel(rz(.7))
    out['TI about z: |Q C Q^T - C| under Rz(0.7)'] = np.abs(Q @ Cti @ Q.T - Cti).max()
    out['orthotropic bead card: |Q C Q^T - C| under Rz(0.7) MPa'] = np.abs(Q @ Cm @ Q.T - Cm).max()

    # 6. Directional modulus between layer plane and build axis for the TI card.
    rows = []
    for deg in [0, 15, 30, 45, 60, 75, 90]:
        p = np.radians(deg)
        n = np.array([np.cos(p), 0, np.sin(p)])
        rows.append((deg, directional_modulus(Cti, n)))
    out['E(angle from layer plane) TI card'] = rows

    # 7. Analytic dQ/dtheta vs central finite difference for C(theta) = Q(Rz(theta)) C Q^T.
    th, h = .3, 1e-6
    def C_of(t):
        Q = q_mandel(rz(t)); return Q @ Cm @ Q.T
    K = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 0.]])  # dRz/dt = K Rz
    R = rz(th)
    dR = K @ R
    dQ = np.einsum('Iij,ik,Jkl,jl->IJ', BASIS, dR, BASIS, R) + np.einsum('Iij,ik,Jkl,jl->IJ', BASIS, R, BASIS, dR)
    Q = q_mandel(R)
    dC = dQ @ Cm @ Q.T + Q @ Cm @ dQ.T
    fd = (C_of(th+h) - C_of(th-h))/(2*h)
    out['dC/dtheta analytic vs FD rel err'] = np.abs(dC-fd).max()/np.abs(dC).max()

    # 8. Permutation into gpu_hex order (xx,yy,zz,xy,yz,xz), engineering shear.
    P = np.eye(6)[GPU_HEX_ORDER]
    Cv_gpu = P @ Cv @ P.T
    out['gpu_hex order C[3,3] (should be G12)'] = Cv_gpu[3, 3]
    out['gpu_hex order C[4,4] (should be G23)'] = Cv_gpu[4, 4]
    out['gpu_hex order C[5,5] (should be G13)'] = Cv_gpu[5, 5]

    # 9. Interlayer criterion for uniaxial stress at angle phi from the layer plane.
    #    sigma_n = s sin^2 phi, tau = s sin phi cos phi, in-plane = s cos^2 phi.
    #    Quadratic: (<sigma_n>/Zt)^2 + (tau/S)^2 + (sigma_inplane/Xt)^2 <= 1 (illustrative, not a recommendation).
    Xt, Zt = 34., 23.
    rows = []
    for S_il in [15., 20., 25.]:
        r = []
        for deg in [0, 15, 30, 45, 60, 75, 90]:
            p = np.radians(deg)
            a = (np.sin(p)**2/Zt)**2 + (np.sin(p)*np.cos(p)/S_il)**2 + (np.cos(p)**2/Xt)**2
            r.append((deg, 1/np.sqrt(a)))
        rows.append((S_il, r))
    out['uniaxial strength vs angle, quadratic interlayer (Xt=34,Zt=23)'] = rows

    for k, v in out.items():
        if isinstance(v, list):
            print(k)
            for row in v:
                print('   ', row if not isinstance(row[1], list) else (row[0], [(d, round(s, 1)) for d, s in row[1]]))
        else:
            print(f'{k}: {v:.3e}' if isinstance(v, float) else f'{k}: {v}')


if __name__ == '__main__':
    main()
