"""Printability columns for one pose (OVH-001, BRG-001 at V, BED-001, BED-002), geometry levels only."""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull

from ..catalog.checks import ovh
from .poses import place


def mesh_volume_centroid(vertices, faces):
    """Volume and centroid of a closed, outward-wound triangle mesh (divergence theorem)."""
    tri = np.asarray(vertices, float)[np.asarray(faces)]
    v6 = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2]))
    vol = v6.sum() / 6.0
    c = (v6[:, None] * tri.sum(axis=1)).sum(axis=0) / (24.0 * vol)
    return float(abs(vol)), c


def spin_matrix(spin_deg: float) -> np.ndarray:
    """Rotation about +Z by spin_deg, counter-clockwise seen from above (p' = Rz p)."""
    r = np.radians(spin_deg)
    return np.array([[np.cos(r), -np.sin(r), 0.0], [np.sin(r), np.cos(r), 0.0], [0.0, 0.0, 1.0]])


def _min_width_and_best_spin(xy, step_deg, usable_mm=None):
    """Minimum caliper width of a 2D point set, and the spin to print at.

    The spin is the smallest angle from 0 whose footprint box fits usable_mm x usable_mm (so parts that
    fit stay axis-aligned); if none fits, the angle with the smallest larger side.
    """
    h = xy[ConvexHull(xy).vertices]
    minw, rows = np.inf, []
    for a in np.arange(0.0, 180.0, step_deg):
        ext = np.ptp(h @ spin_matrix(a)[:2, :2].T, axis=0)
        minw = min(minw, float(ext.min()))
        rows.append((float(a), ext.tolist()))
    fit = [r for r in rows if usable_mm is not None and max(r[1]) <= usable_mm]
    return minw, (fit[0] if fit else min(rows, key=lambda r: max(r[1])))


def pose_columns(vertices, faces, d, bed: dict, stab: dict, *, alpha_min_deg=50.0, centroid=None,
                 contact_tol_mm=0.05, voxel: bool = False, max_bridge_mm=10.0) -> tuple[dict, dict]:
    """Raw printability numbers for build direction d, and the placement (R, t)."""
    V, R, t = place(vertices, d)
    F = np.asarray(faces)
    c = {"height_mm": float(V[:, 2].max())}
    r = ovh.check_mesh(V, F, alpha_min_deg)
    c["ovh_fail_mm2"] = r.metrics["failing_area_mm2"]
    c["ovh_verdict"] = r.verdict.value
    c["bridge_candidate_mm2"] = r.metrics["bridge_candidate_area_mm2"]
    tri = V[F]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(nrm, axis=1) / 2
    on_bed = np.all(tri[:, :, 2] <= contact_tol_mm, axis=1) & (nrm[:, 2] < 0)
    c["contact_mm2"] = float(area[on_bed].sum())
    com = (centroid if centroid is not None else mesh_volume_centroid(vertices, faces)[1]) @ R.T + t
    if c["contact_mm2"] > 1.0:
        cxy = tri[on_bed][:, :, :2].reshape(-1, 2)
        eq = ConvexHull(cxy).equations
        c["com_margin_mm"] = float(-(eq[:, :2] @ com[:2] + eq[:, 2]).max())
        c["base_min_width_mm"], _ = _min_width_and_best_spin(cxy, bed["spin_step_deg"])
    else:
        c["com_margin_mm"], c["base_min_width_mm"] = None, 0.0
    usable = min(bed["bed_x_mm"], bed["bed_y_mm"]) - 2 * bed["margin_mm"]
    _, (spin, ext) = _min_width_and_best_spin(V[:, :2], bed["spin_step_deg"], usable)
    c["footprint_mm2"] = float(ConvexHull(V[:, :2]).volume)
    c["best_spin_deg"], c["best_bbox_mm"] = spin, ext
    # complete pose: lift d to +Z, spin about +Z, lowest point on the bed, footprint box centred on the bed
    Rs = spin_matrix(spin)
    R_full = Rs @ R
    P = np.asarray(vertices, float) @ R_full.T
    lo, hi = P.min(axis=0), P.max(axis=0)
    t_full = np.array([bed["bed_x_mm"] / 2 - (lo[0] + hi[0]) / 2, bed["bed_y_mm"] / 2 - (lo[1] + hi[1]) / 2, -lo[2]])
    c["fits_bed"] = bool(max(ext) <= usable and c["height_mm"] <= bed["max_height_mm"])
    c["contact_ok"] = bool(c["contact_mm2"] >= stab["contact_min_mm2"]
                           and c["contact_mm2"] >= stab["contact_min_fraction"] * c["footprint_mm2"])
    c["stable"] = bool(c["com_margin_mm"] is not None and c["com_margin_mm"] >= stab["com_margin_mm"]
                       and c["height_mm"] <= stab["max_height_to_base"] * max(c["base_min_width_mm"], 1e-9))
    if voxel:
        import trimesh

        from ..catalog.checks import layers
        from ..geom.voxel import voxelise
        occ, g = voxelise(trimesh.Trimesh(V, F, process=False), h=(0.503, 0.503, 0.6), multiple=1)
        c["v_unsupported_mm2"] = ovh.check_voxel(occ, g.h, alpha_min_deg, origin=g.origin).metrics["unsupported_area_mm2"]
        rb = layers.check_bridge(occ, g.h, max_bridge_mm, origin=g.origin)
        w = rb.metrics.get("worst")
        c["brg_worst_span_mm"] = None if w is None else float(w["span_mm"])
        c["brg_verdict"] = rb.verdict.value
    return c, {"R": R_full, "t": t_full}
