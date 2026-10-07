"""Force/moment transfer known answers, including infeasible nonnegative loading."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('seat_transfer', Path(__file__).parents[1]/'bench/seat_load_transfer.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def test_transfer_preserves_uniform_load_when_nodes_unchanged():
    p = np.array([[0., 0., 0.], [2., 0., 0.], [0., 0., 2.], [2., 0., 2.]])
    w, receipt = module.transfer_weights(p, p, [0., -10., 0.])
    assert np.allclose(w, .25)
    assert receipt['force_error_N'] < 1e-10 and receipt['moment_error_N_mm'] < 1e-10


def test_missing_centre_node_preserves_force_and_moment_on_corners():
    target = np.array([[0., 0., 0.], [2., 0., 0.], [0., 0., 2.], [2., 0., 2.]])
    original = np.vstack([target, [1., 0., 1.]])
    w, receipt = module.transfer_weights(original, target, [0., -20., 0.])
    assert np.allclose(w, .25)
    assert np.allclose(receipt['transferred_force_N'], [0., -20., 0.])
    assert np.allclose(receipt['transferred_moment_about_grid_frame_zero_N_mm'], [20., 0., -20.])


def test_offcentre_resultant_requires_nonuniform_positive_weights():
    original = np.array([[.5, 0., 0.]])
    target = np.array([[0., 0., 0.], [2., 0., 0.]])
    w, receipt = module.transfer_weights(original, target, [0., -4., 0.])
    assert np.allclose(w, [.75, .25], atol=1e-10)
    assert receipt['moment_error_N_mm'] < 1e-10


def test_resultant_outside_convex_hull_cannot_use_negative_pressure():
    with pytest.raises(ValueError):
        module.transfer_weights([[3., 0., 0.]], [[0., 0., 0.], [2., 0., 0.]], [0., -1., 0.])


def test_explicit_fragment_policy_reports_removed_cells():
    mask = np.zeros((5, 2, 2), bool); mask[:2] = True; mask[4, 0, 0] = True
    kept, record = module.largest_face_component(mask)
    assert kept.sum() == 8 and not kept[4, 0, 0]
    assert record == {'original_cells':9, 'retained_cells':8, 'removed_cells':1, 'removed_component_cell_counts':[1]}
    with pytest.raises(ValueError, match='empty'):
        module.largest_face_component(np.zeros_like(mask))
