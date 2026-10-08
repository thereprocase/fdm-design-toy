"""Nominal TI density sensitivity with an isotropic auxiliary AMG preconditioner."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_occupancy import audit_domain, read_occupancy
from density_weighted import stiffness_fraction


def array_sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def layer_axis(reference, provenance):
    """Only grid-aligned TI is supported; never silently rotate the tensor."""
    rotations = [np.asarray(reference['installed_to_print']['R'], float),
                 np.asarray(provenance['pose_R_design_to_print'], float)]
    for R in rotations:
        if (R.shape != (3, 3) or not np.isfinite(R).all()
                or not np.allclose(R.T @ R, np.eye(3), atol=1e-12, rtol=0)
                or not np.isclose(np.linalg.det(R), 1, atol=1e-12, rtol=0)):
            raise ValueError('frame rotations must be proper orthogonal matrices')
    # This bracket adapter declares design = installed. Card z is print-layer normal.
    axis = rotations[0] @ rotations[1].T @ np.array([0., 0., 1.])
    if not np.allclose(np.abs(axis), [0, 0, 1], atol=1e-12, rtol=0):
        raise ValueError('layer axis is not grid Z; tensor rotation is not implemented')
    return axis.tolist()


def require_matching_sampling(baseline, project):
    """Different source files are expected; different deposition methods are not."""
    methods = []
    for provenance in (baseline, project):
        sampling = provenance.get('sampling')
        if (not isinstance(sampling, dict)
                or not all(isinstance(sampling.get(k), str) and sampling[k]
                           for k in ('step_frac', 'recorded_step_frac', 'generator', 'purpose'))
                or isinstance(sampling.get('step_mm'), bool)
                or not isinstance(sampling.get('step_mm'), (int, float))
                or not np.isfinite(sampling['step_mm']) or sampling['step_mm'] <= 0
                or ('caps' in sampling and not isinstance(sampling['caps'], bool))):
            raise ValueError('paired TI comparison needs complete sampling method provenance')
        methods.append({k: v for k, v in sampling.items()
                        if k not in ('source_npz', 'source_npz_sha256')})
    if methods[0] != methods[1]:
        raise ValueError('baseline/project sampling methods differ; comparison refused')


def material_spec(path, basis, axis, power):
    from fdmgen.materials.card import load_card
    card = load_card(path)
    C = card.C(basis)
    return C, dict(model='transversely isotropic', card_id=card.id, card_tier=card.tier,
        card_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), modulus_basis=basis,
        constants=card.constants(basis), card_parameters=card.data['moduli'],
        poisson_convention=card.data['poisson_convention'],
        C_grid_MPa=C.tolist(), C_sha256=array_sha(C),
        voigt_order=['xx', 'yy', 'zz', 'yz', 'xz', 'xy'], shear_convention='engineering',
        layer_axis_grid=axis, law='C_cell = min(raw_density, 1)^power * C_grid',
        power=power, stiffness_floor=0, evidence='nominal card and uncalibrated homogenisation assumption')


def solve_ti(weights, grid, fixed, load, C, maxiter):
    """TI equations; fixed isotropic auxiliary operator is only a preconditioner."""
    import time
    import pyamg
    from scipy.sparse.linalg import cg
    from amg_bracket import assemble_active, rigid_candidates
    from fdmgen.fem.element import box_ke, isotropic_C
    if maxiter < 1:
        raise ValueError('maxiter must be positive')
    C = np.asarray(C, float)
    if (C.shape != (6, 6) or not np.isfinite(C).all()
            or not np.allclose(C, C.T, rtol=1e-12, atol=1e-12)
            or np.linalg.eigvalsh(C).min() <= 0):
        raise ValueError('C must be a symmetric positive-definite 6x6 stiffness')
    start = time.perf_counter()
    A, ids = assemble_active(weights, box_ke(C, *grid.h), fixed)
    auxiliary, aux_ids = assemble_active(weights, box_ke(isotropic_C(1000., .3), *grid.h), fixed)
    if not np.array_equal(ids, aux_ids):
        raise ValueError('physical and auxiliary domains differ')
    rhs = load[ids].copy()
    if not np.isfinite(rhs).all() or np.linalg.norm(rhs) == 0:
        raise ValueError('load must be finite and nonzero')
    B = rigid_candidates(grid.node_coords()[ids[::3]//3]); B[fixed[ids] != 0] = 0
    np.random.seed(0)
    ml = pyamg.smoothed_aggregation_solver(auxiliary.tobsr(blocksize=(3, 3)), B=B,
        symmetry='symmetric', strength=('symmetric', {'theta': 0}), aggregate='standard',
        smooth='energy', max_coarse=100, coarse_solver='splu',
        presmoother=('block_gauss_seidel', {'sweep': 'symmetric'}),
        postsmoother=('block_gauss_seidel', {'sweep': 'symmetric'}))
    setup_s = time.perf_counter()-start
    count = []
    start = time.perf_counter()
    u, status = cg(A, rhs, M=ml.aspreconditioner(), rtol=1e-9, atol=0, maxiter=maxiter,
                   callback=lambda _: count.append(1))
    residual = float(np.linalg.norm(rhs-A@u)/np.linalg.norm(rhs))
    compliance = float(rhs@u)
    valid = status == 0 and np.isfinite(residual) and residual <= 1e-8 and compliance > 0
    matrix_sha = lambda M: {k: array_sha(getattr(M, k)) for k in ('data', 'indices', 'indptr')}
    return dict(status='solved' if valid else 'unconverged', iterations=len(count),
        cg_status=int(status), true_relative_residual=residual, setup_s=setup_s,
        solve_s=time.perf_counter()-start, dofs=len(ids),
        compliance_N_mm=compliance if valid else None,
        max_displacement_mm=float(np.linalg.norm(u.reshape(-1, 3), axis=1).max()) if valid else None,
        physical_CSR_sha256=matrix_sha(A), auxiliary_CSR_sha256=matrix_sha(auxiliary),
        active_ids_sha256=array_sha(ids), rhs_sha256=array_sha(rhs), B_sha256=array_sha(B),
        hierarchy=[dict(dofs=int(v.A.shape[0]), nnz=int(v.A.nnz)) for v in ml.levels])


def main():
    from bracket_gate import build
    from fdmgen.adapters.spool_bracket import HANDOFF
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'reference', 'baseline', 'project', 'out'):
        ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--power', type=int, choices=(1, 3), required=True)
    ap.add_argument('--card', type=Path, required=True)
    ap.add_argument('--basis', choices=('short_term', 'sustained_effective'), required=True)
    ap.add_argument('--maxiter', type=int, default=120)
    ap.add_argument('--solve', action='store_true')
    args = ap.parse_args()
    if args.maxiter < 1:
        ap.error("maxiter must be positive")
    raw = args.reference.read_bytes(); ref = json.loads(raw)
    sha = hashlib.sha256(raw).hexdigest()
    paths = {'baseline': args.baseline, 'project': args.project}
    fields = {k:read_occupancy(p, ref, sha) for k, p in paths.items()}
    for key in ('table_sha256', 'pose', 'pose_R_design_to_print', 'pose_t_mm'):
        if fields['baseline'][1].get(key) != fields['project'][1].get(key):
            raise ValueError('baseline/project pose or table differs')
    require_matching_sampling(fields['baseline'][1], fields['project'][1])
    axes = [layer_axis(ref, fields[k][1]) for k in ('baseline', 'project')]
    if axes[0] != axes[1]:
        raise ValueError('baseline/project layer axes differ')
    C, material = material_spec(args.card, args.basis, axes[0], args.power)
    br, full, grid, fixed, load, bc = build(args.root, tuple(ref['grid']['h_mm']))
    if (bc != ref['bc'] or tuple(grid.shape) != tuple(ref['grid']['shape'])
        or not np.allclose(grid.origin, ref['grid']['origin_print_mm'], atol=1e-10, rtol=0)
        or not np.array_equal(br.R_I_to_P, ref['installed_to_print']['R'])
        or not np.array_equal(br.t_I_to_P, ref['installed_to_print']['t_mm'])
        or hashlib.sha256((args.root/HANDOFF/'body-only.stl').read_bytes()).hexdigest() != ref['mesh_sha256']):
        raise ValueError('rebuilt grid, boundaries, frame or mesh differs from reference')
    receipt = dict(schema='fdmgen/ti-density-mechanics-pilot@0.1', reference_sha256=sha,
        material=material,
        grid=ref['grid'], installed_to_print=ref['installed_to_print'], bc=bc,
        load_policy='original full-body nodal loads and restraints; no transfer or deletion',
        load_sha256=hashlib.sha256(load.tobytes()).hexdigest(),
        domain_policy='all positive-density cells',
        establishes='density-law sensitivity of a nominal TI linear FE model',
        does_not_establish=['resolved bead gaps or bonds', 'calibrated stiffness-density law',
          'mesh convergence', 'anisotropic strength', 'physical movement or qualification',
          'equivalence to the thresholded and load-transferred pilot'], cases={})
    import platform, scipy, pyamg
    receipt['versions'] = dict(python=platform.python_version(), numpy=np.__version__,
                               scipy=scipy.__version__, pyamg=pyamg.__version__)
    receipt['fixed_sha256'] = array_sha(fixed)
    for key, value in (('mask_sha256', full), ('fixed_sha256', fixed), ('load_sha256', load)):
        if key in ref and array_sha(value) != ref[key]:
            raise ValueError('rebuilt '+key+' differs from reference')
    receipt['preconditioner'] = dict(role='auxiliary inverse only; physical equations remain TI',
        model='isotropic', E_MPa=1000., nu=.3, density_law='same weights as physical operator',
        strength=dict(method='symmetric', theta=0), aggregation='standard', candidates='global rigid6; fixed rows zero',
        prolongation='energy (installed PyAMG defaults)', relaxation='symmetric block Gauss-Seidel pre/post',
        coarse_solver='splu', max_coarse=100, seed=0)
    receipt['solver'] = dict(method='CG', rtol=1e-9, atol=0, maxiter=args.maxiter,
                             acceptance_true_relative_residual=1e-8)
    receipt['does_not_establish'] += ['all card uncertainty corners', 'validated sustained-life law',
                                     'GPU solver gate']
    repo = Path(__file__).resolve().parents[1]
    receipt['source_sha256'] = {p: hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in (
        'bench/ti_density_weighted.py', 'bench/density_weighted.py', 'bench/compare_occupancy.py',
        'bench/amg_bracket.py', 'bench/bracket_gate.py', 'src/fdmgen/fem/element.py',
        'src/fdmgen/materials/card.py')}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    for name in ('full_solid', 'baseline', 'project'):
        density = full.astype(float) if name == 'full_solid' else fields[name][0]
        weights = stiffness_fraction(density, args.power); mask = weights > 0
        row = dict(raw_audit=audit_domain(mask, grid, fixed, load))
        if name != 'full_solid':
            row.update(npz_sha256=hashlib.sha256(paths[name].read_bytes()).hexdigest(), provenance=fields[name][1])
        row['audit'] = audit_domain(mask, grid, fixed, load)
        row['positive_stiffness_fraction_min'] = float(weights[mask].min()) if mask.any() else None
        row['cells_outside_full_body'] = int((mask & ~full).sum())
        receipt['cases'][name] = row; save()
        if args.solve and row['audit']['status'] == 'ready':
            row['solve'] = solve_ti(weights, grid, fixed, load, C, args.maxiter)
        elif args.solve:
            row['solve'] = {'status':'blocked_by_audit'}
        save(); print(name, row['audit']['status'], row.get('solve', {}), flush=True)
    if all(receipt['cases'][n].get('solve', {}).get('status') == 'solved' for n in ('baseline','project')):
        a, b = (receipt['cases'][n]['solve']['compliance_N_mm'] for n in ('baseline','project'))
        receipt['project_compliance_change_fraction'] = (b-a)/a
    else:
        receipt['comparison_status'] = 'not established; inspect audits and solves'
    save()
    if args.solve and receipt.get('comparison_status'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
