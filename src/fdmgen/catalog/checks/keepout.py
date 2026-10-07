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


def check_body(vertices, faces, keep_outs, *, tol_mm: float = 1e-3, frame: str = "installed") -> list[CheckResult]:
    """One result per keep-out: does the body mesh (in `frame`) enter it?"""
    v = np.asarray(vertices, float)
    tri = v[np.asarray(faces)]
    out = []
    for ko in keep_outs or []:
        m = {"keep_out_id": ko["id"]}
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


def check_boxes(boxes: dict, keep_outs, extent_lo, extent_hi, *, tol_mm: float = 1e-3) -> list[CheckResult]:
    """One result per (box id, keep-out): axis-aligned boxes {id: (lo, hi)} in the keep-outs' frame."""
    out = []
    for bid, (blo, bhi) in boxes.items():
        for ko in keep_outs or []:
            m = {"helper_id": bid, "keep_out_id": ko["id"]}
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
