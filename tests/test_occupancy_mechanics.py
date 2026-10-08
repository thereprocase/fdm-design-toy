"""Known-answer safety screens before interpreting the occupancy FEM comparison."""
import importlib.util
from pathlib import Path
import numpy as np
from fdmgen.geom.voxel import Grid

spec = importlib.util.spec_from_file_location('occupancy_pilot', Path(__file__).parents[1]/'bench/compare_occupancy.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def case():
    g = Grid(np.zeros(3), (1., 1., 1.), (4, 2, 2))
    fixed = np.repeat(g.node_coords()[:, 0] == 0, 3)
    load = np.zeros(len(fixed)); load[-2] = -1
    return g, fixed, load


def test_connected_clamped_block_preserves_load():
    g, fixed, load = case()
    a = pilot.audit_domain(np.ones(g.shape, bool), g, fixed, load)
    assert a['status'] == 'ready' and a['restrained_rigid_modes'] == 6
    assert a['retained_resultant_grid_N'] == [0., -1., 0.]
    assert a['missing_fixed_dofs'] == 0


def test_missing_restraint_blocks_even_with_six_rigid_modes_constrained():
    g, fixed, load = case()
    mask = np.ones(g.shape, bool)
    mask[0, 0, 0] = False  # Only the corner node loses all incident cells.
    a = pilot.audit_domain(mask, g, fixed, load)
    assert a['face_components'] == 1 and a['restrained_rigid_modes'] == 6
    assert a['missing_loaded_dofs'] == 0
    assert a['original_fixed_dofs'] == 27
    assert a['retained_fixed_dofs'] == 24 and a['missing_fixed_dofs'] == 3
    assert a['status'] == 'blocked'
    assert a['reasons'] == ['original fixed DOFs are absent; restraints were not relocated']


def test_missing_load_is_not_silently_deleted():
    g, fixed, load = case(); mask = np.ones(g.shape, bool); mask[-1] = False
    a = pilot.audit_domain(mask, g, fixed, load)
    assert a['status'] == 'blocked' and a['missing_loaded_dofs'] == 1
    assert a['missing_load_l1_N'] == 1


def test_floating_fragment_and_insufficient_restraints_are_blocked():
    g, fixed, load = case(); mask = np.ones(g.shape, bool); mask[2] = False
    assert pilot.audit_domain(mask, g, fixed, load)['face_components'] == 2
    assert pilot.audit_domain(mask, g, fixed, load)['status'] == 'blocked'
    fixed[:] = False; fixed[:3] = True
    assert pilot.audit_domain(np.ones(g.shape, bool), g, fixed, load)['restrained_rigid_modes'] == 3
    assert pilot.audit_domain(np.ones(g.shape, bool), g, fixed, load)['status'] == 'blocked'


def test_pinned_grid_and_density_validation(tmp_path):
    import json
    import pytest
    reference = {'grid': {'shape': [2, 2, 2]}, 'installed_to_print': {'R': np.eye(3).tolist()}}
    provenance = {**reference, 'grid_receipt_sha256': 'a'*64}
    path = tmp_path/'grid.npz'
    def write(density, prov=provenance):
        np.savez(path, density=density, provenance=np.array(json.dumps(prov)))
    write(np.ones((2, 2, 2)))
    assert pilot.read_occupancy(path, reference, 'a'*64)[0].shape == (2, 2, 2)
    with pytest.raises(ValueError, match='receipt'):
        pilot.read_occupancy(path, reference, 'b'*64)
    write(np.full((2, 2, 2), np.nan))
    with pytest.raises(ValueError, match='finite'):
        pilot.read_occupancy(path, reference, 'a'*64)
    write(np.ones((2, 2, 2)), {**provenance, 'grid': {'shape': [3, 2, 2]}})
    with pytest.raises(ValueError, match='grid'):
        pilot.read_occupancy(path, reference, 'a'*64)
