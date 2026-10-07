"""Density-weighted R1 sensitivity; uncalibrated homogenisation, not print truth."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_occupancy import audit_domain, read_occupancy, solve
from seat_load_transfer import active_nodes, largest_face_component


def stiffness_fraction(density, power):
    density = np.asarray(density, dtype=float)
    if power not in (1, 3):
        raise ValueError('power must be 1 or 3 for this sensitivity')
    if density.ndim != 3 or not np.isfinite(density).all() or (density < 0).any():
        raise ValueError('density must be a finite nonnegative 3D field')
    return np.minimum(density, 1.)**power


def main():
    from bracket_gate import build
    from fdmgen.adapters.spool_bracket import HANDOFF
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'reference', 'baseline', 'project', 'out'):
        ap.add_argument('--'+name, type=Path, required=True)
    ap.add_argument('--power', type=int, choices=(1, 3), required=True)
    ap.add_argument('--largest-face-component', action='store_true')
    ap.add_argument('--solve', action='store_true')
    args = ap.parse_args()
    raw = args.reference.read_bytes(); ref = json.loads(raw)
    sha = hashlib.sha256(raw).hexdigest()
    paths = {'baseline': args.baseline, 'project': args.project}
    fields = {k:read_occupancy(p, ref, sha) for k, p in paths.items()}
    for key in ('table_sha256', 'pose', 'pose_R_design_to_print', 'pose_t_mm'):
        if fields['baseline'][1].get(key) != fields['project'][1].get(key):
            raise ValueError('baseline/project pose or table differs')
    br, full, grid, fixed, load, bc = build(args.root, tuple(ref['grid']['h_mm']))
    if (bc != ref['bc'] or tuple(grid.shape) != tuple(ref['grid']['shape'])
        or not np.allclose(grid.origin, ref['grid']['origin_print_mm'], atol=1e-10, rtol=0)
        or not np.array_equal(br.R_I_to_P, ref['installed_to_print']['R'])
        or not np.array_equal(br.t_I_to_P, ref['installed_to_print']['t_mm'])
        or hashlib.sha256((args.root/HANDOFF/'body-only.stl').read_bytes()).hexdigest() != ref['mesh_sha256']):
        raise ValueError('rebuilt grid, boundaries, frame or mesh differs from reference')
    receipt = dict(schema='fdmgen/density-weighted-mechanics-pilot@0.1', reference_sha256=sha,
        material=dict(E0_MPa=1000., nu=.3, law='E/E0 = min(raw_density, 1)^power', power=args.power,
                      stiffness_floor=0, evidence='uncalibrated homogenisation assumption'),
        grid=ref['grid'], installed_to_print=ref['installed_to_print'], bc=bc,
        load_policy='original full-body nodal loads and restraints; no transfer or deletion',
        load_sha256=hashlib.sha256(load.tobytes()).hexdigest(),
        domain_policy='largest face component of positive-density cells' if args.largest_face_component else 'all positive-density cells',
        establishes='density-law sensitivity of a coarse isotropic linear FE model',
        does_not_establish=['resolved bead gaps or bonds', 'calibrated stiffness-density law',
          'mesh convergence', 'anisotropic strength', 'physical movement or qualification',
          'equivalence to the thresholded and load-transferred pilot'], cases={})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    for name in ('full_solid', 'baseline', 'project'):
        density = full.astype(float) if name == 'full_solid' else fields[name][0]
        weights = stiffness_fraction(density, args.power); mask = weights > 0
        row = dict(raw_audit=audit_domain(mask, grid, fixed, load))
        if name != 'full_solid':
            row.update(npz_sha256=hashlib.sha256(paths[name].read_bytes()).hexdigest(), provenance=fields[name][1])
        if args.largest_face_component:
            kept, removed = largest_face_component(mask)
            lost = active_nodes(mask) & ~active_nodes(kept)
            removed.update(removed_grid_volume_mm3=removed['removed_cells']*float(np.prod(grid.h)),
                removed_deposited_volume_mm3=float(density[mask & ~kept].sum()*np.prod(grid.h)),
                removed_original_load_l1_N=float(np.abs(load.reshape(-1, 3)[lost]).sum()),
                removed_fixed_dofs=int(fixed.reshape(-1, 3)[lost].sum()))
            row['fragment_removal'] = removed
            weights = np.where(kept, weights, 0); mask = kept
        row['audit'] = audit_domain(mask, grid, fixed, load)
        row['positive_stiffness_fraction_min'] = float(weights[mask].min()) if mask.any() else None
        row['cells_outside_full_body'] = int((mask & ~full).sum())
        receipt['cases'][name] = row; save()
        if args.solve and row['audit']['status'] == 'ready':
            row['solve'] = solve(weights, grid, fixed, load, 500)
        elif args.solve:
            row['solve'] = {'status':'blocked_by_audit'}
        save(); print(name, row['audit']['status'], row.get('solve', {}), flush=True)
    if all(receipt['cases'][n].get('solve', {}).get('status') == 'solved' for n in ('baseline','project')):
        a, b = (receipt['cases'][n]['solve']['compliance_N_mm'] for n in ('baseline','project'))
        receipt['project_compliance_change_fraction'] = (b-a)/a
    else:
        receipt['comparison_status'] = 'not established; inspect audits and solves'
    save()


if __name__ == '__main__':
    main()
