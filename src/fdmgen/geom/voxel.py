"""Voxelise a watertight mesh on a print-frame grid, layer by layer (as a slicer would).

Cell (i, j, k) has centre origin + ((i + 1/2) dx, (j + 1/2) dy, (k + 1/2) dz). A cell is solid when its centre
lies inside the cross-section of the mesh at the cell's mid-height. Grid dimensions are padded up to a
multiple of `multiple` (for multigrid coarsening); padded cells are outside.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Grid:
    origin: np.ndarray       # mm, corner of cell (0, 0, 0)
    h: tuple                 # (dx, dy, dz) mm
    shape: tuple             # (nx, ny, nz) cells

    def centres(self, axis: int) -> np.ndarray:
        return self.origin[axis] + (np.arange(self.shape[axis]) + 0.5) * self.h[axis]

    def node_coords(self) -> np.ndarray:
        """(n_nodes, 3) node positions, node index (ix * (ny+1) + iy) * (nz+1) + iz."""
        ax = [self.origin[a] + np.arange(self.shape[a] + 1) * self.h[a] for a in range(3)]
        X, Y, Z = np.meshgrid(*ax, indexing="ij")
        return np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)


def _pad(n: int, multiple: int) -> int:
    return int(np.ceil(n / multiple) * multiple)


def voxelise(mesh, h=(0.503, 0.503, 0.6), multiple=8, margin_cells=1) -> tuple[np.ndarray, Grid]:
    """Boolean occupancy (nx, ny, nz) of `mesh` (trimesh, print frame) and its grid."""
    import shapely

    lo, hi = mesh.bounds
    h = tuple(float(v) for v in h)
    origin = np.array([lo[0] - margin_cells * h[0], lo[1] - margin_cells * h[1], lo[2]])
    shape = tuple(_pad(int(np.ceil((hi[a] - origin[a]) / h[a])) + (margin_cells if a < 2 else 0), multiple)
                  for a in range(3))
    g = Grid(origin, h, shape)
    xs, ys, zs = g.centres(0), g.centres(1), g.centres(2)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    occ = np.zeros(shape, bool)
    for k, z in enumerate(zs):
        if z <= lo[2] or z >= hi[2]:
            continue
        sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if sec is None:
            continue
        planar, T = sec.to_planar()
        polys = planar.polygons_full
        if not polys:
            continue
        # back to print-frame XY: apply T to the polygon points
        geoms = []
        for poly in polys:
            def tr(coords):
                c = np.asarray(coords)
                p = np.c_[c, np.zeros(len(c)), np.ones(len(c))] @ T.T
                return p[:, :2]
            geoms.append(shapely.Polygon(tr(poly.exterior.coords), [tr(r.coords) for r in poly.interiors]))
        area = shapely.union_all(geoms)
        occ[:, :, k] = shapely.contains_xy(area, X, Y)
    return occ, g
