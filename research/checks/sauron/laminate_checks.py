"""Sauron scratch: exact layered homogenisation and two slicer-geometry relations.

1. Exact 3D laminate homogenisation (partial inversion, cf. Sun & Li 1988) for an
   alternating +45/-45 solid-infill stack, compared with naive Voigt/Reuss averages.
2. Surface-normal shell thickness of an Orca-style part vs surface inclination.
3. Nominal inter-layer overlap fraction of a wall stepping out at overhang angle beta.
All numbers are illustrative; the bead card is ASSUMED (see sauron.md section 1).
"""
import numpy as np
from tensor_checks import (ortho_compliance_voigt, voigt_to_mandel_C, mandel_to_voigt_C,
                           q_mandel, rz, directional_modulus)

A = [0, 1, 5]   # in-plane strain group (11, 22, 12)  -> continuous across layers
B = [2, 3, 4]   # out-of-plane stress group (33, 23, 13) -> continuous across layers


def partial_inverse(C):
    Caa, Cab, Cba, Cbb = C[np.ix_(A, A)], C[np.ix_(A, B)], C[np.ix_(B, A)], C[np.ix_(B, B)]
    Bi = np.linalg.inv(Cbb)
    return np.block([[Caa - Cab@Bi@Cba, Cab@Bi], [-Bi@Cba, Bi]])


def undo_partial_inverse(M):
    Maa, Mab, Mba, Mbb = M[:3, :3], M[:3, 3:], M[3:, :3], M[3:, 3:]
    Cbb = np.linalg.inv(Mbb)
    Cba = -Cbb@Mba
    Cab = Mab@Cbb
    Caa = Maa + Cab@np.linalg.inv(Cbb)@Cba
    C = np.zeros((6, 6))
    C[np.ix_(A, A)], C[np.ix_(A, B)], C[np.ix_(B, A)], C[np.ix_(B, B)] = Caa, Cab, Cba, Cbb
    return C


def laminate(Cs, fractions):
    """Exact homogenisation of perfectly bonded layers normal to axis 3 (Mandel C in, Mandel C out)."""
    M = sum(f*partial_inverse(C) for C, f in zip(Cs, fractions))
    return undo_partial_inverse(M)


def main():
    # ASSUMED single-bead card: 1 = bead, 2 = in-layer transverse, 3 = build Z.
    Cv = np.linalg.inv(ortho_compliance_voigt(2000., 1500., 1300., .38, .36, .36, 650., 520., 480.))
    Cb = voigt_to_mandel_C(Cv)
    # identity check
    print('identical layers round-trip err', np.abs(laminate([Cb, Cb], [.5, .5]) - Cb).max())
    layers = [q_mandel(rz(s*np.pi/4)) @ Cb @ q_mandel(rz(s*np.pi/4)).T for s in (+1, -1)]
    exact = laminate(layers, [.5, .5])
    voigt = 0.5*(layers[0]+layers[1])
    reuss = np.linalg.inv(0.5*(np.linalg.inv(layers[0])+np.linalg.inv(layers[1])))
    for name, C in [('exact', exact), ('Voigt', voigt), ('Reuss', reuss)]:
        Ex = directional_modulus(C, np.array([1., 0, 0]))
        E45 = directional_modulus(C, np.array([1., 1, 0])/np.sqrt(2))
        Ez = directional_modulus(C, np.array([0, 0, 1.]))
        Cvv = mandel_to_voigt_C(C)
        print(f'{name:5s} E_x={Ex:7.1f} E_45={E45:7.1f} E_z={Ez:7.1f} G_xz={Cvv[4,4]:6.1f} '
              f'C_16(coupling)={Cvv[0,5]:7.2f}  min eig={np.linalg.eigvalsh(C).min():7.1f}')
    # +-45 stack: square symmetric about z with axes at 0/90? check invariance under Rz(90deg)
    Q = q_mandel(rz(np.pi/2))
    print('exact +-45 invariant under Rz(90):', np.abs(Q@exact@Q.T - exact).max())
    Q = q_mandel(rz(np.pi/4))
    print('exact +-45 NOT TI (Rz(45) change, MPa):', np.abs(Q@exact@Q.T - exact).max())

    print('\nSurface-normal shell thickness t(alpha) = max(nw*w*sin a, nt*h*cos a)')
    for nw, w, nt, h in [(2, .42, 5, .2), (2, .42, 3, .2), (4, .42, 5, .2)]:
        Hw, Ht = nw*w, nt*h
        a_star = np.degrees(np.arctan2(Ht, Hw))
        t_min = Hw*Ht/np.hypot(Hw, Ht)
        print(f'  walls {nw}x{w}  skins {nt}x{h}: min t = {t_min:.3f} mm at alpha = {a_star:.1f} deg from horizontal')

    print('\nNominal inter-layer overlap of a wall leaning beta from vertical: f = 1 - h tan(beta)/w')
    for w, h in [(.42, .2), (.42, .12), (.42, .28)]:
        row = [(b, round(max(0., 1-h*np.tan(np.radians(b))/w), 2)) for b in (0, 30, 45, 55, 60, 65)]
        print(f'  w={w} h={h}:', row, f' zero at beta={np.degrees(np.arctan(w/h)):.1f}')
    w, h = .42, .2
    print(f'\nStadium bead (Slic3r/Orca flow model) flat contact width w-h = {w-h:.2f} mm '
          f'= {(w-h)/w:.0%} of nominal; area h(w-h(1-pi/4)) = {h*(w-h*(1-np.pi/4)):.4f} vs w*h = {w*h:.4f} mm^2')


if __name__ == '__main__':
    main()
