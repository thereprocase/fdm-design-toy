"""Export a CPU auxiliary AMG cycle for independent GPU arithmetic experiments.

This benchmark does not change the production solver or its pinned Warp version.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import cg, spsolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amg_bracket import assemble_active, rigid_candidates
from amg_relaxation import configure_relaxation
from ti_density_weighted import array_sha, layer_axis, material_spec

SCHEMA = 'fdmgen/amg-transfer@0.1'


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cycle(matrices, rhs, levels, i=0):
    if i == levels-1:
        return matrices['coarse'] @ rhs
    A, D = matrices[f'A{i}'], matrices[f'D{i}']
    x = D @ rhs
    x += matrices[f'P{i}'] @ cycle(matrices, matrices[f'R{i}'] @ (rhs-A@x), levels, i+1)
    return x + D @ (rhs-A@x)


def export(weights, grid, fixed, load, C, path, provenance, *, maxiter=120, direct=False):
    """Build and pin the residual-Jacobi/pinv recipe, including a CPU solve."""
    import pyamg
    import scipy
    from fdmgen.fem.element import box_ke, isotropic_C
    if maxiter < 1:
        raise ValueError('maxiter must be positive')
    weights = np.asarray(weights, float)
    C = np.asarray(C, float)
    if (weights.shape != tuple(grid.shape) or not np.isfinite(weights).all()
            or (weights < 0).any() or not (weights > 0).any()):
        raise ValueError('weights must be finite, nonnegative and nonempty on the grid')
    if (C.shape != (6, 6) or not np.isfinite(C).all()
            or not np.allclose(C, C.T, atol=1e-12, rtol=1e-12)
            or np.linalg.eigvalsh(C).min() <= 0):
        raise ValueError('C must be symmetric positive definite')
    start = time.perf_counter()
    A, ids = assemble_active(weights, box_ke(C, *grid.h), fixed)
    aux, aux_ids = assemble_active(weights, box_ke(isotropic_C(1000, .3), *grid.h), fixed)
    if not np.array_equal(ids, aux_ids):
        raise ValueError('physical and auxiliary domains differ')
    rhs = np.asarray(load[ids], float)
    if not np.isfinite(rhs).all() or np.linalg.norm(rhs) == 0:
        raise ValueError('load must be finite and nonzero')
    B = rigid_candidates(grid.node_coords()[ids[::3]//3]); B[fixed[ids] != 0] = 0
    assembly_s = time.perf_counter()-start
    start = time.perf_counter()
    np.random.seed(0)
    ml = pyamg.smoothed_aggregation_solver(aux.tobsr(blocksize=(3, 3)), B=B,
        symmetry='symmetric', strength=('symmetric', {'theta': 0}), aggregate='standard',
        smooth='energy', max_coarse=100, coarse_solver='pinv',
        presmoother=('block_gauss_seidel', {'sweep': 'symmetric'}),
        postsmoother=('block_gauss_seidel', {'sweep': 'symmetric'}))
    configure_relaxation(ml, 'residual_block_jacobi')
    matrices = {'physical': A}
    for i, level in enumerate(ml.levels):
        matrices[f'A{i}'] = level.A.tocsr()
        if i == len(ml.levels)-1:
            continue
        matrices[f'P{i}'], matrices[f'R{i}'] = level.P.tocsr(), level.R.tocsr()
        pre, post = level.presmoother.keywords, level.postsmoother.keywords
        if pre['iterations'] != 1 or post['iterations'] != 1:
            raise ValueError('only one residual-Jacobi pre/post sweep is supported')
        for key in ('Dinv', 'omega'):
            if not np.array_equal(pre[key], post[key]):
                raise ValueError('pre/post relaxation differs')
        matrices[f'D{i}'] = sparse.block_diag(list(pre['omega']*pre['Dinv']), format='csr')
    matrices['coarse'] = sparse.csr_matrix(np.linalg.pinv(ml.levels[-1].A.toarray()))
    setup_s = time.perf_counter()-start
    n = len(ml.levels)
    probes = np.random.default_rng(7731).normal(size=(2, len(ids)))
    probes[:, fixed[ids] != 0] = 0
    reference = np.array([cycle(matrices, v, n) for v in probes])
    native = np.array([ml.aspreconditioner() @ v for v in probes])
    error = float(np.linalg.norm(reference-native)/np.linalg.norm(native))
    if not np.isfinite(error) or error > 1e-10:
        raise ValueError('exported cycle differs from installed PyAMG')
    count = []; start = time.perf_counter()
    u, status = cg(A, rhs, M=ml.aspreconditioner(), rtol=1e-9, atol=0, maxiter=maxiter,
                   callback=lambda _: count.append(1))
    residual = float(np.linalg.norm(rhs-A@u)/np.linalg.norm(rhs))
    solve_s = time.perf_counter()-start
    if status != 0 or not np.isfinite(residual) or residual > 1e-8:
        raise ValueError(f'CPU reference did not converge: status={status}, true residual={residual}')
    arrays = dict(load=rhs, rhs=probes, fp64_reference=reference)
    solve = dict(iterations=len(count), true_relative_residual=residual,
        compliance_N_mm=float(rhs@u), max_displacement_mm=float(np.linalg.norm(u.reshape(-1, 3), axis=1).max()))
    if direct:
        if len(ids) > 10000:
            raise ValueError('direct reference is limited to 10000 DOFs')
        exact = spsolve(A, rhs)
        if np.linalg.norm(rhs-A@exact)/np.linalg.norm(rhs) > 1e-8:
            raise ValueError('direct reference failed true residual check')
        arrays['direct_solution'] = exact
        solve['relative_direct_solution_error'] = float(np.linalg.norm(u-exact)/np.linalg.norm(exact))
    metadata = dict(schema=SCHEMA, levels=n, dofs=[int(l.A.shape[0]) for l in ml.levels],
        matrices={}, provenance=provenance, reference_solve=solve,
        C_grid_MPa=C.tolist(), C_sha256=array_sha(C), active_ids_sha256=array_sha(ids),
        weights_sha256=array_sha(weights), fixed_sha256=array_sha(fixed), B_sha256=array_sha(B),
        recipe=dict(auxiliary='isotropic E1000 MPa nu0.3; same weights/constraints',
            strength='symmetric theta0', aggregation='standard', candidates='global rigid6; fixed rows zero',
            prolongation='energy; installed defaults', relaxation='one residual-block-Jacobi pre/post',
            coarse='numpy pinv', seed=0, max_coarse=100),
        versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__, pyamg=pyamg.__version__),
        timings_s=dict(assembly=assembly_s, hierarchy_and_export_matrices=setup_s, cpu_reference_solve=solve_s),
        export_vs_pyamg_relative_error=error,
        establishes='CPU reference and transferable auxiliary cycle for this exact operator',
        does_not_establish=['GPU solver gate', 'physical qualification', 'all material/floor cases', 'optimiser throughput'])
    for key, matrix in matrices.items():
        coo = matrix.tocoo()
        if max(coo.shape) >= 2**31 or coo.nnz >= 2**31:
            raise ValueError('matrix exceeds int32 sparse limits')
        metadata['matrices'][key] = list(coo.shape)
        arrays.update({key+'_row': coo.row.astype(np.int32), key+'_col': coo.col.astype(np.int32),
                       key+'_data': coo.data.astype(np.float64)})
    metadata['array_sha256'] = {key: array_sha(value) for key, value in arrays.items()}
    metadata['uncompressed_array_bytes'] = sum(value.nbytes for value in arrays.values())
    metadata['estimated_csr_bytes_fp64'] = sum(m.nnz*12+(m.shape[0]+1)*4 for m in matrices.values())
    metadata['memory_scope'] = 'CSR storage only; excludes vectors, upload/sort scratch, caches and host arrays'
    repo = Path(__file__).resolve().parents[1]
    metadata['source_sha256'] = {p: file_sha(repo/p) for p in (
        'bench/amg_transfer.py', 'bench/amg_bracket.py', 'bench/amg_relaxation.py',
        'bench/ti_density_weighted.py', 'bench/compare_occupancy.py', 'bench/bracket_gate.py',
        'src/fdmgen/fem/element.py', 'src/fdmgen/materials/card.py')}
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    np.savez_compressed(path, metadata=np.array(json.dumps(metadata, allow_nan=False)), **arrays)
    manifest = dict(metadata, npz_sha256=file_sha(path), npz_bytes=path.stat().st_size,
                    write_and_hash_s=time.perf_counter()-start)
    path.with_suffix('.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    return manifest


def load_pack(path, expected_sha256):
    """Verify bytes, numeric arrays and operator dimensions before device upload."""
    if file_sha(path) != expected_sha256:
        raise ValueError('pack SHA256 mismatch')
    with np.load(path, allow_pickle=False) as pack:
        meta = json.loads(str(pack['metadata']))
        if meta.get('schema') != SCHEMA:
            raise ValueError('unsupported transfer schema')
        arrays = {key: pack[key] for key in pack.files if key != 'metadata'}
    if set(arrays) != set(meta['array_sha256']):
        raise ValueError('array inventory differs')
    for key, value in arrays.items():
        if array_sha(value) != meta['array_sha256'][key] or not np.isfinite(value).all():
            raise ValueError('invalid array or hash: '+key)
    dofs = meta['dofs']; n = meta['levels']
    if not isinstance(n, int) or n < 1 or len(dofs) != n or any(type(d) is not int or d < 1 for d in dofs):
        raise ValueError('invalid hierarchy dimensions')
    shapes = {'physical': [dofs[0], dofs[0]], 'coarse': [dofs[-1], dofs[-1]]}
    for i, d in enumerate(dofs):
        shapes[f'A{i}'] = [d, d]
        if i < n-1:
            shapes.update({f'D{i}': [d, d], f'P{i}': [d, dofs[i+1]], f'R{i}': [dofs[i+1], d]})
    if meta['matrices'] != shapes:
        raise ValueError('matrix dimensions differ from hierarchy')
    matrices = {}
    for key, shape in shapes.items():
        row, col, data = [arrays[key+'_'+suffix] for suffix in ('row', 'col', 'data')]
        if (row.dtype != np.int32 or col.dtype != np.int32 or data.dtype != np.float64
                or row.ndim != 1 or row.shape != col.shape or row.shape != data.shape
                or (row < 0).any() or (row >= shape[0]).any() or (col < 0).any() or (col >= shape[1]).any()):
            raise ValueError('invalid sparse indices/data: '+key)
        matrices[key] = sparse.coo_matrix((data, (row, col)), shape=shape).tocsr()
    if (arrays['load'].shape != (dofs[0],) or arrays['rhs'].shape != (2, dofs[0])
            or arrays['fp64_reference'].shape != arrays['rhs'].shape):
        raise ValueError('invalid vector dimensions')
    vector_keys = ['load', 'rhs', 'fp64_reference']
    if 'direct_solution' in arrays:
        vector_keys.append('direct_solution')
        if arrays['direct_solution'].shape != (dofs[0],):
            raise ValueError('invalid direct-solution dimensions')
    if any(arrays[key].dtype != np.float64 for key in vector_keys) or np.linalg.norm(arrays['load']) == 0:
        raise ValueError('vectors must be float64 with a nonzero load')
    solve = meta.get('reference_solve', {})
    for key in ('compliance_N_mm', 'max_displacement_mm'):
        value = solve.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or value <= 0:
            raise ValueError('invalid CPU reference metric: '+key)
    residual = solve.get('true_relative_residual')
    if not isinstance(residual, (float, int)) or not np.isfinite(residual) or not 0 <= residual <= 1e-8:
        raise ValueError('CPU reference is not converged')
    for i in range(n-1):
        delta = matrices[f'R{i}']-matrices[f'P{i}'].T
        if delta.nnz and np.max(np.abs(delta.data)) > 1e-12:
            raise ValueError('restriction is not the transpose of prolongation')
    return meta, arrays, matrices


def main():
    from fdmgen.geom.voxel import Grid
    from fdmgen.fem.element import ti_C
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--case', choices=('cube', 'bracket'), required=True)
    for key in ('root', 'reference', 'occupancy', 'card'):
        ap.add_argument('--'+key, type=Path)
    ap.add_argument('--basis', choices=('short_term', 'sustained_effective'))
    ap.add_argument('--maxiter', type=int, default=120)
    args = ap.parse_args()
    if args.out.suffix != '.npz':
        ap.error('--out must end in .npz')
    if args.case == 'cube':
        grid = Grid(np.zeros(3), (1., 1., 1.), (16, 12, 8))
        weights = np.ones(grid.shape); weights[4:8] = .03
        fixed = np.repeat(grid.node_coords()[:, 0] == 0, 3)
        load = np.zeros(len(fixed)); load[-2] = -1
        C = ti_C(1000, 870, .38, .36, 278.4)
        provenance = dict(case='heterogeneous clamped cube', grid=dict(shape=list(grid.shape), h_mm=list(grid.h)),
                          load='minus1 N at last node Y DOF', material='nominal TI constants; synthetic control')
    else:
        from bracket_gate import build
        from compare_occupancy import audit_domain, read_occupancy
        from fdmgen.adapters.spool_bracket import HANDOFF
        if not all((args.root, args.reference, args.occupancy, args.card, args.basis)):
            ap.error('bracket needs --root --reference --occupancy --card --basis')
        ref = json.loads(args.reference.read_bytes()); ref_sha = file_sha(args.reference)
        density, occupancy = read_occupancy(args.occupancy, ref, ref_sha)
        C, material = material_spec(args.card, args.basis, layer_axis(ref, occupancy), 1)
        br, full, grid, fixed, load, bc = build(args.root, tuple(ref['grid']['h_mm']))
        if (bc != ref['bc'] or tuple(grid.shape) != tuple(ref['grid']['shape'])
                or not np.allclose(grid.origin, ref['grid']['origin_print_mm'], atol=1e-10, rtol=0)
                or not np.array_equal(br.R_I_to_P, ref['installed_to_print']['R'])
                or not np.array_equal(br.t_I_to_P, ref['installed_to_print']['t_mm'])
                or file_sha(args.root/HANDOFF/'body-only.stl') != ref['mesh_sha256']):
            raise ValueError('rebuilt domain/frame/BC differs from reference')
        for key, value in (('mask_sha256', full), ('fixed_sha256', fixed), ('load_sha256', load)):
            if key in ref and array_sha(value) != ref[key]:
                raise ValueError('rebuilt '+key+' differs')
        weights = np.minimum(density, 1)
        audit = audit_domain(weights > 0, grid, fixed, load)
        if audit['status'] != 'ready':
            raise ValueError('original-load/restraint domain audit blocked export: '+json.dumps(audit))
        provenance = dict(case='slice-derived bracket', reference_sha256=ref_sha,
            occupancy_sha256=file_sha(args.occupancy), occupancy=occupancy, material=material,
            audit=audit, grid=ref['grid'], installed_to_print=ref['installed_to_print'], bc=bc,
            domain_policy='all positive-density cells; capped p1; no floor/filter/load transfer')
    result = export(weights, grid, fixed, load, C, args.out, provenance,
                    maxiter=args.maxiter, direct=args.case == 'cube')
    print(json.dumps({'npz_sha256': result['npz_sha256'], 'dofs': result['dofs'],
                      'reference_solve': result['reference_solve'], 'timings_s': result['timings_s']}))


if __name__ == '__main__':
    main()
