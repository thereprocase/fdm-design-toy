"""Audited CPU comparison of thresholded slice grids, not printed-material truth.

Uses the original solver-gate nodal loads without redistributing missing loads.
Cases that lose loaded or restrained DOFs, split into face-disconnected pieces, or retain
rigid motions are reported as blocked. No ersatz material joins missing cells.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amg_bracket import assemble_active, rigid_candidates
from fdmgen.fem.element import CORNERS, box_ke, isotropic_C


def audit_domain(mask, grid, fixed, load):
    mask = np.asarray(mask, bool)
    if mask.shape != tuple(grid.shape):
        raise ValueError('mask shape does not match grid')
    active = np.zeros(tuple(np.array(mask.shape) + 1), bool)
    nx, ny, nz = mask.shape
    for x, y, z in CORNERS:
        active[x:x+nx, y:y+ny, z:z+nz] |= mask
    dofs = np.repeat(active.ravel(), 3)
    fixed, load = np.asarray(fixed, bool), np.asarray(load, float)
    if fixed.shape != dofs.shape or load.shape != dofs.shape or not np.isfinite(load).all():
        raise ValueError('invalid boundary arrays')
    labels, ncomp = ndimage.label(mask)  # face adjacency: edge/point-only joins are not accepted
    sizes = sorted(np.bincount(labels.ravel())[1:].tolist(), reverse=True)
    _, node_components = ndimage.label(mask, structure=np.ones((3, 3, 3), bool))
    missing = (~dofs) & (load != 0)
    missing_fixed = (~dofs) & fixed
    on_fixed = dofs & fixed & (load != 0)
    nodes = np.flatnonzero(active.ravel())
    rank = 0
    if len(nodes):
        B = rigid_candidates(grid.node_coords()[nodes])
        rank = int(np.linalg.matrix_rank(B[fixed[dofs]])) if fixed[dofs].any() else 0
    reasons = []
    if ncomp != 1:
        reasons.append(f'{ncomp} face-connected components; one connected body required')
    if missing.any():
        reasons.append('original loaded DOFs are absent; loads were not redistributed')
    if missing_fixed.any():
        reasons.append('original fixed DOFs are absent; restraints were not relocated')
    if on_fixed.any():
        reasons.append('loaded DOFs are constrained; loads were not silently zeroed')
    if rank != 6:
        reasons.append(f'retained restraints constrain {rank} of 6 rigid motions')
    return dict(status='blocked' if reasons else 'ready', reasons=reasons,
                cells=int(mask.sum()), active_nodes=len(nodes), face_components=int(ncomp),
                face_component_cell_counts=sizes, node_connected_components=int(node_components),
                restrained_rigid_modes=rank, original_fixed_dofs=int(fixed.sum()),
                retained_fixed_dofs=int((fixed & dofs).sum()),
                missing_fixed_dofs=int(missing_fixed.sum()),
                missing_loaded_dofs=int(missing.sum()), loaded_fixed_dofs=int(on_fixed.sum()),
                missing_load_l1_N=float(np.abs(load[missing]).sum()),
                original_resultant_grid_N=load.reshape(-1, 3).sum(axis=0).tolist(),
                retained_resultant_grid_N=np.where(dofs, load, 0).reshape(-1, 3).sum(axis=0).tolist())


def read_occupancy(path, receipt, receipt_sha):
    with np.load(path, allow_pickle=False) as z:
        density = np.asarray(z['density'], float)
        provenance = json.loads(str(z['provenance']))
    if provenance.get('grid_receipt_sha256') != receipt_sha:
        raise ValueError('occupancy references a different grid receipt')
    for key in ('grid', 'installed_to_print'):
        if provenance.get(key) != receipt[key]:
            raise ValueError(f'occupancy {key} does not match reference')
    if density.shape != tuple(receipt['grid']['shape']) or not np.isfinite(density).all() or (density < 0).any():
        raise ValueError('density must be a finite nonnegative field on the common grid')
    return density, provenance


def solve(mask, grid, fixed, load, maxiter):
    import pyamg
    from scipy.sparse.linalg import cg
    start = time.perf_counter()
    A, ids = assemble_active(mask.astype(float), box_ke(isotropic_C(1000., .3), *grid.h), fixed)
    rhs = load[ids].copy()
    B = rigid_candidates(grid.node_coords()[ids[::3]//3]); B[fixed[ids] != 0] = 0
    np.random.seed(0)
    ml = pyamg.smoothed_aggregation_solver(A.tobsr(blocksize=(3, 3)), B=B, symmetry='symmetric',
        smooth='energy', max_coarse=100, coarse_solver='splu',
        presmoother=('block_gauss_seidel', {'sweep':'symmetric'}),
        postsmoother=('block_gauss_seidel', {'sweep':'symmetric'}))
    setup_s = time.perf_counter()-start
    count = []
    start = time.perf_counter()
    # Leave margin for the independently recomputed true residual (acceptance 1e-8).
    u, status = cg(A, rhs, M=ml.aspreconditioner(), rtol=1e-9, atol=0, maxiter=maxiter,
                   callback=lambda _:count.append(1))
    residual = float(np.linalg.norm(rhs-A@u)/np.linalg.norm(rhs))
    valid = status == 0 and np.isfinite(residual) and residual <= 1e-8
    return dict(status='solved' if valid else 'unconverged', iterations=len(count),
        cg_status=int(status), true_relative_residual=residual, setup_s=setup_s,
        solve_s=time.perf_counter()-start, dofs=len(ids),
        compliance_N_mm=float(rhs@u) if valid else None,
        max_displacement_mm=float(np.linalg.norm(u.reshape(-1, 3), axis=1).max()) if valid else None)


def main():
    from bracket_gate import build
    from fdmgen.adapters.spool_bracket import HANDOFF
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--baseline', type=Path, required=True)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--threshold', type=float, default=.5)
    ap.add_argument('--maxiter', type=int, default=500)
    ap.add_argument('--audit-only', action='store_true')
    args = ap.parse_args()
    if not np.isfinite(args.threshold) or not 0 < args.threshold <= 1:
        ap.error('threshold must be in (0, 1]')
    raw = args.reference.read_bytes(); reference = json.loads(raw)
    ref_sha = hashlib.sha256(raw).hexdigest()
    if hashlib.sha256((args.root/HANDOFF/'body-only.stl').read_bytes()).hexdigest() != reference['mesh_sha256']:
        raise ValueError('body mesh differs from pinned reference')
    fields = {}
    for name, path in [('baseline', args.baseline), ('project', args.project)]:
        fields[name] = read_occupancy(path, reference, ref_sha)
    if any(fields['baseline'][1].get(k) != fields['project'][1].get(k)
           for k in ('table_sha256', 'pose', 'pose_R_design_to_print', 'pose_t_mm')):
        raise ValueError('baseline/project pose or table differs')
    br, full, grid, fixed, load, bc = build(args.root, tuple(reference['grid']['h_mm']))
    if tuple(grid.shape) != tuple(reference['grid']['shape']) or not np.allclose(grid.origin, reference['grid']['origin_print_mm'], atol=1e-10, rtol=0):
        raise ValueError('rebuilt full-body grid differs from the pinned grid')
    if not np.allclose(br.R_I_to_P, reference['installed_to_print']['R']) or not np.allclose(br.t_I_to_P, reference['installed_to_print']['t_mm']):
        raise ValueError('rebuilt frame differs from the pinned transform')
    if bc != reference['bc']:
        raise ValueError('rebuilt boundary selection differs from pinned reference')
    result = dict(schema='fdmgen/occupancy-mechanics-pilot@0.1', threshold=args.threshold,
        reference_sha256=ref_sha, grid=reference['grid'], bc=bc,
        load_sha256=hashlib.sha256(load.tobytes()).hexdigest(), material=dict(E_MPa=1000., nu=.3),
        establishes='isotropic thresholded-raster screening with original solver-gate boundary arrays',
        does_not_establish=['printed-material truth', 'bond continuity', 'contact realism', 'mesh convergence',
                           'anisotropic strength', 'physical qualification'], cases={})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    for name in ('full_solid', 'baseline', 'project'):
        mask = full if name == 'full_solid' else fields[name][0] >= args.threshold
        row = dict(audit=audit_domain(mask, grid, fixed, load))
        if name != 'full_solid':
            path = args.baseline if name == 'baseline' else args.project
            row.update(npz_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), provenance=fields[name][1],
                       cells_outside_full_body=int((mask & ~full).sum()))
        result['cases'][name] = row
        save()
        print(name, row['audit'], flush=True)
        if row['audit']['status'] == 'ready' and not args.audit_only:
            row['solve'] = solve(mask, grid, fixed, load, args.maxiter)
            if name == 'full_solid' and row['solve']['status'] == 'solved':
                expected = reference['compliance_N_mm']
                row['reference_compliance_relative_difference'] = abs(row['solve']['compliance_N_mm']-expected)/expected
                if row['reference_compliance_relative_difference'] > 1e-6:
                    row['solve']['status'] = 'reference_mismatch'
            save(); print(name, row['solve'], flush=True)
    solved = [result['cases'][name].get('solve', {}).get('status') == 'solved' for name in ('full_solid', 'baseline', 'project')]
    if all(solved):
        a, b = (result['cases'][name]['solve']['compliance_N_mm'] for name in ('baseline', 'project'))
        result['project_compliance_change_fraction'] = (b-a)/a
    else:
        result['comparison_status'] = 'not established; inspect audits/solver results'
    save()


if __name__ == '__main__':
    main()
