"""Printed-material density grid from a slice: credited roads deposited into the cells of a given grid.

Each credited road (see reader.credit: thick bridges, support, skirt/brim and priming are excluded and
counted) is sampled along its length, across its declared width (in the print XY plane, perpendicular
to the road) and through its declared height (below the layer top); every sample carries an equal share
of the road's extruded volume. Sample points go from the slice's plate frame to the grid frame through
one affine map g = M p + c, e.g. the pose inverse (plate -> design) followed by the solver grid's
design -> print map. Volume is conserved and accounted: credited input, deposited inside the grid,
clipped outside it, and the excess above density 1 where beads overlap (saturation). The raster is an
approximation of the slicer's material, not a measured print.
"""
from __future__ import annotations

import numpy as np

from .reader import Toolpath, credit


def deposit(tp: Toolpath, offset, M, c, origin, h, shape, *, step_frac: float = 1 / 3, mask=None, caps: bool = False):
    """Volume grid (mm3 per cell) and the volume that fell outside it, for the roads in mask (default credited).

    Each road is a rectangle (width x layer height) along its centreline. Without caps, the half-bead square
    at a convex corner (where the slicer turns a wall at its centreline) and the bead's end caps stay empty.
    caps=True extends roads where the path is not a straight continuation (see _cap_extensions), lays the
    extension at the road's own volume per unit length, then rescales the whole grid once so the total is
    still the roads' volume. Splitting a straight road into collinear moves changes nothing.
    """
    sel = credit(tp)["credited_mask"] if mask is None else np.asarray(mask, bool)
    a = tp.start[sel] + np.asarray(offset, float)
    b = tp.end[sel] + np.asarray(offset, float)
    w, hh, vol = tp.width[sel], tp.height[sel], tp.volume[sel]
    h = np.broadcast_to(np.asarray(h, float), (3,))
    step = float(h.min()) * step_frac
    L = np.linalg.norm(b[:, :2] - a[:, :2], axis=1)
    total = float(vol.sum())
    if caps:
        lead, trail = _cap_extensions(a, b, w, L)
        u = np.zeros_like(a)
        u[:, :2] = (b[:, :2] - a[:, :2]) / np.maximum(L, 1e-12)[:, None]
        a, b = a - u * lead[:, None], b + u * trail[:, None]
        L_ext = L + lead + trail
        vol = np.where(L > 1e-12, vol * L_ext / np.maximum(L, 1e-12), vol)
        L = L_ext
    n_l = np.maximum(1, np.ceil(L / step)).astype(int)
    n_w = np.maximum(1, np.ceil(w / step)).astype(int)
    n_h = np.maximum(1, np.ceil(hh / step)).astype(int)
    dirs = np.zeros_like(a)
    dirs[:, :2] = (b[:, :2] - a[:, :2]) / np.maximum(L, 1e-12)[:, None]
    perp = np.stack([-dirs[:, 1], dirs[:, 0], np.zeros(len(a))], axis=1)
    grid = np.zeros(shape, float)
    M, c, origin = np.asarray(M, float), np.asarray(c, float), np.asarray(origin, float)
    outside = 0.0
    for nl, nw, nh in {(x, y, z) for x, y, z in zip(n_l, n_w, n_h)}:
        g = (n_l == nl) & (n_w == nw) & (n_h == nh)
        fl = (np.arange(nl) + 0.5) / nl
        fw = (np.arange(nw) + 0.5) / nw - 0.5
        fh = (np.arange(nh) + 0.5) / nh
        ff = np.stack(np.meshgrid(fl, fw, fh, indexing="ij"), axis=-1).reshape(-1, 3)
        p = (a[g, None, :] + (b[g] - a[g])[:, None, :] * ff[None, :, 0:1]
             + perp[g, None, :] * (w[g, None, None] * ff[None, :, 1:2])
             - np.array([0, 0, 1.0]) * (hh[g, None, None] * ff[None, :, 2:3]))
        share = np.repeat(vol[g] / len(ff), len(ff))
        q = p.reshape(-1, 3) @ M.T + c
        idx = np.floor((q - origin) / h).astype(int)
        ok = np.all((idx >= 0) & (idx < np.asarray(shape)), axis=1)
        np.add.at(grid, tuple(idx[ok].T), share[ok])
        outside += float(share[~ok].sum())
    if caps and vol.sum() > 0:
        k = total / float(vol.sum())                # one global factor: cap material comes from the same extrusion
        grid *= k
        outside *= k
    return grid, outside


def _cap_extensions(a, b, w, L, *, tol_mm=1e-6):
    """Lead and trail extensions (mm) per road: half the width where a path starts or ends, the miter length
    (w/2) tan(theta/2), at most w/2, at a turn of theta between consecutive roads, and 0 when the next road
    continues straight on. Consecutive means the next road starts where this one ends."""
    lead, trail = w / 2, w / 2                     # new arrays (w / 2 allocates)
    if len(a) > 1:
        joined = np.linalg.norm(a[1:] - b[:-1], axis=1) < tol_mm
        d = np.zeros((len(a), 2))
        ok = L > 1e-12
        d[ok] = (b - a)[ok, :2] / L[ok, None]
        theta = np.arccos(np.clip(np.einsum("ij,ij->i", d[:-1], d[1:]), -1.0, 1.0))
        miter = (w[:-1] / 2) * np.minimum(1.0, np.tan(np.minimum(theta, np.pi / 2) / 2))
        trail[:-1] = np.where(joined, miter, trail[:-1])
        lead[1:] = np.where(joined, 0.0, lead[1:])
    lead[L <= 1e-12] = 0.0
    trail[L <= 1e-12] = 0.0
    return lead, trail




def plate_to_grid(R_pose, t_pose, R_design_to_grid, t_design_to_grid):
    """Compose plate -> design (pose inverse: design = R^T (p - t)) and design -> grid (g = Rg d + tg)."""
    Rp, tp_, Rg, tg = (np.asarray(x, float) for x in (R_pose, t_pose, R_design_to_grid, t_design_to_grid))
    M = Rg @ Rp.T
    return M, tg - M @ tp_


def occupancy(tp: Toolpath, offset, M, c, origin, h, shape, *, threshold=0.5, meta=None) -> dict:
    """NPZ-ready dict: dense density (C order, x y z), threshold mask, accounting and provenance."""
    cr = credit(tp)
    vgrid, outside = deposit(tp, offset, M, c, origin, h, shape)
    cell_v = float(np.prod(np.broadcast_to(np.asarray(h, float), (3,))))
    density = vgrid / cell_v
    excess = float(np.clip(density - 1.0, 0, None).sum() * cell_v)
    solid = density >= threshold
    idx = np.argwhere(solid)
    acct = {"credited_input_mm3": cr["structurally_credited_extrusion_volume_mm3"],
            "deposited_inside_grid_mm3": float(vgrid.sum()), "clipped_outside_grid_mm3": outside,
            "saturation_excess_mm3": excess,
            "excluded": {"thick_bridge_mm3": cr["sacrificial_thick_bridge_extrusion_volume_mm3"],
                         "thick_bridge_segments": cr["thick_bridge_segments"],
                         "support_and_aux_mm3": cr["support_and_aux_volume_mm3"],
                         "nonobject_mm3": cr["nonobject_spent_volume_mm3"]},
            "threshold": threshold, "solid_cells": int(solid.sum())}
    return {"density": density.astype(np.float32), "density_capped": np.minimum(density, 1.0).astype(np.float32),
            "solid_mask": solid, "cell_indices": idx.astype(np.int32),
            "centres_grid_mm": (np.asarray(origin, float) + (idx + 0.5) * np.asarray(h, float)),
            "cell_volume_mm3": np.full(len(idx), cell_v), "accounting": acct, "M_plate_to_grid": np.asarray(M, float),
            "c_plate_to_grid": np.asarray(c, float), **(meta or {})}
