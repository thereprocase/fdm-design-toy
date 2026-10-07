"""Explicit seat-load transfer for occupancy experiments, not a contact model.

Keep each seat's original force direction and resultant moment, with nonnegative
nodal weights closest to uniform on the surviving original bearing-side nodes.
Use the common node set for both slices so their new load arrays are identical.
No cells or restraints are repaired; connectivity remains separately audited.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import minimize
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_occupancy import audit_domain, read_occupancy, solve
from fdmgen.fem.element import CORNERS


def transfer_weights(original_points, target_points, force):
    original, target, force = (np.asarray(x, float) for x in (original_points, target_points, force))
    if (original.ndim != 2 or target.ndim != 2 or original.shape[1:] != (3,) or target.shape[1:] != (3,)
            or not len(original) or not len(target) or force.shape != (3,)
            or not all(np.isfinite(x).all() for x in (original, target, force)) or np.linalg.norm(force) == 0):
        raise ValueError('finite nonempty point sets and a nonzero force are required')
    direction = force/np.linalg.norm(force)
    origin = original.mean(axis=0)
    scale = max(float(np.linalg.norm(target-origin, axis=1).max()), 1.)
    A = np.vstack([np.ones(len(target)), np.cross((target-origin)/scale, direction).T])
    # Original weights are uniform. Centring at their centroid makes the target moment zero.
    b = np.array([1., 0., 0., 0.])
    U, singular, _ = np.linalg.svd(A, full_matrices=False)
    rank = int((singular > singular[0]*1e-12).sum())
    basis = U[:, :rank]
    if np.linalg.norm(b-basis@(basis.T@b)) > 1e-10:
        raise ValueError('target nodes cannot preserve the original seat moment')
    C, d = basis.T@A, basis.T@b
    uniform = np.full(len(target), 1/len(target))
    result = minimize(lambda w:.5*len(w)*np.sum((w-uniform)**2), uniform,
        jac=lambda w:len(w)*(w-uniform), method='SLSQP', bounds=[(0., 1.)]*len(target),
        constraints={'type':'eq', 'fun':lambda w:C@w-d, 'jac':lambda w:C},
        options={'ftol':1e-12, 'maxiter':200})
    if not result.success or np.min(result.x) < -1e-12 or np.linalg.norm(A@result.x-b) > 1e-9:
        raise ValueError('no converged nonnegative force/moment-preserving transfer: '+result.message)
    weights = np.maximum(result.x, 0.)
    forces = weights[:, None]*force
    resultant = forces.sum(axis=0)
    original_moment = np.cross(original, force/len(original)).sum(axis=0)
    moment = np.cross(target, forces).sum(axis=0)
    force_error = float(np.linalg.norm(resultant-force))
    moment_error = float(np.linalg.norm(moment-original_moment))
    if force_error > 1e-9 or moment_error > 1e-7:
        raise ValueError('transfer exceeds force or moment conservation tolerance')
    return weights, dict(original_nodes=len(original), target_nodes=len(target),
        weight_min=float(weights.min()), weight_max=float(weights.max()),
        uniform_weight=1/len(target), relative_weight_l2=float(np.linalg.norm(weights-uniform)/np.linalg.norm(uniform)),
        original_force_N=force.tolist(), transferred_force_N=resultant.tolist(),
        original_moment_about_grid_frame_zero_N_mm=original_moment.tolist(),
        transferred_moment_about_grid_frame_zero_N_mm=moment.tolist(),
        force_error_N=force_error, moment_error_N_mm=moment_error)


def active_nodes(mask):
    shape = mask.shape
    active = np.zeros(tuple(np.array(shape)+1), bool)
    for x, y, z in CORNERS:
        active[x:x+shape[0], y:y+shape[1], z:z+shape[2]] |= mask
    return active.ravel()


def largest_face_component(mask):
    labels, count = ndimage.label(mask)
    if not count:
        raise ValueError('empty material domain')
    sizes = np.bincount(labels.ravel()); sizes[0] = 0
    winner = int(np.argmax(sizes))
    return labels == winner, dict(original_cells=int(mask.sum()), retained_cells=int(sizes[winner]),
        removed_cells=int(mask.sum()-sizes[winner]),
        removed_component_cell_counts=sorted(np.delete(sizes[1:], winner-1).tolist(), reverse=True))


def original_seats(br, full, grid, fixed):
    from fdmgen.adapters import spool_bracket as sb
    P = grid.node_coords(); active = active_nodes(full); tol = max(grid.h)
    seats = {}
    for name, (x, y) in sb.ROD_AXES_I.items():
        rel = P-br.to_print([x, y, 0.]); axis = br.vec_to_print([0., 0., 1.])
        radial = rel-np.outer(rel@axis, axis); radius = np.linalg.norm(radial, axis=1)
        force = br.loads_print()[name]; direction = force/np.linalg.norm(force)
        selected = active & (radius >= sb.SEAT_RADIUS[0]-tol) & (radius <= sb.SEAT_RADIUS[1]+tol) & \
                   ((radial@direction) > .3*radius) & (fixed[::3] == 0)
        seats[name] = (np.flatnonzero(selected), force)
    return seats


def main():
    from bracket_gate import build
    from fdmgen.adapters.spool_bracket import HANDOFF
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'reference', 'baseline', 'project', 'out'):
        ap.add_argument('--'+key, type=Path, required=True)
    ap.add_argument('--threshold', type=float, default=.5)
    ap.add_argument('--largest-face-component', action='store_true', help='explicit fragment-removal sensitivity, not the raw domain')
    ap.add_argument('--solve', action='store_true', help='solve audited domains with the transferred common load')
    args = ap.parse_args()
    if not np.isfinite(args.threshold) or not 0 < args.threshold <= 1:
        ap.error('threshold must be in (0, 1]')
    raw = args.reference.read_bytes(); ref = json.loads(raw); sha = hashlib.sha256(raw).hexdigest()
    fields = {name:read_occupancy(path, ref, sha) for name, path in [('baseline', args.baseline), ('project', args.project)]}
    if any(fields['baseline'][1].get(k) != fields['project'][1].get(k)
           for k in ('table_sha256', 'pose', 'pose_R_design_to_print', 'pose_t_mm')):
        raise ValueError('slice pose/table provenance differs')
    br, full, grid, fixed, original_load, bc = build(args.root, tuple(ref['grid']['h_mm']))
    if (bc != ref['bc'] or tuple(grid.shape) != tuple(ref['grid']['shape'])
        or not np.allclose(grid.origin, ref['grid']['origin_print_mm'], atol=1e-10, rtol=0)
        or not np.array_equal(br.R_I_to_P, ref['installed_to_print']['R'])
        or not np.array_equal(br.t_I_to_P, ref['installed_to_print']['t_mm'])
        or hashlib.sha256((args.root/HANDOFF/'body-only.stl').read_bytes()).hexdigest() != ref['mesh_sha256']):
        raise ValueError('rebuilt grid, boundary selection, transform or mesh differs from pinned reference')
    masks = {name:density >= args.threshold for name, (density, _) in fields.items()}
    masks['full_solid'] = full
    fragment_policy = {}
    if args.largest_face_component:
        for name, mask in masks.items():
            kept, record = largest_face_component(mask)
            removed_nodes = active_nodes(mask) & ~active_nodes(kept)
            record.update(removed_volume_mm3=record['removed_cells']*float(np.prod(grid.h)),
                removed_original_load_l1_N=float(np.abs(original_load.reshape(-1, 3)[removed_nodes]).sum()),
                removed_fixed_dofs=int(fixed.reshape(-1, 3)[removed_nodes].sum()))
            fragment_policy[name] = record
            masks[name] = kept
    common = active_nodes(masks['baseline']) & active_nodes(masks['project']) & active_nodes(masks['full_solid'])
    P = grid.node_coords(); reconstructed = np.zeros_like(original_load).reshape(-1, 3)
    transferred = np.zeros_like(reconstructed); records = {}
    for name, (ids, force) in original_seats(br, full, grid, fixed).items():
        reconstructed[ids] += force/len(ids)
        target = ids[common[ids]]
        weights, records[name] = transfer_weights(P[ids], P[target], force)
        transferred[target] += weights[:, None]*force
        records[name]['target_node_indices_sha256'] = hashlib.sha256(target.astype('<i8').tobytes()).hexdigest()
    if not np.allclose(reconstructed.ravel(), original_load, atol=1e-13, rtol=0):
        raise ValueError('per-seat reconstruction differs from original solver loads')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    load_path = args.out.with_suffix('.npz')
    np.savez_compressed(load_path, original_load=original_load, transferred_load=transferred.ravel(), fixed=fixed)
    receipt = dict(schema='fdmgen/seat-load-transfer-pilot@0.1', reference_sha256=sha, threshold=args.threshold,
        method='nonnegative fixed-direction nodal forces, closest uniform weights, per-seat force and moment constraints',
        candidate_policy='intersection of baseline/project/full-solid active nodes with original bearing-side nodes',
        domain_policy='largest-face-component sensitivity' if args.largest_face_component else 'unmodified threshold masks',
        fragment_removal=fragment_policy,
        context_note='Centre-sampled full solid is contextual, not a guaranteed upper stiffness bound: raster boundary cells differ.',
        establishes='common redistributed load arrays preserving each original seat resultant and moment',
        does_not_establish=['equivalent local pressure/contact physics', 'unchanged compliance', 'connected material',
                           'printed-material truth', 'physical qualification'], seats=records,
        original_load_sha256=hashlib.sha256(original_load.tobytes()).hexdigest(),
        transferred_load_sha256=hashlib.sha256(transferred.ravel().tobytes()).hexdigest(),
        load_npz_sha256=hashlib.sha256(load_path.read_bytes()).hexdigest(),
        inputs={name:dict(npz_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), provenance=fields[name][1])
                for name, path in [('baseline', args.baseline), ('project', args.project)]},
        audits={name:audit_domain(mask, grid, fixed, transferred.ravel()) for name, mask in masks.items()})
    args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(seats=records, audits=receipt['audits'], fragment_removal=fragment_policy), indent=2), flush=True)
    if args.solve:
        receipt['solves'] = {}
        for name in ('full_solid', 'baseline', 'project'):
            if receipt['audits'][name]['status'] != 'ready':
                receipt['solves'][name] = {'status':'blocked_by_audit'}
            else:
                receipt['solves'][name] = solve(masks[name], grid, fixed, transferred.ravel(), 500)
            args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
            print(name, receipt['solves'][name], flush=True)
        if all(receipt['solves'][name]['status'] == 'solved' for name in masks):
            a, b = (receipt['solves'][name]['compliance_N_mm'] for name in ('baseline', 'project'))
            receipt['project_compliance_change_fraction'] = (b-a)/a
            args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
