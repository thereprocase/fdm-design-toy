"""CPU AMG convergence sensitivity; synthetic TI and stiffness bands, not material calibration."""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
from scipy.sparse.linalg import cg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amg_bracket import assemble_active, rigid_candidates
from fdmgen.fem import element


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def constitutive(ratio, axis, shear_ratio=None, nu_p=.3, nu_pz=.3):
    """Ep=1, Ez=ratio, both Poisson inputs .3, Gpz=ratio/2.6; axis in grid frame.

    Proper cyclic axis permutations preserve engineering-shear Voigt convention.
    Defaults retain the synthetic family; explicit parameters support card-ratio sensitivity.
    """
    if not np.isfinite(ratio) or not 0 < ratio <= 1 or axis not in ('x', 'y', 'z'):
        raise ValueError('ratio must be finite in (0,1], axis x/y/z')
    if shear_ratio is not None and (not np.isfinite(shear_ratio) or shear_ratio <= 0):
        raise ValueError('shear ratio must be finite and positive')
    if not np.isfinite([nu_p, nu_pz]).all():
        raise ValueError('Poisson inputs must be finite')
    C = element.ti_C(1., ratio, nu_p, nu_pz, ratio / 2.6 if shear_ratio is None else ratio * shear_ratio)
    order = {'x': [2, 0, 1, 5, 3, 4], 'y': [1, 2, 0, 4, 5, 3], 'z': list(range(6))}[axis]
    return C[np.ix_(order, order)]


def parameter_cases(ratios=None, shear_ratios=None, nu_p=None, nu_pz=None, card_path=None):
    """Read ratio endpoints and nominal Poisson inputs; normalize Ep to one."""
    card_source = None
    if card_path is not None:
        if any(x is not None for x in (ratios, shear_ratios, nu_p, nu_pz)):
            raise ValueError('card ratio corners cannot be mixed with explicit material parameters')
        from fdmgen.materials.card import load_card
        card = load_card(card_path)
        m = card.data['moduli']
        ratios = m['E_z_over_E_p']['interval']
        shear_ratios = m['G_z_over_E_z']['interval']
        nu_p, nu_pz = m['nu_p']['value'], m['nu_pz']['value']
        card_source = dict(id=card.id, tier=card.tier,
            sha256=hashlib.sha256(card.path.read_bytes()).hexdigest(),
            parameters={key: m[key] for key in ['E_z_over_E_p', 'G_z_over_E_z', 'nu_p', 'nu_pz']},
            normalization='Ep=1; neither dimensional modulus basis is used',
            scope='two ratio intervals at nominal Poisson inputs, not all card uncertainty corners')
    ratios = [1., .7] if ratios is None else ratios
    shear_ratios = [None] if shear_ratios is None else shear_ratios
    nu_p, nu_pz = .3 if nu_p is None else nu_p, .3 if nu_pz is None else nu_pz
    cases = [dict(ratio=r, shear_ratio=g, nu_p=nu_p, nu_pz=nu_pz) for r in ratios for g in shear_ratios]
    for case in cases:
        constitutive(axis='z', **case)
    return cases, card_source


def stiffness_field(mask, emin, pattern):
    """Uniform rho=.5 or four-cell grid-X bands alternating rho=0/1.

    All body cells remain active via E_min; outside cells are strictly inactive.
    Bands are an artificial contrast challenge, not proposed helper geometry.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 3 or not mask.any() or not np.isfinite(emin) or not 0 < emin <= 1:
        raise ValueError('nonempty 3D mask and finite emin in (0,1] required')
    if pattern == 'uniform':
        rho = np.full(mask.shape, .5)
    elif pattern == 'bands':
        rho = np.broadcast_to(((np.arange(mask.shape[0]) // 4) % 2)[:, None, None], mask.shape).astype(float)
    else:
        raise ValueError('pattern must be uniform or bands')
    rho = np.where(mask, rho, 0.)
    return rho, np.where(mask, emin + rho**3 * (1 - emin), 0.)


def solve_case(A, rhs, B, smoother, maxiter, seed=0, strength_threshold=0., coarse_solver='splu'):
    if not np.isfinite(strength_threshold) or not 0 <= strength_threshold <= 1:
        raise ValueError('strength threshold must be finite in [0,1]')
    if coarse_solver not in ('splu', 'pinv'):
        raise ValueError('coarse solver must be splu or pinv')
    import pyamg
    # Reset separately for every case, including spectral-radius estimation.
    np.random.seed(seed)
    start = time.perf_counter()
    ml = pyamg.smoothed_aggregation_solver(
        A.tobsr(blocksize=(3, 3)), B=B, symmetry='symmetric', smooth=smoother,
        strength=('symmetric', {'theta': strength_threshold}),
        max_coarse=100, presmoother=('block_gauss_seidel', {'sweep': 'symmetric'}),
        postsmoother=('block_gauss_seidel', {'sweep': 'symmetric'}), coarse_solver=coarse_solver)
    setup_s = time.perf_counter() - start
    history = []
    norm = np.linalg.norm(rhs)
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError('finite nonzero rhs required')
    start = time.perf_counter()
    u, status = cg(A, rhs, M=ml.aspreconditioner(), rtol=1e-6, atol=0, maxiter=maxiter,
                   callback=lambda x: history.append(float(np.linalg.norm(rhs - A @ x) / norm)))
    solve_s = time.perf_counter() - start
    residual = float(np.linalg.norm(rhs - A @ u) / norm)
    compliance = float(rhs @ u)
    return dict(smoother=smoother, seed=seed, coarse_solver=coarse_solver,
                strength=dict(method='symmetric', theta=strength_threshold, blocksize=3), status=int(status), iterations=len(history),
                converged=bool(status == 0 and np.isfinite(residual) and residual <= 1e-6
                               and np.isfinite(compliance) and compliance > 0),
                true_relative_residual=residual, compliance=compliance,
                setup_s=setup_s, solve_s=solve_s, history=history,
                operator_complexity=float(ml.operator_complexity()),
                timing_scope='solve includes one diagnostic residual matvec per iteration')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--h', type=float, default=1.6)
    ap.add_argument('--emin', type=float, default=1e-3)
    ap.add_argument('--ratios', nargs='+', type=float)
    ap.add_argument('--shear-ratios', nargs='+', type=float, help='Gpz/Ez; default 1/2.6')
    ap.add_argument('--nu-p', type=float)
    ap.add_argument('--nu-pz', type=float)
    ap.add_argument('--card-ratio-corners', help='linted card path or ID; uses ratio endpoints and nominal Poisson inputs')
    ap.add_argument('--axes', nargs='+', choices=['x', 'y', 'z'], default=['z'])
    ap.add_argument('--patterns', nargs='+', choices=['uniform', 'bands'], default=['uniform', 'bands'])
    ap.add_argument('--smoothers', nargs='+', choices=['jacobi', 'energy'], default=['energy'])
    ap.add_argument('--strength-thresholds', nargs='+', type=float, default=[0.],
                    help='symmetric nodal block-strength theta values in [0,1]')
    ap.add_argument('--coarse-solver', choices=['splu', 'pinv'], default='splu')
    ap.add_argument('--maxiter', type=int, default=150)
    args = ap.parse_args()
    if not np.isfinite(args.h) or args.h <= 0 or args.maxiter < 1:
        ap.error('positive finite grid spacing and iteration cap required')
    if any(not np.isfinite(t) or not 0 <= t <= 1 for t in args.strength_thresholds):
        ap.error('strength thresholds must be finite in [0,1]')
    try:
        cases, card_source = parameter_cases(args.ratios, args.shear_ratios, args.nu_p, args.nu_pz, args.card_ratio_corners)
    except ValueError as error:
        ap.error(str(error))
    stiffness_field(np.ones((1, 1, 1), bool), args.emin, 'uniform')
    import scipy
    import pyamg
    from bracket_gate import build
    from fdmgen.adapters.spool_bracket import HANDOFF
    _, mask, grid, fixed, b, bc = build(args.root, (args.h,) * 3)
    receipt = dict(schema='fdmgen/amg-sensitivity@0.1', machine_role='compute box',
        establishes='CPU convergence on these declared synthetic stiffness fields and gate restraints',
        does_not_establish='calibrated anisotropy, printable helpers, physical response, GPU/mixed-precision gate or zero-ersatz gap',
        card=card_source, parameter_cases=cases,
        law=dict(Ep=1., Ez='ratio', Gpz='ratio * shear_ratio; null shear_ratio means 1/2.6', frame='grid',
                 density_power=3, emin=args.emin, bands='floor(grid_i/4) modulo 2 gives rho=0 or 1'),
        h_mm=list(grid.h), grid=list(grid.shape), body_cells=int(mask.sum()), bc=bc,
        mask_sha256=digest(mask), fixed_sha256=digest(fixed), load_sha256=digest(b),
        mesh_sha256=hashlib.sha256((args.root / HANDOFF / 'body-only.stl').read_bytes()).hexdigest(),
        source_sha256={p: hashlib.sha256((Path(__file__).parents[1] / p).read_bytes()).hexdigest()
                       for p in ['bench/amg_sensitivity.py', 'bench/amg_bracket.py', 'bench/bracket_gate.py', 'src/fdmgen/fem/element.py']},
        versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__, pyamg=pyamg.__version__),
        maxiter=args.maxiter, relative_tolerance=1e-6, rows=[])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    save()
    for pattern in args.patterns:
        rho, E = stiffness_field(mask, args.emin, pattern)
        for case in cases:
            for axis in args.axes:
                C = constitutive(axis=axis, **case)
                start = time.perf_counter()
                A, gdofs = assemble_active(E, element.box_ke(C, *grid.h), fixed)
                assembly_s = time.perf_counter() - start
                rhs = b[gdofs].copy(); rhs[fixed[gdofs] != 0] = 0
                B = rigid_candidates(grid.node_coords()[gdofs[::3] // 3]); B[fixed[gdofs] != 0] = 0
                for smoother in args.smoothers:
                    for theta in args.strength_thresholds:
                        row = solve_case(A, rhs, B, smoother, args.maxiter, strength_threshold=theta, coarse_solver=args.coarse_solver)
                        row.update(pattern=pattern, **case, axis=axis, C=C.tolist(),
                            density_sha256=digest(rho), stiffness_sha256=digest(E), rhs_sha256=digest(rhs),
                            active_dofs_sha256=digest(gdofs), body_stiffness_min=float(E[mask].min()),
                            body_stiffness_max=float(E[mask].max()), dofs=A.shape[0], nnz=A.nnz, assembly_s=assembly_s)
                        receipt['rows'].append(row); save()
                        print(pattern, case, axis, smoother, theta, row['iterations'], row['true_relative_residual'], row['converged'], flush=True)
    return 0 if all(r['converged'] for r in receipt['rows']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
