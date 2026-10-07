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


def _min_width_and_best_spin(xy, step_deg):
    h = xy[ConvexHull(xy).vertices]
    best, minw = None, np.inf
    for a in np.arange(0.0, 180.0, step_deg):
        r = np.radians(a)
        ext = np.ptp(h @ np.array([[np.cos(r), -np.sin(r)], [np.sin(r), np.cos(r)]]), axis=0)
        minw = min(minw, float(ext.min()))
        if best is None or ext.max() < max(best[1]):
            best = (float(a), ext.tolist())
    return minw, best


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
    _, (spin, ext) = _min_width_and_best_spin(V[:, :2], bed["spin_step_deg"])
    c["footprint_mm2"] = float(ConvexHull(V[:, :2]).volume)
    c["best_spin_deg"], c["best_bbox_mm"] = spin, ext
    usable = min(bed["bed_x_mm"], bed["bed_y_mm"]) - 2 * bed["margin_mm"]
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
    return c, {"R": R, "t": t}
