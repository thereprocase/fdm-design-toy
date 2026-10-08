"""CPU known answers and malformed-pack refusals; GPU validation runs separately."""
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('transfer', Path(__file__).parents[1]/'bench/amg_transfer.py')
transfer = importlib.util.module_from_spec(spec); spec.loader.exec_module(transfer)


@pytest.fixture
def exported(tmp_path):
    pytest.importorskip('pyamg')
    from fdmgen.geom.voxel import Grid
    from fdmgen.fem.element import ti_C
    grid = Grid(np.zeros(3), (1., 1., 1.), (6, 4, 3))
    fixed = np.repeat(grid.node_coords()[:, 0] == 0, 3)
    load = np.zeros(len(fixed)); load[-2] = -1
    weights = np.ones(grid.shape); weights[2:4] = .03
    path = tmp_path/'cycle.npz'
    manifest = transfer.export(weights, grid, fixed, load, ti_C(1000, 870, .38, .36, 278.4),
                               path, {'case': 'known-answer test'}, direct=True)
    return path, manifest


def test_transfer_cycle_matches_pyamg_and_direct_solution(exported):
    path, manifest = exported
    meta, arrays, matrices = transfer.load_pack(path, manifest['npz_sha256'])
    assert meta['levels'] >= 2
    assert meta['reference_solve']['true_relative_residual'] < 1e-8
    assert meta['reference_solve']['relative_direct_solution_error'] < 1e-7
    np.testing.assert_allclose(matrices['physical']@arrays['direct_solution'], arrays['load'], atol=1e-9)
    for rhs, reference in zip(arrays['rhs'], arrays['fp64_reference']):
        np.testing.assert_allclose(transfer.cycle(matrices, rhs, meta['levels']), reference, rtol=1e-12, atol=1e-12)
    assert manifest['npz_sha256'] == transfer.file_sha(path)
    assert manifest['write_and_hash_s'] >= 0
    assert meta['recipe']['relaxation'] == 'one residual-block-Jacobi pre/post'


def rewrite(path, meta, arrays):
    np.savez_compressed(path, metadata=np.array(json.dumps(meta)), **arrays)
    return transfer.file_sha(path)


@pytest.mark.parametrize('mutation', ['hash', 'index', 'shape', 'restriction', 'nan', 'zero_load', 'reference', 'direct_shape'])
def test_transfer_refuses_corrupt_or_inconsistent_pack(exported, mutation):
    path, manifest = exported
    meta, arrays, _ = transfer.load_pack(path, manifest['npz_sha256'])
    if mutation == 'hash':
        with pytest.raises(ValueError, match='SHA256'):
            transfer.load_pack(path, '0'*64)
        arrays['load'][0] += 1
    elif mutation == 'index':
        arrays['A0_row'][0] = meta['dofs'][0]
        meta['array_sha256']['A0_row'] = transfer.array_sha(arrays['A0_row'])
    elif mutation == 'shape':
        meta['matrices']['P0'][0] += 1
    elif mutation == 'restriction':
        arrays['R0_data'] *= 2
        meta['array_sha256']['R0_data'] = transfer.array_sha(arrays['R0_data'])
    elif mutation == 'nan':
        arrays['load'][0] = np.nan
        meta['array_sha256']['load'] = transfer.array_sha(arrays['load'])
    elif mutation == 'zero_load':
        arrays['load'][:] = 0
        meta['array_sha256']['load'] = transfer.array_sha(arrays['load'])
    elif mutation == 'reference':
        meta['reference_solve']['compliance_N_mm'] = 0
    elif mutation == 'direct_shape':
        arrays['direct_solution'] = arrays['direct_solution'][:-1]
        meta['array_sha256']['direct_solution'] = transfer.array_sha(arrays['direct_solution'])
    sha = rewrite(path, meta, arrays)
    with pytest.raises(ValueError):
        transfer.load_pack(path, sha)
