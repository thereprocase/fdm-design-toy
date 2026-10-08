"""Known graph: identity constraints must not hide a free/free node connection."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import csr_matrix

spec = importlib.util.spec_from_file_location('amg_strength', Path(__file__).parents[1] / 'bench/amg_strength.py')
strength = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strength)


def fixture():
    A = np.diag([.001, .001, 1., .001, .001, 1., 1., 1., 1.])
    A[0, 3] = A[3, 0] = A[1, 4] = A[4, 1] = -.0004
    return csr_matrix(A), np.array([True, True, False, True, True, False, False, False, False])


def test_constraint_graph_reveals_known_connection_without_mutating_operator():
    pytest.importorskip('pyamg')
    A, free = fixture(); before = A.toarray()
    options, meta = strength.strength_options(A, .08, free)
    assert options == ('symmetric', {'theta': .08})
    assert meta['unassigned_free_dofs'] == 4
    for policy in ['zero', 'mean']:
        options, meta = strength.strength_options(A, .08, free, policy)
        S = options[0][1]['C']
        assert S[0, 1] > 0 and S[1, 0] > 0
        assert S[0, 2] == 0 and S[1, 2] == 0
        assert meta['unassigned_free_dofs'] == 0
        np.testing.assert_array_equal(A.toarray(), before)


@pytest.mark.parametrize('policy', ['zero', 'mean'])
def test_missing_mask_and_nonidentity_fixed_rows_are_refused(policy):
    pytest.importorskip('pyamg')
    A, free = fixture()
    with pytest.raises(ValueError, match='requires a free mask'):
        strength.strength_options(A, .08, policy=policy)
    A[2, 2] = 2
    with pytest.raises(ValueError, match='identity rows'):
        strength.strength_options(A, .08, free, policy)


def test_no_constraints_has_identical_graph_and_rng_unchanged():
    pytest.importorskip('pyamg')
    A, _ = fixture(); free = np.ones(A.shape[0], bool)
    state = np.random.get_state()
    hashes = [strength.strength_options(A, .08, free, policy)[1]['first_graph_sha256']
              for policy in strength.POLICIES]
    assert hashes[0] == hashes[1] == hashes[2]
    after = np.random.get_state()
    assert state[0] == after[0] and state[2:] == after[2:]
    np.testing.assert_array_equal(state[1], after[1])
