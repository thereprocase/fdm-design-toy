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
    anywhere = np.zeros(len(xy), bool)
    for rid, (lo, hi) in regions.items():
        inside = np.all((xy >= np.asarray(lo[:2]) - margin_mm) & (xy <= np.asarray(hi[:2]) + margin_mm), axis=1)
        anywhere |= inside
        out[rid] = {"support_segments": int(inside.sum()), "support_length_mm": float(length[inside].sum()),
                    "support_volume_mm3": float(vol[inside].sum())}
    # regions may overlap, so a road can count for several regions; "_unassigned" is outside all of them
    out["_unassigned"] = {"support_segments": int((~anywhere).sum()), "support_length_mm": float(length[~anywhere].sum()),
                          "support_volume_mm3": float(vol[~anywhere].sum())}
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


def bridge_spans(tp: Toolpath, *, offset=(0.0, 0.0, 0.0), cell_mm: float = 0.1, support_density: float = 0.5,
                 margin_mm: float = 2.0) -> list[dict]:
    """Per bridge road: the longest run with nothing printed under it in the layer below.

    The layer below is every object road (support included: a road over support is not bridging) whose
    top is the highest top below the bridge layer, rasterised on an XY grid of cell_mm with road caps.
    A point is supported where that layer's density is at least support_density. A run bounded by support
    at both ends is a bridge span; a run that reaches a road end is reported as a cantilever instead.
    """
    from ...gcode.occupancy import deposit
    off = np.asarray(offset, float)
    role = np.char.lower(tp.role.astype(str))
    bridge = tp.in_object & (np.char.find(role, "bridge") >= 0)
    top = tp.end[:, 2]
    out = []
    for z in np.unique(np.round(top[bridge], 4)):
        here = bridge & (np.abs(top - z) < 1e-4)
        lower = tp.in_object & (top < z - 1e-4)
        if not lower.any():
            continue                                          # first layer: the bed supports it
        z_prev = top[lower].max()
        below = lower & (np.abs(top - z_prev) < 1e-4)
        h_prev = float(np.median(tp.height[below]))
        ends = np.vstack([tp.start[here], tp.end[here]])[:, :2] + off[:2]
        lo = np.append(ends.min(axis=0) - margin_mm, z_prev - h_prev) + 1e-4 * np.pi
        hi = np.append(ends.max(axis=0) + margin_mm, z_prev)
        h = np.array([cell_mm, cell_mm, h_prev])
        shape = (int(np.ceil((hi[0] - lo[0]) / cell_mm)), int(np.ceil((hi[1] - lo[1]) / cell_mm)), 1)
        g, _ = deposit(tp, off, np.eye(3), np.zeros(3), lo, h, shape, mask=below, caps=True)
        supported = (g[:, :, 0] / np.prod(h)) >= support_density
        for i in np.flatnonzero(here):
            a, b = tp.start[i, :2] + off[:2], tp.end[i, :2] + off[:2]
            L = float(np.linalg.norm(b - a))
            if L < 1e-9:
                continue
            step = cell_mm / 2
            s = np.arange(step / 2, L, step)
            p = a + (b - a) * (s / L)[:, None]
            idx = np.floor((p - lo[:2]) / cell_mm).astype(int)
            sup = supported[idx[:, 0], idx[:, 1]]
            runs, k = [], 0
            while k < len(sup):                               # maximal unsupported runs as (first, last) sample
                if not sup[k]:
                    j = k
                    while j + 1 < len(sup) and not sup[j + 1]:
                        j += 1
                    runs.append((k, j))
                    k = j + 1
                else:
                    k += 1
            span = max(((j - k + 1) * step for k, j in runs if k > 0 and j < len(sup) - 1), default=0.0)
            cant = max(((j - k + 1) * step for k, j in runs if k == 0 or j == len(sup) - 1), default=0.0)
            out.append({"role": str(tp.role[i]), "z_mm": float(z), "length_mm": L, "span_mm": span,
                        "cantilever_mm": cant, "supported_fraction": float(sup.mean())})
    return out


def check_bridge_toolpath(tp: Toolpath, *, offset=(0.0, 0.0, 0.0), max_span_external_mm: float = 10.0,
                          max_span_internal_mm: float = 18.0, cell_mm: float = 0.1,
                          provisional: bool = True) -> CheckResult:
    """BRG-001 at T: the longest unsupported run of any bridge road in the real slice, external vs internal."""
    rows = bridge_spans(tp, offset=offset, cell_mm=cell_mm)
    internal = np.array(["internal" in r["role"].lower() for r in rows], bool)
    spans = np.array([r["span_mm"] for r in rows]) if rows else np.zeros(0)

    def worst(sel):
        return float(spans[sel].max()) if sel.any() else 0.0
    ext, inn = worst(~internal), worst(internal)
    metrics = {"bridge_roads": len(rows), "external_roads": int((~internal).sum()), "internal_roads": int(internal.sum()),
               "max_span_external_mm": round(ext, 3), "max_span_internal_mm": round(inn, 3),
               "max_cantilever_mm": round(max((r["cantilever_mm"] for r in rows), default=0.0), 3),
               "limits_mm": {"external": max_span_external_mm, "internal": max_span_internal_mm}, "cell_mm": cell_mm,
               "bridge_layers_z_mm": sorted({r["z_mm"] for r in rows})}
    does_not = ("Sag or anchor quality in print (P level); spans are measured on a cell_mm raster of the layer below, "
                "so they carry about one cell of error; cantilevers (runs reaching a road end) are reported, not judged.")
    over = [f"external {ext:.1f} mm > {max_span_external_mm:g}" if ext > max_span_external_mm else None,
            f"internal {inn:.1f} mm > {max_span_internal_mm:g}" if inn > max_span_internal_mm else None]
    over = [o for o in over if o]
    if over:
        return CheckResult("BRG-001", "T", Verdict.FAIL, f"BRG-001 T FAIL: the slice bridges {'; '.join(over)}.",
                           provisional, metrics, ["shorten the span with a pillar or rib", "or re-orient"], "", does_not)
    msg = (f"BRG-001 T PASS: {len(rows)} bridge roads, longest span external {ext:.1f} mm "
           f"(limit {max_span_external_mm:g}), internal {inn:.1f} mm (limit {max_span_internal_mm:g}).")
    return CheckResult("BRG-001", "T", Verdict.PASS, msg, provisional, metrics, [],
                       "Every bridge road in the slice spans no more than the limits over the printed layer below.",
                       does_not)
