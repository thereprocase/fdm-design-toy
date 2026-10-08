"""Direct-reference tests for TI physics with an isotropic auxiliary inverse."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse.linalg import spsolve
from fdmgen.geom.voxel import Grid
from fdmgen.fem.element import box_ke, isotropic_C, ti_C

spec = importlib.util.spec_from_file_location('ti_density_pilot', Path(__file__).parents[1]/'bench/ti_density_weighted.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_axis_validation_refuses_unimplemented_tensor_rotation():
    ref = {'installed_to_print': {'R': np.diag([-1, -1, 1]).tolist()}}
    prov = {'pose_R_design_to_print': np.eye(3).tolist()}
    assert pilot.layer_axis(ref, prov) == [0, 0, 1]
    prov['pose_R_design_to_print'] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    with pytest.raises(ValueError, match='not grid Z'):
        pilot.layer_axis(ref, prov)
    for bad in (np.diag([1, 1, -1]), np.eye(3)*2, np.full((3, 3), np.nan)):
        with pytest.raises(ValueError, match='proper orthogonal'):
            pilot.layer_axis(ref, {'pose_R_design_to_print': bad.tolist()})


def test_card_basis_is_explicit_and_tensor_receipted():
    path = Path(__file__).parents[1]/'catalog/materials/polymaker-polylite-asa-t0.yaml'
    C, metadata = pilot.material_spec(path, 'sustained_effective', [0, 0, 1], 1)
    assert metadata['constants']['E_p'] == 1000
    assert metadata['constants']['E_z'] == 870
    assert metadata['C_sha256'] == pilot.array_sha(C)
    np.testing.assert_allclose(np.linalg.inv(C)[2, 0], -.36/1000)
    with pytest.raises(ValueError, match='basis'):
        pilot.material_spec(path, 'unspecified', [0, 0, 1], 1)


@pytest.mark.parametrize('C', [isotropic_C(1000, .3), ti_C(1000, 870, .38, .36, 278.4)])
def test_surrogate_preconditioner_solves_physical_operator(C):
    pytest.importorskip('pyamg')
    from amg_bracket import assemble_active
    grid = Grid(np.zeros(3), (1., 1., 1.), (4, 2, 2))
    fixed = np.repeat(grid.node_coords()[:, 0] == 0, 3)
    load = np.zeros(len(fixed)); load[-2] = -1
    rho = np.linspace(.2, 1, np.prod(grid.shape)).reshape(grid.shape)
    A, ids = assemble_active(rho, box_ke(C, *grid.h), fixed)
    u = spsolve(A, load[ids])
    result = pilot.solve_ti(rho, grid, fixed, load, C, 120)
    assert result['status'] == 'solved'
    assert result['true_relative_residual'] < 1e-8
    np.testing.assert_allclose(result['compliance_N_mm'], load[ids]@u, rtol=1e-8)
    np.testing.assert_allclose(result['max_displacement_mm'], np.linalg.norm(u.reshape(-1, 3), axis=1).max(), rtol=1e-8)
    assert result['physical_CSR_sha256']['data'] == pilot.array_sha(A.data)
    if not np.array_equal(C, isotropic_C(1000, .3)):
        assert result['physical_CSR_sha256'] != result['auxiliary_CSR_sha256']
