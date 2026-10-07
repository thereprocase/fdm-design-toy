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


def voxelise(mesh, h=(0.503, 0.503, 0.6), multiple=8, margin_cells=1, *, backend="scanline") -> tuple[np.ndarray, Grid]:
    """Boolean occupancy (nx, ny, nz) of `mesh` (trimesh, print frame) and its grid."""
    import trimesh

    if backend not in {"scanline", "section"}:
        raise ValueError("backend must be scanline or section")
    h = np.asarray(h, dtype=float)
    if h.shape != (3,) or not np.isfinite(h).all() or (h <= 0).any():
        raise ValueError("h must contain three finite positive spacings")
    if not isinstance(multiple, (int, np.integer)) or multiple < 1:
        raise ValueError("multiple must be a positive integer")
    if not isinstance(margin_cells, (int, np.integer)) or margin_cells < 0:
        raise ValueError("margin_cells must be a nonnegative integer")
    if not mesh.is_watertight:
        raise ValueError("voxelisation requires a watertight mesh")
    lo, hi = mesh.bounds
    h = tuple(float(v) for v in h)
    origin = np.array([lo[0] - margin_cells * h[0], lo[1] - margin_cells * h[1], lo[2]])
    shape = tuple(_pad(int(np.ceil((hi[a] - origin[a]) / h[a])) + (margin_cells if a < 2 else 0), multiple)
                  for a in range(3))
    g = Grid(origin, h, shape)
    xs, ys, zs = g.centres(0), g.centres(1), g.centres(2)
    if backend == "section":
        import shapely
        X, Y = np.meshgrid(xs, ys, indexing="ij")
    vertex_z = np.asarray(mesh.vertices[:, 2])
    occ = np.zeros(shape, bool)
    for k, z in enumerate(zs):
        if z <= lo[2] or z >= hi[2]:
            continue
        if backend == "scanline":
            segments = trimesh.intersections.mesh_plane(
                mesh, plane_normal=[0, 0, 1], plane_origin=[0, 0, z],
                cached_dots=vertex_z - z)
            occ[:, :, k] = _scanline(segments[:, :, :2], xs, ys)
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


def _scanline(segments, xs, ys):
    """Even/odd fill; half-open Y endpoints count shared vertices once.

    No polygon reconstruction or point objects. Holes and disconnected shells
    follow the same parity rule. Chunk rows to bound crossing scratch memory.
    Meshes must describe non-overlapping watertight solids.
    """
    out = np.zeros((len(xs), len(ys)), dtype=bool)
    if not len(segments):
        return out
    a, b = segments[:, 0], segments[:, 1]
    dy = b[:, 1] - a[:, 1]
    nonhorizontal = dy != 0
    a, b, dy = a[nonhorizontal], b[nonhorizontal], dy[nonhorizontal]
    for start in range(0, len(ys), 64):
        y = ys[start:start + 64, None]
        hits = (y >= np.minimum(a[:, 1], b[:, 1])) & (y < np.maximum(a[:, 1], b[:, 1]))
        crossing = a[:, 0] + (y - a[:, 1]) * ((b[:, 0] - a[:, 0]) / dy)
        crossing[~hits] = np.inf
        crossing.sort(axis=1)
        for j, row in enumerate(crossing):
            left = np.searchsorted(row, xs, side="left")
            right = np.searchsorted(row, xs, side="right")
            out[:, start + j] = (left % 2 == 1) & (left == right)
    return out
