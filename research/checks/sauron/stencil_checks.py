"""Sauron scratch (round 3): AM-filter stencil acceptance angle vs azimuth, and Orca-style shell numbers.

1. A layer-wise support stencil S (in-layer cell offsets allowed beneath a cell) with cell sizes dx (XY), dz (Z)
   admits a sustained overhang whose lateral advance per layer in azimuth phi is the support function
   h_S(phi) = max_{s in S} s . (cos phi, sin phi) * dx  (k-fold Minkowski sums scale the hull).
   Min self-supported slope from horizontal: alpha(phi) = atan(dz / h_S(phi)).
2. Orca/Slic3r-lineage wall shell thickness with flow spacing s = w - h (1 - pi/4) [approximate model].
3. Overlap of a leaning outer wall expressed with slope from horizontal: f = 1 - h / (w tan alpha).
"""
import numpy as np

CROSS = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
SQUARE = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1)]


def alpha_from_horizontal(stencil, dx, dz, phi):
    d = np.array([np.cos(phi), np.sin(phi)])
    adv = max(np.dot(s, d) for s in stencil) * dx
    return np.degrees(np.arctan2(dz, adv))


def table(name, stencil, dx, dz):
    vals = [alpha_from_horizontal(stencil, dx, dz, np.radians(p)) for p in (0, 15, 30, 45)]
    print(f'{name:28s} dx={dx:.3f} dz={dz:.2f}: alpha_min(phi=0,15,30,45) =', [round(v, 1) for v in vals],
          ' worst =', round(min(vals), 1))


def shell(w_o, w_i, h, n_w):
    s_o, s_i = w_o - h*(1 - np.pi/4), w_i - h*(1 - np.pi/4)
    eff = w_o/2 + s_o/2 + (n_w - 1)*s_i if n_w >= 2 else w_o/2 + s_o/2
    nominal = eff - s_i/2 + w_i/2 if n_w >= 2 else w_o
    return eff, nominal


def main():
    print('1. Stencil acceptance (slope from horizontal; Orca supported the exactly-45 deg wedge)')
    for dz in (0.2, 0.4, 0.6):
        table('cross, cubic', CROSS, dz, dz)
        table('3x3, cubic', SQUARE, dz, dz)
        dx = dz*np.tan(np.radians(40))     # target 50 deg from horizontal on axes
        table('cross, dx = dz tan40', CROSS, dx, dz)
        table('3x3, dx = dz tan40', SQUARE, dx, dz)
    print('\n2. Wall shell (outer 0.42, inner 0.45, h 0.2), flow spacing model')
    for n in (1, 2, 3, 4):
        eff, nom = shell(.42, .45, .2, n)
        print(f'  n_w={n}: effective {eff:.3f} mm, nominal-footprint {nom:.3f} mm, naive n*w(0.42) {n*.42:.3f}')
    for n_w, n_t in [(2, 5), (2, 3), (4, 5)]:
        W, T = shell(.42, .45, .2, n_w)[0], n_t*.2
        print(f'  t_min walls {n_w} skins {n_t}: {W*T/np.hypot(W, T):.3f} mm at alpha = {np.degrees(np.arctan2(T, W)):.1f} deg from horizontal')
    print('\n3. Leaning outer wall overlap f = 1 - h/(w tan alpha), w = 0.42')
    for h in (.12, .2, .28):
        row = [(a, round(max(0., 1 - h/(.42*np.tan(np.radians(a)))), 2)) for a in (60, 50, 45, 40, 35, 30)]
        print(f'  h={h}:', row, f' zero at alpha = {np.degrees(np.arctan(h/.42)):.1f} deg')


if __name__ == '__main__':
    main()
