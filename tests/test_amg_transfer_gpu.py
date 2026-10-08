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
