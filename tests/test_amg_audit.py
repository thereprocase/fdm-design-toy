"""Known matrices distinguish positive, indefinite, asymmetric and leaking inverses."""
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.sparse import csr_array
from scipy.sparse.linalg import aslinearoperator
sys.path.insert(0, str(Path(__file__).parents[1] / 'bench'))
from amg_audit import inverse_probes, hierarchy_structure


def test_known_positive_and_negative_energy():
    good = inverse_probes(aslinearoperator(np.diag([2., 3.])))
    assert good['min_energy'] >= 2
    assert good['max_symmetry_gap'] < 1e-14
    bad = inverse_probes(aslinearoperator(-np.eye(2)))
    np.testing.assert_allclose(bad['energies'], -1, atol=1e-14)


def test_asymmetry_and_free_subspace_leakage():
    M = aslinearoperator(np.array([[2., 3.], [0., 1.]]))
    assert inverse_probes(M)['max_symmetry_gap'] > .1
    free = inverse_probes(M, free=[False, True])
    np.testing.assert_allclose(free['energies'], 1, atol=1e-14)
    assert free['max_symmetry_gap'] < 1e-14
    assert free['max_output_leakage'] == pytest.approx(3/np.sqrt(10))


def test_zero_inverse_is_not_reported_as_small_symmetry_gap():
    result = inverse_probes(aslinearoperator(np.zeros((2, 2))))
    assert result['max_symmetry_gap'] is None
    assert result['undefined_symmetry_gaps'] == 20
    assert result['min_energy'] == 0


def test_probe_seed_does_not_change_global_rng_and_is_repeatable():
    M = aslinearoperator(np.diag([2., 3.]))
    np.random.seed(19); expected = np.random.random()
    np.random.seed(19); first = inverse_probes(M)
    assert np.random.random() == expected
    assert first == inverse_probes(M)


def test_structure_exposes_transfer_and_pair_mismatch():
    def smooth(A, x, b, **kwargs): pass
    P = csr_array([[1.], [1.]])
    level = SimpleNamespace(A=csr_array(np.eye(2)), P=P, R=2*P.T,
        presmoother=partial(smooth, iterations=1, Dinv=np.ones((2, 1, 1))),
        postsmoother=partial(smooth, iterations=2, Dinv=np.ones((2, 1, 1))))
    result = hierarchy_structure(SimpleNamespace(levels=[level]))['levels'][0]
    assert result['restriction_transpose_relative'] == pytest.approx(1)
    assert not result['recorded_pair_equal']
    level.R=P.T; level.postsmoother=level.presmoother
    result = hierarchy_structure(SimpleNamespace(levels=[level]))['levels'][0]
    assert result['restriction_transpose_relative'] == 0
    assert result['recorded_pair_equal']
