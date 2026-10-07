"""Export a fully solid R1 bracket stress prescreen, not printed-material truth."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from scipy.sparse.linalg import cg
import pyamg
from amg_bracket import assemble_active, rigid_candidates
from bracket_gate import build
from fdmgen.fem.element import CORNERS, box_ke, isotropic_C
from fdmgen.fem.stress import centre_stress, rotate_stress
from fdmgen.adapters.spool_bracket import HANDOFF, interface_loads, TOTAL_LOAD_N


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--h', type=float, default=1.6)
    args = ap.parse_args()
    if not np.isfinite(args.h) or args.h <= 0:
        ap.error('h must be finite and positive')
    np.random.seed(0)
    t = time.perf_counter()
    br, mask, grid, fixed, load, bc = build(args.root, (args.h,)*3)
    C = isotropic_C(1000, .3)
    A, gdofs = assemble_active(mask.astype(float), box_ke(C, *grid.h), fixed)
    rhs = load[gdofs].copy(); rhs[fixed[gdofs] != 0] = 0
    B = rigid_candidates(grid.node_coords()[gdofs[::3]//3]); B[fixed[gdofs] != 0] = 0
    ml = pyamg.smoothed_aggregation_solver(A.tobsr(blocksize=(3, 3)), B=B, symmetry='symmetric',
          smooth='energy', max_coarse=100, coarse_solver='splu',
          presmoother=('block_gauss_seidel', {'sweep':'symmetric'}),
          postsmoother=('block_gauss_seidel', {'sweep':'symmetric'}))
    iterations = []
    u, status = cg(A, rhs, M=ml.aspreconditioner(), rtol=1e-8, atol=0, maxiter=300,
                   callback=lambda x: iterations.append(1))
    residual = float(np.linalg.norm(rhs-A@u)/np.linalg.norm(rhs))
    if status or not np.isfinite(residual) or residual > 1e-8:
        raise RuntimeError(f'unconverged stress source: status={status}, residual={residual}')
    full = np.zeros(len(load)); full[gdofs] = u
    cells = np.argwhere(mask)
    corners = cells[:, None, :] + CORNERS[None, :, :]
    _, ny, nz = grid.shape
    nodes = (corners[..., 0]*(ny+1)+corners[..., 1])*(nz+1)+corners[..., 2]
    stress_p = centre_stress(full.reshape(-1, 3)[nodes], C, grid.h)
    # P = R I + t; row-vector points I = (P-t) R; stress I = R.T stress P R.
    centres_p = np.asarray(grid.origin)+(cells+.5)*np.asarray(grid.h)
    centres_i = (centres_p-br.t_I_to_P) @ br.R_I_to_P
    stress_i = rotate_stress(stress_p, br.R_I_to_P.T)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, schema=np.array('fdmgen.stress-field.v1'), frame=np.array('installed'),
        voigt_order=np.array(['xx', 'yy', 'zz', 'yz', 'xz', 'xy']), centres_mm=centres_i,
        stress_mpa=stress_i, cell_volume_mm3=np.full(len(cells), np.prod(grid.h)),
        cell_indices=cells, solid_mask=mask)
    receipt = dict(schema='fdmgen.stress-field.v1', frame='installed', sampling='cell centre',
        establishes='linear fully-solid-envelope stress prescreen under the G2 full load',
        does_not_establish=['printed shell/helper truth', 'stress peaks within a cell', 'contact realism',
                           'mesh convergence', 'physical qualification'],
        material=dict(model='isotropic', E_MPa=1000., nu=.3, density=1.),
        restraint_model='mount bores clamped; wall bilateral roller; solver-gate simplification',
        load_total_N=TOTAL_LOAD_N, loads_installed_N={k:v.tolist() for k,v in interface_loads(TOTAL_LOAD_N).items()},
        installed_to_print=dict(R=br.R_I_to_P.tolist(), t_mm=br.t_I_to_P.tolist()),
        grid=dict(shape=list(grid.shape), h_mm=list(grid.h), origin_print_mm=list(grid.origin)),
        bc=bc, cells=len(cells), dofs=len(gdofs), iterations=len(iterations), true_relative_residual=residual,
        compliance_N_mm=float(rhs@u), elapsed_s=time.perf_counter()-t,
        stress_sha256=hashlib.sha256(args.out.read_bytes()).hexdigest(),
        mesh_sha256=hashlib.sha256((args.root/HANDOFF/'body-only.stl').read_bytes()).hexdigest(),
        versions=dict(numpy=np.__version__, pyamg=pyamg.__version__))
    args.out.with_suffix('.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    main()
