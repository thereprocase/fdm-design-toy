"""Keep-out regions (problem.yaml keep_outs): exact triangle-box and box-box overlap.

A keep-out box may be unbounded on any side (null in min_mm / max_mm). Overlap is decided by the
separating-axis test for each triangle (13 axes: box faces, triangle normal, edge cross products),
so thin intrusions between sample points cannot be missed. The box is shrunk by tol_mm first, so
material that only touches a keep-out boundary (a locating face sitting on it) is contact, not
intrusion.
"""
from __future__ import annotations

import numpy as np

from ..result import CheckResult, Verdict


def _bounds(keep_out: dict, extent_lo, extent_hi, tol_mm: float):
    lo = np.array([extent_lo[k] - 1.0 if v is None else v for k, v in enumerate(keep_out["min_mm"])], float)
    hi = np.array([extent_hi[k] + 1.0 if v is None else v for k, v in enumerate(keep_out["max_mm"])], float)
    return lo + tol_mm, hi - tol_mm


def triangles_overlap_box(tri: np.ndarray, lo, hi) -> np.ndarray:
    """(n,) bool: which triangles (n, 3, 3) overlap the axis-aligned box [lo, hi] (separating-axis test)."""
    c = (np.asarray(lo) + np.asarray(hi)) / 2
    h = (np.asarray(hi) - np.asarray(lo)) / 2
    v = tri - c
    if np.any(h < 0):
        return np.zeros(len(tri), bool)
    hit = np.ones(len(tri), bool)
    for k in range(3):                                         # box face normals
        hit &= (v[:, :, k].min(axis=1) <= h[k]) & (v[:, :, k].max(axis=1) >= -h[k])
    e = np.stack([v[:, 1] - v[:, 0], v[:, 2] - v[:, 1], v[:, 0] - v[:, 2]], axis=1)
    n = np.cross(e[:, 0], e[:, 1])                              # triangle normal
    r = np.abs(n) @ h
    d = np.einsum("ij,ij->i", n, v[:, 0])
    hit &= np.abs(d) <= r
    axes = np.eye(3)
    for i in range(3):                                         # edge x box axis
        for j in range(3):
            a = np.cross(e[:, i], axes[j])
            p = np.einsum("nkj,nj->nk", v, a)
            rad = np.abs(a) @ h
            hit &= (p.min(axis=1) <= rad) & (p.max(axis=1) >= -rad)
    return hit


def flange_discs(ko: dict, interfaces, step_mm: float = 1.0):
    """(centres (n, 2), radii (n,)) of the flange discs sampled over spool radius (step) and both rail-radius ends."""
    axes = {i["id"]: np.asarray(i["center_xy_mm"], float) for i in interfaces or [] if "center_xy_mm" in i}
    p0, p1 = (axes[k] for k in ko["rod_interfaces"])
    span = float(np.linalg.norm(p1 - p0))
    t = (p1 - p0) / span
    n = np.array([-t[1], t[0]])
    n = n if n[1] > 0 else -n                                  # the spool sits above the rods (+Y)
    mid = (p0 + p1) / 2
    cs, rs = [], []
    for R in np.arange(ko["spool_diameter_mm"][0] / 2, ko["spool_diameter_mm"][1] / 2 + 1e-9, step_mm):
        for r in ko["rail_radius_mm"]:
            cs.append(mid + n * np.sqrt((R + r) ** 2 - span ** 2 / 4))
            rs.append(R + ko["clearance_mm"])
    return np.array(cs), np.array(rs)


def _point_triangle_distance_2d(c, tri2):
    """Distance from point c to each 2D triangle (n, 3, 2); 0 when c is inside."""
    a, b, d = tri2[:, 0], tri2[:, 1], tri2[:, 2]
    def seg(p, q):
        pq = q - p
        t = np.clip(np.einsum("ij,ij->i", c - p, pq) / np.maximum(np.einsum("ij,ij->i", pq, pq), 1e-30), 0, 1)
        return np.linalg.norm(p + t[:, None] * pq - c, axis=1)
    dist = np.minimum(np.minimum(seg(a, b), seg(b, d)), seg(d, a))
    def cross(p, q):
        return (q[:, 0] - p[:, 0]) * (c[1] - p[:, 1]) - (q[:, 1] - p[:, 1]) * (c[0] - p[:, 0])
    s1, s2, s3 = cross(a, b), cross(b, d), cross(d, a)
    inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
    return np.where(inside, 0.0, dist)


def check_body(vertices, faces, keep_outs, *, tol_mm: float = 1e-3, frame: str = "installed",
               interfaces=None) -> list[CheckResult]:
    """One result per keep-out: does the body mesh (in `frame`) enter it?"""
    v = np.asarray(vertices, float)
    tri = v[np.asarray(faces)]
    out = []
    for ko in keep_outs or []:
        m = {"keep_out_id": ko["id"]}
        if ko.get("type") == "flange_sweep" and ko.get("frame") == frame and interfaces:
            cs, rs = flange_discs(ko, interfaces)
            tri2 = tri[:, :, :2]
            worst, hit_any = None, np.zeros(len(tri), bool)
            for c, r in zip(cs, rs):
                dd = _point_triangle_distance_2d(c, tri2)
                hit = dd < r - tol_mm
                hit_any |= hit
                if hit.any() and (worst is None or (r - dd[hit].min()) > worst[0]):
                    worst = (float(r - dd[hit].min()), float(r), c.round(3).tolist())
            m.update(triangles_inside=int(hit_any.sum()), sampled_spools=len(cs) // 2, sample_step_mm=1.0)
            if hit_any.any():
                p = tri[hit_any].reshape(-1, 3)
                m.update(bbox_mm=[p.min(axis=0).round(3).tolist(), p.max(axis=0).round(3).tolist()],
                         max_intrusion_mm=round(worst[0], 3))
                out.append(CheckResult("KEEP-OUT", "M", Verdict.FAIL,
                                       f"KEEP-OUT FAIL: {hit_any.sum()} body triangles come within the {ko['clearance_mm']} mm "
                                       f"flange clearance of {ko['id']} (deepest {worst[0]:.2f} mm, sampled spool radii at 1 mm "
                                       f"steps). {ko['rule']}", True, m, ["cut material back from the flange sweep"]))
            else:
                out.append(CheckResult("KEEP-OUT", "M", Verdict.PASS,
                                       f"KEEP-OUT PASS (sampled): no body triangle comes within the flange clearance of "
                                       f"{ko['id']} for spool radii sampled at 1 mm steps.", True, m, [],
                                       f"The body stays clear of the sampled flange sweep of {ko['id']}.",
                                       "Spool sizes between samples, real spool tolerances, or sliding in practice."))
            continue
        if ko.get("type") != "box" or ko.get("frame") != frame:
            out.append(CheckResult("KEEP-OUT", "M", Verdict.NOT_CHECKED,
                                   f"KEEP-OUT NOT_CHECKED: {ko['id']} has no box geometry in the {frame} frame "
                                   f"({ko.get('note') or ko.get('type')}).", True, m))
            continue
        lo, hi = _bounds(ko, v.min(axis=0), v.max(axis=0), tol_mm)
        hit = triangles_overlap_box(tri, lo, hi)
        m.update(triangles_inside=int(hit.sum()), tol_mm=tol_mm)
        if hit.any():
            p = tri[hit].reshape(-1, 3)
            m["bbox_mm"] = [p.min(axis=0).round(3).tolist(), p.max(axis=0).round(3).tolist()]
            out.append(CheckResult("KEEP-OUT", "M", Verdict.FAIL,
                                   f"KEEP-OUT FAIL: {hit.sum()} body triangles enter {ko['id']} ({ko.get('rule', '')})",
                                   True, m, [f"remove material from {ko['id']}"]))
        else:
            out.append(CheckResult("KEEP-OUT", "M", Verdict.PASS,
                                   f"KEEP-OUT PASS: no body triangle enters {ko['id']} (contact within {tol_mm} mm "
                                   "allowed).", True, m, [], f"The body mesh stays out of {ko['id']}.",
                                   "Physical fit against the real installation."))
    return out


def check_boxes(boxes: dict, keep_outs, extent_lo, extent_hi, *, tol_mm: float = 1e-3,
                interfaces=None) -> list[CheckResult]:
    """One result per (box id, keep-out): axis-aligned boxes {id: (lo, hi)} in the keep-outs' frame."""
    out = []
    for bid, (blo, bhi) in boxes.items():
        for ko in keep_outs or []:
            m = {"helper_id": bid, "keep_out_id": ko["id"]}
            if ko.get("type") == "flange_sweep" and interfaces:
                cs, rs = flange_discs(ko, interfaces)
                d = np.linalg.norm(np.maximum(0.0, np.maximum(np.asarray(blo)[:2] - cs, cs - np.asarray(bhi)[:2])), axis=1)
                bad = d < rs - tol_mm
                m.update(sampled_spools=len(cs) // 2, sample_step_mm=1.0)
                out.append(CheckResult("KEEP-OUT", "M", Verdict.FAIL if bad.any() else Verdict.PASS,
                                       (f"KEEP-OUT FAIL: helper {bid} comes within the flange clearance of {ko['id']}." if bad.any()
                                        else f"KEEP-OUT PASS (sampled): helper {bid} stays clear of the flange sweep of {ko['id']}."),
                                       True, m, [f"move helper {bid} away from the spool flanges"] if bad.any() else []))
                continue
            if ko.get("type") != "box":
                out.append(CheckResult("KEEP-OUT", "M", Verdict.NOT_CHECKED,
                                       f"KEEP-OUT NOT_CHECKED: helper {bid} vs {ko['id']}: no keep-out geometry.", True, m))
                continue
            lo, hi = _bounds(ko, extent_lo, extent_hi, tol_mm)
            overlap = bool(np.all(np.minimum(hi, bhi) > np.maximum(lo, blo)))
            out.append(CheckResult("KEEP-OUT", "M", Verdict.FAIL if overlap else Verdict.PASS,
                                   (f"KEEP-OUT FAIL: helper {bid} enters {ko['id']}." if overlap else
                                    f"KEEP-OUT PASS: helper {bid} stays out of {ko['id']}."), True, m,
                                   [f"move helper {bid} out of {ko['id']}"] if overlap else []))
    return out


AXES = ("x", "y", "z")


def render_items(keep_outs, interfaces, body_lo, body_hi, *, margin_mm: float = 10.0, step_mm: float = 1.0) -> dict:
    """Bounded, render-only geometry for keep-outs in their (design = installed) frame.

    Open box bounds (null) become the body's bounding box widened by margin_mm, and are listed as unbounded so a
    viewer can say the drawn face is a clip, not a limit. A flange sweep becomes the same sampled discs the
    KEEP-OUT check tests (flange_discs), drawn over the body's Z range plus margin, since the sweep applies along
    the whole rod axis. Anything else is listed with rendered false and the reason. Not a clearance check.
    """
    lo = np.round(np.asarray(body_lo, float) - margin_mm, 6)
    hi = np.round(np.asarray(body_hi, float) + margin_mm, 6)
    items = []
    for ko in keep_outs or []:
        base = {"id": ko["id"], "type": ko.get("type"), "rule": ko.get("rule")}
        if ko.get("type") == "box":
            mn, mx = ko["min_mm"], ko["max_mm"]
            items.append({**base, "rendered": True,
                          "min_mm": [float(lo[k]) if v is None else float(v) for k, v in enumerate(mn)],
                          "max_mm": [float(hi[k]) if v is None else float(v) for k, v in enumerate(mx)],
                          "unbounded": [f"{s}_{AXES[k]}" for s, side in (("min", mn), ("max", mx))
                                        for k, v in enumerate(side) if v is None],
                          "original": {"min_mm": mn, "max_mm": mx}})
        elif ko.get("type") == "flange_sweep" and ko.get("axis") == "Z" and interfaces:
            cs, rs = flange_discs(ko, interfaces, step_mm)
            items.append({**base, "rendered": True, "axis": "Z",
                          "discs": [{"centre_xy_mm": [round(float(c[0]), 6), round(float(c[1]), 6)],
                                     "radius_mm": round(float(r), 6)} for c, r in zip(cs, rs)],
                          "z_min_mm": float(lo[2]), "z_max_mm": float(hi[2]), "unbounded": ["min_z", "max_z"],
                          "method": {"sampler": "fdmgen.catalog.checks.keepout.flange_discs", "step_mm": step_mm,
                                     "spool_diameter_mm": ko["spool_diameter_mm"], "rail_radius_mm": ko["rail_radius_mm"],
                                     "clearance_mm": ko["clearance_mm"], "rod_interfaces": ko["rod_interfaces"],
                                     "disc": "centre: spool resting on both rods at rail radius r; radius: spool radius "
                                             "+ clearance"},
                          "coverage": {"discs": len(rs), "sampled_spool_radii": len(rs) // len(ko["rail_radius_mm"]),
                                       "note": f"spool radii every {step_mm} mm at both rail-radius ends, as the KEEP-OUT "
                                               "check samples them; the envelope between samples is not drawn"}})
        else:
            items.append({**base, "rendered": False,
                          "reason": f"no renderable geometry ({ko.get('type')}{', ' + ko['note'] if ko.get('note') else ''})"})
    return {"clip": {"bbox_mm": [lo.tolist(), hi.tolist()], "margin_mm": margin_mm,
                     "basis": "body bounding box in the design frame, widened by margin_mm"}, "items": items}
