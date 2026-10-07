"""T-level checks on real slicer toolpaths: support roads per region (OVH-001 T, SUP-001, BRG-001 T).

Orca is the final judge of support (research/final/frodo.md 3.2): a region passes OVH-001 at T level
when the slice puts no Support / Support interface roads under it. Regions are print-frame XY boxes
(mm, design layout with the bed at z = 0). The object's placement on the plate is measured, not
assumed: the footprint of its non-support material in the G-code (extruder offset restored) is
matched to the design footprint, and a mismatch beyond tol_mm raises instead of guessing.
"""
from __future__ import annotations

import numpy as np

from ...gcode import Toolpath
from ..result import CheckResult, Verdict


def _is_support(tp: Toolpath) -> np.ndarray:
    return np.char.find(np.char.lower(tp.role.astype(str)), "support") >= 0


def locate(tp: Toolpath, design_lo_xy, design_hi_xy, offset=(0.0, 0.0, 0.0), *, half_width=0.21, tol_mm=0.3):
    """XY shift from design (print-frame layout) to plate coordinates, measured from the footprint."""
    m = tp.in_object & ~_is_support(tp)
    q = np.vstack([tp.start[m], tp.end[m]])[:, :2] + np.asarray(offset, float)[:2]
    lo, hi = q.min(axis=0), q.max(axis=0)
    dlo, dhi = np.asarray(design_lo_xy, float), np.asarray(design_hi_xy, float)
    size_err = np.abs((hi - lo) - (dhi - dlo - 2 * half_width))
    if size_err.max() > tol_mm:
        raise ValueError(f"G-code footprint {np.round(hi - lo, 3).tolist()} mm does not match the design "
                         f"{np.round(dhi - dlo, 3).tolist()} mm (minus one line width); the object was scaled, "
                         "rotated or is not this design")
    return (lo + hi) / 2 - (dlo + dhi) / 2


def support_by_region(tp: Toolpath, regions: dict, shift_xy, offset=(0.0, 0.0, 0.0), *, margin_mm=1.0) -> dict:
    """Support road length (mm) and volume (mm3) whose midpoints fall in each region's XY box (+ margin)."""
    sup = tp.in_object & _is_support(tp)
    mid = (tp.start[sup] + tp.end[sup]) / 2
    xy = mid[:, :2] + np.asarray(offset, float)[:2] - np.asarray(shift_xy, float)
    length = np.linalg.norm(tp.end[sup] - tp.start[sup], axis=1)
    vol = tp.volume[sup]
    out = {}
    for rid, (lo, hi) in regions.items():
        inside = np.all((xy >= np.asarray(lo[:2]) - margin_mm) & (xy <= np.asarray(hi[:2]) + margin_mm), axis=1)
        out[rid] = {"support_segments": int(inside.sum()), "support_length_mm": float(length[inside].sum()),
                    "support_volume_mm3": float(vol[inside].sum())}
    out["_unassigned"] = {"support_segments": int(sup.sum()) - sum(v["support_segments"] for v in out.values())}
    return out


def check_support(tp: Toolpath, regions: dict, design_bbox, *, offset=(0.0, 0.0, 0.0), rule="OVH-001",
                  slicer_settings: dict | None = None) -> CheckResult:
    """T level: FAIL when the slice puts support roads under any region where support is forbidden."""
    shift = locate(tp, design_bbox[0][:2], design_bbox[1][:2], offset)
    per = support_by_region(tp, regions, shift, offset)
    bad = {k: v for k, v in per.items() if not k.startswith("_") and v["support_segments"] > 0}
    metrics = {"per_region": per, "shift_xy_mm": np.round(shift, 4).tolist(), "slicer_settings": slicer_settings or {}}
    does_not = "How the region prints (P level); support is the slicer's decision under the stated settings only."
    if bad:
        names = ", ".join(f"{k} ({v['support_segments']} roads, {v['support_length_mm']:.0f} mm)" for k, v in bad.items())
        return CheckResult(rule, "T", Verdict.FAIL, f"{rule} T FAIL: the slice supports {names}.", False, metrics,
                           ["steepen or re-orient those regions", "or mark them support_allowed with a reason"], "",
                           does_not)
    return CheckResult(rule, "T", Verdict.PASS, f"{rule} T PASS: no support roads under any of {len(regions)} regions.",
                       False, metrics, [], "The slicer generated no support under these regions.", does_not)
