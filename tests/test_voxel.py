"""Analytical occupancy and independent polygon-section parity (simulation geometry only)."""
import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("shapely")
from fdmgen.geom.voxel import voxelise


def test_box_known_answer_padding_and_nodes():
    mesh = trimesh.creation.box(extents=[3, 4, 5])
    occ, g = voxelise(mesh, h=(0.5, 0.5, 0.5), multiple=4)
    assert occ.sum() == 6 * 8 * 10
    assert all(n % 4 == 0 for n in g.shape)
    assert occ.sum() * np.prod(g.h) == mesh.volume
    nodes = g.node_coords().reshape(*(n + 1 for n in g.shape), 3)
    assert np.allclose(nodes[2, 3, 4], g.origin + np.array([2, 3, 4]) * g.h)


@pytest.mark.parametrize("kind", ["rotated", "hole", "disconnected"])
def test_section_parity(kind):
    if kind == "hole":
        mesh = trimesh.creation.annulus(r_min=2, r_max=4, height=3, sections=32)
    elif kind == "disconnected":
        a = trimesh.creation.box(extents=[2, 3, 4])
        b = a.copy(); b.apply_translation([5, 0, 1])
        mesh = trimesh.util.concatenate([a, b])
    else:
        mesh = trimesh.creation.box(extents=[3, 4, 5])
        mesh.apply_transform(trimesh.transformations.rotation_matrix(0.37, [1, 2, 3]))
    mesh.apply_translation([0.123, -2.345, 0.789])
    fast, grid = voxelise(mesh, h=(0.31, 0.37, 0.41), multiple=4)
    old, ref = voxelise(mesh, h=grid.h, multiple=4, backend="section")
    assert grid.shape == ref.shape
    assert np.array_equal(fast, old)


@pytest.mark.parametrize("kwargs", [{"h": (0, 1, 1)}, {"h": (1, 1)}, {"h": (1, np.nan, 1)},
                                    {"multiple": 0}, {"margin_cells": -1}, {"backend": "bad"}])
def test_invalid_grid(kwargs):
    with pytest.raises(ValueError):
        voxelise(trimesh.creation.box(), **kwargs)


def test_open_mesh_rejected():
    mesh = trimesh.creation.box(); mesh.update_faces(np.arange(len(mesh.faces) - 1))
    with pytest.raises(ValueError, match="watertight"):
        voxelise(mesh)
