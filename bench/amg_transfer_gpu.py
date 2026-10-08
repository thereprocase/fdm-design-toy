"""Experimental Warp 1.18 consumer of a verified CPU auxiliary AMG pack."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
import warp as wp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amg_transfer import file_sha, load_pack


def version_boundary(version, opted_in):
    if not opted_in or version != '1.18.0':
        raise ValueError('requires explicit --experimental-warp-118 and Warp 1.18.0; production pin is unchanged')
    return dict(used=version, production_gate_pin='1.17.0', gate_eligible=False,
        reason='Reusable Warp CG interface tested in the existing 1.18 environment; compatibility/parity with the production 1.17 pin is not established')


@wp.kernel
def cast32(x: wp.array(dtype=wp.float64), y: wp.array(dtype=wp.float32)):
    i = wp.tid(); y[i] = wp.float32(x[i])


@wp.kernel
def combine32(x: wp.array(dtype=wp.float32), y: wp.array(dtype=wp.float64),
              z: wp.array(dtype=wp.float64), alpha: wp.float64, beta: wp.float64):
    i = wp.tid()
    if beta == wp.float64(0):
        z[i] = alpha*wp.float64(x[i])
    else:
        z[i] = alpha*wp.float64(x[i])+beta*y[i]


@wp.kernel
def combine64(x: wp.array(dtype=wp.float64), y: wp.array(dtype=wp.float64),
              z: wp.array(dtype=wp.float64), alpha: wp.float64, beta: wp.float64):
    i = wp.tid()
    if beta == wp.float64(0):
        z[i] = alpha*x[i]
    else:
        z[i] = alpha*x[i]+beta*y[i]


def validate_controls(sweeps, rtol):
    if isinstance(sweeps, bool) or not isinstance(sweeps, int) or not 1 <= sweeps <= 32:
        raise ValueError('sweeps must be an integer from 1 to 32')
    if isinstance(rtol, bool) or not np.isfinite(rtol) or not 0 < rtol < 1:
        raise ValueError('rtol must be finite and between 0 and 1')


def cpu_cycle_reference(cpu, levels, rhs, sweeps, level=0):
    """FP64 residual-Jacobi cycle with the same pre/post work as the GPU."""
    if level == levels-1:
        return cpu['coarse']@rhs
    A, D = cpu[f'A{level}'], cpu[f'D{level}']
    value = D@rhs
    for _ in range(sweeps-1):
        value += D@(rhs-A@value)
    value += cpu[f'P{level}']@cpu_cycle_reference(
        cpu, levels, cpu[f'R{level}']@(rhs-A@value), sweeps, level+1)
    for _ in range(sweeps):
        value += D@(rhs-A@value)
    return value


def assess_solution(A, load, solution, reference, scale, direct=None, requested_rtol=1e-9):
    """Acceptance uses the unmodified CPU physical operator, not CG's recurrence."""
    validate_controls(1, requested_rtol)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('load scale must be positive and finite')
    rhs = load*scale
    residual = float(np.linalg.norm(rhs-A@solution)/np.linalg.norm(rhs))
    compliance = float(rhs@solution)
    displacement = float(np.linalg.norm(solution.reshape(-1, 3), axis=1).max())
    ce = abs(compliance/(reference['compliance_N_mm']*scale**2)-1)
    de = abs(displacement/(reference['max_displacement_mm']*scale)-1)
    ue = float(np.linalg.norm(solution-direct*scale)/np.linalg.norm(direct*scale)) if direct is not None else None
    valid = bool(np.isfinite([residual, ce, de]).all() and residual < 1e-8
                 and ce < 1e-6 and de < 1e-6 and (ue is None or ue < 1e-6))
    # An invalid result still gets a serialisable diagnostic receipt.
    clean = lambda v: float(v) if v is not None and np.isfinite(v) else None
    return dict(accepted=valid, requested_tolerance_met=bool(np.isfinite(residual) and residual <= requested_rtol),
        true_relative_residual_cpu_physical=clean(residual),
        compliance_N_mm=clean(compliance), max_displacement_mm=clean(displacement),
        relative_reference_compliance_error=clean(ce), relative_reference_max_displacement_error=clean(de),
        relative_direct_displacement_error=clean(ue))


def run(pack, sha256, *, precision, graph, maxiter, experimental, sweeps=1, rtol=1e-9):
    validate_controls(sweeps, rtol)
    boundary = version_boundary(wp.__version__, experimental)
    if precision not in ('fp32', 'fp64') or maxiter < 1:
        raise ValueError('invalid cycle precision or iteration limit')
    from warp.sparse import bsr_zeros, bsr_set_from_triplets, bsr_mv
    from warp.optim.linear import LinearOperator, cg
    start = time.perf_counter()
    meta, arrays, cpu = load_pack(pack, sha256)
    validation_s = time.perf_counter()-start
    wp.init(); device = wp.get_device('cuda:0')
    if not device.is_cuda:
        raise ValueError('CUDA device required')
    start = time.perf_counter(); matrices = {}
    dtype = wp.float32 if precision == 'fp32' else wp.float64
    for key, shape in meta['matrices'].items():
        matrix_type = wp.float64 if key == 'physical' else dtype
        matrix = bsr_zeros(*shape, block_type=matrix_type, device=device)
        bsr_set_from_triplets(matrix,
            wp.array(arrays[key+'_row'], dtype=wp.int32, device=device),
            wp.array(arrays[key+'_col'], dtype=wp.int32, device=device),
            wp.array(arrays[key+'_data'], dtype=matrix_type, device=device))
        matrices[key] = matrix
    wp.synchronize(); upload_s = time.perf_counter()-start
    start = time.perf_counter(); size = meta['dofs'][0]; n = meta['levels']
    buffers = [{key: wp.empty(d, dtype=dtype, device=device) for key in ('b', 'x', 'r')} for d in meta['dofs']]

    def cycle(i=0):
        b, x, r = (buffers[i][key] for key in ('b', 'x', 'r'))
        if i == n-1:
            bsr_mv(matrices['coarse'], b, x, beta=0); return x
        bsr_mv(matrices[f'D{i}'], b, x, beta=0)
        for _ in range(sweeps-1):
            wp.copy(r, b); bsr_mv(matrices[f'A{i}'], x, r, alpha=-1., beta=1.)
            bsr_mv(matrices[f'D{i}'], r, x, alpha=1., beta=1.)
        wp.copy(r, b); bsr_mv(matrices[f'A{i}'], x, r, alpha=-1., beta=1.)
        bsr_mv(matrices[f'R{i}'], r, buffers[i+1]['b'], beta=0)
        bsr_mv(matrices[f'P{i}'], cycle(i+1), x, alpha=1., beta=1.)
        for _ in range(sweeps):
            wp.copy(r, b); bsr_mv(matrices[f'A{i}'], x, r, alpha=-1., beta=1.)
            bsr_mv(matrices[f'D{i}'], r, x, alpha=1., beta=1.)
        return x

    def action(x, y, result, alpha, beta):
        if precision == 'fp32':
            wp.launch(cast32, size, inputs=[x, buffers[0]['b']], device=device)
        else:
            wp.copy(buffers[0]['b'], x)
        value = cycle()
        wp.launch(combine32 if precision == 'fp32' else combine64, size,
                  inputs=[value, y, result, wp.float64(alpha), wp.float64(beta)], device=device)

    M = LinearOperator((size, size), wp.float64, device, action)
    x = wp.empty(size, dtype=wp.float64, device=device); y = wp.zeros_like(x); v = wp.empty_like(x)
    references = arrays['fp64_reference'] if sweeps == 1 else [cpu_cycle_reference(cpu, n, rhs, sweeps) for rhs in arrays['rhs']]
    probes = []
    for rhs, reference in zip(arrays['rhs'], references):
        x.assign(rhs); action(x, y, v, 1., 0.); actual = v.numpy()
        probes.append(float(np.linalg.norm(actual-reference)/np.linalg.norm(reference)))
    if not np.isfinite(probes).all() or max(probes) > (5e-4 if precision == 'fp32' else 1e-10):
        raise ValueError('GPU cycle differs excessively from CPU FP64 reference')
    rhs = arrays['rhs'][0]; x.assign(rhs); action(x, y, v, 1., 0.); reference = v.numpy()
    contracts = []
    for alias in ('separate', 'x', 'y'):
        x.assign(rhs); y.assign(np.ones(size)); target = x if alias == 'x' else y if alias == 'y' else v
        action(x, y, target, .7, -.3)
        answer = .7*reference-.3
        error = float(np.linalg.norm(target.numpy()-answer)/np.linalg.norm(answer))
        if not np.isfinite(error) or error > 1e-13:
            raise ValueError('preconditioner alias/alpha/beta contract failed')
        contracts.append(dict(alias=alias, relative_error=error))
    x.assign(rhs); y.assign(np.full(size, np.nan)); action(x, y, v, 1., 0.)
    if not np.array_equal(v.numpy(), reference):
        raise ValueError('preconditioner beta-zero/repeat contract failed')
    load = arrays['load']; b = wp.array(load, dtype=wp.float64, device=device); u = wp.zeros_like(b)
    solver = cg(matrices['physical'], b, u, M=M, tol=rtol, atol=0., maxiter=maxiter,
                check_every=1, use_cuda_graph=graph, run=False)
    wp.synchronize(); setup_s = time.perf_counter()-start
    runs = []; first = None
    for scale in (1., .5, 1.):
        b.assign(load*scale); u.zero_(); wp.synchronize(); start = time.perf_counter()
        iterations, recursive, tolerance = solver()
        wp.synchronize(); elapsed = time.perf_counter()-start
        solution = u.numpy()
        result = assess_solution(cpu['physical'], load, solution, meta['reference_solve'], scale,
                                 arrays.get('direct_solution'), requested_rtol=rtol)
        if first is None:
            first = solution.copy()
        repeat = float(np.linalg.norm(solution/scale-first)/np.linalg.norm(first))
        result['accepted'] &= bool(np.isfinite(repeat) and repeat < 1e-7)
        result.update(scale=scale, iterations=int(iterations), recursive_residual=float(recursive) if np.isfinite(recursive) else None,
            absolute_tolerance=float(tolerance), relative_scaled_solution_error_vs_first=repeat if np.isfinite(repeat) else None,
            solve_s_including_graph_capture_and_scalar_checks=elapsed)
        runs.append(result); print(json.dumps(result, allow_nan=False), flush=True)
    return dict(schema='fdmgen/amg-transfer-gpu@0.1', version_boundary=boundary,
        input_sha256=sha256, input_schema=meta['schema'], input_provenance=meta['provenance'],
        source_sha256={p.name: file_sha(p) for p in (Path(__file__), Path(__file__).with_name('amg_transfer.py'))},
        device=device.name, levels=meta['dofs'], cycle_precision=precision, physical_and_outer_precision='fp64',
        graph=graph, check_every=1, maxiter=maxiter, sweeps=sweeps, requested_relative_tolerance=rtol, reference_solve=meta['reference_solve'],
        cpu_export_timings_s=meta['timings_s'],
        timings_s=dict(read_and_validation=validation_s, upload=upload_s, buffers_probes_solver_setup=setup_s),
        timing_scope='solve includes graph capture and scalar checks; excludes export, transfer, validation, upload and setup; not optimiser throughput',
        probe_relative_errors_vs_cpu_fp64=probes,
        probe_scope='includes cycle quantization and arithmetic, not only rounding',
        cpu_cycle_reference='stored pack reference' if sweeps == 1 else 'FP64 cycle recomputed with matching pre/post sweep count',
        operator_contract_tests=contracts, beta_zero_ignores_nan_y=True, runs=runs,
        accepted=all(r['accepted'] for r in runs),
        requested_tolerance_met=all(r['requested_tolerance_met'] for r in runs),
        acceptance_scope='accepted and exit status retain true residual <1e-8, metric and reuse checks; requested_tolerance_met only observes true residual <= requested rtol and is not the solver gate',
        establishes='transfer accuracy and reusable solver state on the supplied operator',
        does_not_establish=['production Warp 1.17 parity', 'P0-H gate', 'all floor/material cases',
                            'optimiser iteration time', 'physical qualification'])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pack', type=Path, required=True)
    ap.add_argument('--sha256', required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cycle-precision', choices=('fp32', 'fp64'), required=True)
    ap.add_argument('--sweeps', type=int, default=1, help='residual-Jacobi sweeps before and after coarse correction (1..32)')
    ap.add_argument('--rtol', type=float, default=1e-9, help='CG stopping tolerance; strict receipt acceptance remains unchanged')
    ap.add_argument('--no-graph', action='store_true')
    ap.add_argument('--maxiter', type=int, default=120)
    ap.add_argument('--experimental-warp-118', action='store_true')
    args = ap.parse_args()
    if args.out.suffix != '.json' or args.out.resolve() in (args.pack.resolve(), args.pack.with_suffix('.json').resolve()):
        ap.error('--out must be a separate .json receipt, not the pack or its manifest')
    args.out.unlink(missing_ok=True)
    result = run(args.pack, args.sha256, precision=args.cycle_precision, graph=not args.no_graph,
                 maxiter=args.maxiter, experimental=args.experimental_warp_118, sweeps=args.sweeps, rtol=args.rtol)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    raise SystemExit(0 if result['accepted'] else 2)


if __name__ == '__main__':
    main()
