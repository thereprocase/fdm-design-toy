"""Known answers for the uncalibrated density-law sensitivity."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse.linalg import spsolve
from fdmgen.geom.voxel import Grid
from fdmgen.fem.element import box_ke, isotropic_C

spec = importlib.util.spec_from_file_location('density_pilot', Path(__file__).parents[1]/'bench/density_weighted.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
from amg_bracket import assemble_active


def test_density_law_has_no_floor_and_caps_overlap():
    rho = np.array([0, .001, .5, 1, 1.4]).reshape(5, 1, 1)
    for power in (1, 3):
        got = pilot.stiffness_fraction(rho, power)
        np.testing.assert_allclose(got.ravel(), [0, .001**power, .5**power, 1, 1])
    for bad in (np.full((1, 1, 1), np.nan), np.full((1, 1, 1), -1), np.ones(3)):
        with pytest.raises(ValueError):
            pilot.stiffness_fraction(bad, 1)
    with pytest.raises(ValueError):
        pilot.stiffness_fraction(rho, 2)


def test_uniform_density_scales_compliance_without_changing_load():
    grid = Grid(np.zeros(3), (1., 1., 1.), (2, 1, 1))
    fixed = np.repeat(grid.node_coords()[:, 0] == 0, 3)
    load = np.zeros(len(fixed)); load[-2] = -1
    values = []
    for rho, power in ((1., 1), (.5, 1), (.5, 3)):
        field = pilot.stiffness_fraction(np.full(grid.shape, rho), power)
        A, ids = assemble_active(field, box_ke(isotropic_C(1000., .3), *grid.h), fixed)
        assert pilot.audit_domain(field > 0, grid, fixed, load)['status'] == 'ready'
        rhs = load[ids]; u = spsolve(A, rhs); values.append(rhs@u)
        assert np.linalg.norm(A@u-rhs) < 1e-12
    np.testing.assert_allclose(values, np.array([1, 2, 8])*values[0], rtol=1e-12)
