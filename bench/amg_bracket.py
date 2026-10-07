"""CPU masked-bracket solver pilot (#4), intended for the RAM-rich compute box.

Optional experiment dependency: PyAMG. No production solver changes.
Assembles only active cells/nodes; compares a sparse direct reference with
smoothed aggregation using six elasticity rigid-body candidate vectors.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import cg, splu
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fdmgen.fem import element


def assemble_active(E, Ke, fixed):
    """Return constrained CSR and its global DOF map, retaining nodal 3x3 blocks.

    Zero-stiffness cells and nodes incident only to those cells are omitted.
    Homogeneous fixed DOFs remain identity rows/columns, matching the reference.
    """
    E = np.asarray(E, dtype=np.float64)
    if E.ndim != 3 or not np.isfinite(E).all() or (E < 0).any() or not E.any():
        raise ValueError('E must be a nonempty finite nonnegative 3D active field')
    nx, ny, nz = E.shape
    if np.asarray(Ke).shape != (24, 24):
        raise ValueError('Ke must be 24x24')
    if np.asarray(fixed).shape != (3*(nx+1)*(ny+1)*(nz+1),):
        raise ValueError('fixed must match the full grid DOF count')
    cells = np.argwhere(E > 0)
    corners = cells[:, None, :] + element.CORNERS[None, :, :]
    cell_nodes = (corners[:, :, 0]*(ny+1)+corners[:, :, 1])*(nz+1)+corners[:, :, 2]
    nodes, inverse = np.unique(cell_nodes, return_inverse=True)
    dofs = (3*inverse.reshape(-1, 8, 1)+np.arange(3)).reshape(-1, 24)
    global_dofs = (3*nodes[:, None]+np.arange(3)).ravel()
    rows = np.repeat(dofs, 24, axis=1).ravel()
    cols = np.tile(dofs, (1, 24)).ravel()
    data = (E[tuple(cells.T)][:, None]*np.asarray(Ke).ravel()[None, :]).ravel()
    A = sparse.coo_matrix((data, (rows, cols)), shape=(len(global_dofs),)*2).tocsr()
    f = np.asarray(fixed)[global_dofs].astype(bool)
    keep = sparse.diags((~f).astype(float))
    A = (keep @ A @ keep + sparse.diags(f.astype(float))).tocsr()
    A.eliminate_zeros()
    return A, global_dofs


def rigid_candidates(points):
    """Three translations and three rotations, with dimensionless coordinates."""
    points = np.asarray(points, float)
    q = points-points.mean(axis=0)
    q /= max(float(np.linalg.norm(q, axis=1).max()), 1.0)
    B = np.zeros((len(points), 3, 6))
    B[:, :, :3] = np.eye(3)
    # e_axis cross position
    for axis in range(3):
        B[:, :, 3+axis] = np.cross(np.eye(3)[axis], q)
    return B.reshape(-1, 6)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--h', type=float, default=1.6)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--skip-direct', action='store_true', help='defer the expensive direct reference; report true residuals only')
    ap.add_argument('--maxiter', type=int, default=300)
    ap.add_argument('--emin', type=float, default=1e-6)
    ap.add_argument('--density', type=float, default=0.5)
    args = ap.parse_args()
    if not np.isfinite(args.h) or not 0 < args.h or not 0 < args.emin <= 1 or not 0 < args.density <= 1 or args.maxiter < 1:
        ap.error('spacing, stiffness, density and iteration cap must be positive and physically valid')
    np.random.seed(0)
    import pyamg
    import scipy
    from bracket_gate import build
    from fdmgen.adapters.spool_bracket import HANDOFF

    receipt = dict(evidence='measured CPU assembled-operator experiment', machine_role='compute box',
                   establishes='accuracy and iteration counts for this masked uniform-density design problem',
                   does_not_establish='GPU speed, production interpolation, full gate sweeps or physical qualification',
                   h_mm=args.h, emin=args.emin, density=args.density, direct_reference_requested=not args.skip_direct, rows=[],
                   versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__, pyamg=pyamg.__version__),
                   mesh_sha256=hashlib.sha256((args.root/HANDOFF/'body-only.stl').read_bytes()).hexdigest())
    def save():
        receipt['peak_process_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        args.out.write_text(json.dumps(receipt, indent=2)+'\n')
    t0 = time.perf_counter()
    _, occ, grid, fixed, b, bc = build(args.root, (args.h,)*3)
    E = np.where(occ, args.emin+args.density**3*(1-args.emin), 0)
    Ke = element.box_ke(element.isotropic_C(1, 0.3), *grid.h)
    A, gdofs = assemble_active(E, Ke, fixed)
    rhs = b[gdofs].copy(); rhs[fixed[gdofs] != 0] = 0
    B = rigid_candidates(grid.node_coords()[gdofs[::3]//3])
    B[fixed[gdofs] != 0] = 0
    receipt.update(grid=grid.shape, body_cells=int(occ.sum()), dofs=A.shape[0], nnz=A.nnz,
                   assembly_s=time.perf_counter()-t0, bc=bc,
                   rhs_sha256=hashlib.sha256(rhs.tobytes()).hexdigest())
    save(); print('assembled', receipt['dofs'], 'DOFs', receipt['nnz'], 'nonzeros', flush=True)
    ref = None
    if not args.skip_direct:
        t0 = time.perf_counter()
        lu = splu(A.tocsc(), permc_spec='MMD_AT_PLUS_A')
        factor_s = time.perf_counter()-t0
        t0 = time.perf_counter(); ref = lu.solve(rhs); direct_s = time.perf_counter()-t0
        ref_res = float(np.linalg.norm(rhs-A@ref)/np.linalg.norm(rhs))
        ref_compliance = float(rhs@ref)
        receipt['direct'] = dict(factor_s=factor_s, solve_s=direct_s, true_rel_res=ref_res,
                                 compliance=ref_compliance, factor_nnz=int(lu.L.nnz+lu.U.nnz))
        save(); del lu
        if not np.isfinite(ref_res) or ref_res > 1e-8 or ref_compliance <= 0:
            raise RuntimeError('direct reference is not sufficiently accurate/positive')
        print('direct reference', receipt['direct'], flush=True)
    for name, candidates, smooth in [('translations', B[:, :3], 'jacobi'),
                                      ('rigid6', B, 'jacobi'),
                                      ('rigid6_energy', B, 'energy')]:
        t0 = time.perf_counter()
        ml = pyamg.smoothed_aggregation_solver(A.tobsr(blocksize=(3,3)), B=candidates,
                symmetry='symmetric', smooth=smooth, max_coarse=100,
                presmoother=('block_gauss_seidel', {'sweep':'symmetric'}),
                postsmoother=('block_gauss_seidel', {'sweep':'symmetric'}), coarse_solver='splu')
        setup_s = time.perf_counter()-t0
        history = []
        def callback(x):
            history.append(float(np.linalg.norm(rhs-A@x)/np.linalg.norm(rhs)))
        t0 = time.perf_counter()
        u, status = cg(A, rhs, M=ml.aspreconditioner(), rtol=1e-6, atol=0,
                       maxiter=args.maxiter, callback=callback)
        solve_s = time.perf_counter()-t0
        row = dict(variant=name, iterations=len(history), status=int(status), setup_s=setup_s,
                   solve_s=solve_s, true_rel_res=float(np.linalg.norm(rhs-A@u)/np.linalg.norm(rhs)),
                   compliance=float(rhs@u), compliance_rel_diff=None if ref is None else float(abs(rhs@u-ref_compliance)/abs(ref_compliance)),
                   displacement_rel_l2=None if ref is None else float(np.linalg.norm(u-ref)/np.linalg.norm(ref)),
                   operator_complexity=float(ml.operator_complexity()),
                   levels=[int(l.A.shape[0]) for l in ml.levels], history=history,
                   timing_note='includes one explicit residual matvec per iteration for diagnostics')
        receipt['rows'].append(row); save()
        print(name, row['iterations'], 'iterations', row['true_rel_res'], 'residual', round(solve_s,3), 's', flush=True)
        del ml


if __name__ == '__main__':
    main()
