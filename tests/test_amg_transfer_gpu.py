"""CPU-side acceptance/version checks; real GPU runs exercise Warp kernels."""
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pytest
from scipy import sparse

pytest.importorskip('warp')
spec = importlib.util.spec_from_file_location('transfer_gpu', Path(__file__).parents[1]/'bench/amg_transfer_gpu.py')
pilot = importlib.util.module_from_spec(spec); sys.modules[spec.name] = pilot; spec.loader.exec_module(pilot)


def test_version_boundary_requires_explicit_experiment_and_exact_version():
    for version, opt_in in [('1.17.0', True), ('1.18.0', False), ('1.19.0', True)]:
        with pytest.raises(ValueError, match='production pin'):
            pilot.version_boundary(version, opt_in)
    boundary = pilot.version_boundary('1.18.0', True)
    assert boundary['production_gate_pin'] == '1.17.0'
    assert boundary['used'] == '1.18.0'
    assert boundary['gate_eligible'] is False


def test_acceptance_uses_true_operator_residual_and_load_scaling():
    A = sparse.diags([2., 3., 4.]); load = np.array([2., 3., 4.]); u = np.ones(3)
    reference = dict(compliance_N_mm=9., max_displacement_mm=np.sqrt(3))
    for scale in [1., .5, 2.]:
        result = pilot.assess_solution(A, load, u*scale, reference, scale, direct=u)
        assert result['accepted'] and result['true_relative_residual_cpu_physical'] == 0
        assert result['compliance_N_mm'] == 9*scale**2
    # A small displacement perturbation can satisfy metric tolerances but fail true residual.
    result = pilot.assess_solution(A, load, u+1e-7, reference, 1.)
    assert result['relative_reference_compliance_error'] < 1e-6
    assert not result['accepted']
    for bad in [np.zeros(3), np.full(3, np.nan)]:
        assert not pilot.assess_solution(A, load, bad, reference, 1.)['accepted']
    with pytest.raises(ValueError, match='scale'):
        pilot.assess_solution(A, load, u, reference, 0)


@pytest.mark.parametrize('sweeps', [1, 2, 5, 6])
def test_cpu_cycle_known_constant_and_antisymmetric_modes(sweeps):
    # A has eigenvalues 1 (constant) and 3 (antisymmetric). Coarse correction
    # solves the constant mode exactly; each Jacobi sweep shrinks the other
    # error by 1/4. Equal pre/post counts give 2*sweeps factors.
    A = sparse.csr_matrix([[2., -1.], [-1., 2.]])
    P = sparse.csr_matrix([[1.], [1.]])
    cpu = {'A0': A, 'D0': sparse.eye(2)*.25, 'P0': P,
           'R0': P.T, 'coarse': sparse.csr_matrix([[.5]])}
    antisymmetric = (1-.25**(2*sweeps))/3
    expected = np.array([1+antisymmetric, 1-antisymmetric])
    np.testing.assert_allclose(pilot.cpu_cycle_reference(cpu, 2, np.array([2., 0.]), sweeps),
                               expected, rtol=1e-14)
    np.testing.assert_array_equal(pilot.cpu_cycle_reference(cpu, 1, np.array([2.]), sweeps), [1.])


@pytest.mark.parametrize('sweeps,rtol', [(0, 1e-6), (33, 1e-6), (True, 1e-6), (1.5, 1e-6),
                                        (1, 0), (1, -1), (1, 1), (1, np.nan), (1, np.inf), (1, True)])
def test_invalid_controls_refused_before_pack_read(sweeps, rtol):
    with pytest.raises(ValueError, match='sweeps|rtol'):
        pilot.run('does-not-exist.npz', 'bad', precision='fp32', graph=True,
                  maxiter=40, experimental=True, sweeps=sweeps, rtol=rtol)


def test_requested_tolerance_does_not_relax_strict_acceptance():
    A = sparse.eye(3); load = np.ones(3)
    ref = dict(compliance_N_mm=3., max_displacement_mm=np.sqrt(3))
    result = pilot.assess_solution(A, load, load+2e-7, ref, 1., requested_rtol=1e-6)
    assert result['requested_tolerance_met']
    assert not result['accepted']
    assert not pilot.assess_solution(A, load, load+2e-6, ref, 1., requested_rtol=1e-6)['requested_tolerance_met']
    assert not pilot.assess_solution(A, load, np.full(3, np.nan), ref, 1., requested_rtol=1e-6)['requested_tolerance_met']
