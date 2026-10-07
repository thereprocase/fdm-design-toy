"""Per-layer raster checks: WALL-001 minimum solid width, GAP-001 minimum clear gap, BRG-001 bridge span.

Input is a boolean occupancy stack occ[ix, iy, iz] in the print frame (z = build direction) with cell
size h = (dx, dy, dz): a sectioned mesh (M level, dz = layer height) or a thresholded design field (V).
All in-plane operations are strictly per layer.

Width/gap method: morphological opening of the phase with a disc of diameter d_min. Pixels the opening
removes are thinner than d_min, except the unavoidable residue in corners (a disc cannot reach into a
corner tip). Residue that lies within `corner_tol` (default 0.5 r) of the kept, opened set is treated
as corner rounding and ignored; at a 90-degree corner the tip is 0.414 r away. Consequence (stated in
every result): stubs and pinches shorter than about 0.5 r are not reported. The threshold is resolved
to one pixel.
"""
from __future__ import annotations

import numpy as np

from ..result import CheckResult, Verdict


def _ndi():
    try:
        from scipy import ndimage
    except ImportError as e:            # pragma: no cover - exercised only without the geom extra
        raise ImportError("layer checks need scipy (pip install 'fdmgen[geom]')") from e
    return ndimage


def _disc(radius_mm: float, dx: float, dy: float) -> np.ndarray:
    rx, ry = int(np.floor(radius_mm / dx + 1e-9)), int(np.floor(radius_mm / dy + 1e-9))
    i, j = np.mgrid[-rx:rx + 1, -ry:ry + 1]
    return ((i * dx) ** 2 + (j * dy) ** 2 <= radius_mm ** 2 + 1e-12)[:, :, None]


def _layer_structure():
    s = np.zeros((3, 3, 3), bool)
    s[:, :, 1] = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]
    return s


def _box(mask, h, origin):
    idx = np.argwhere(mask)
    lo = np.asarray(origin) + idx.min(axis=0) * np.asarray(h)
    hi = np.asarray(origin) + (idx.max(axis=0) + 1) * np.asarray(h)
    return lo.round(3).tolist(), hi.round(3).tolist()


def thin_regions(phase: np.ndarray, h, d_min_mm: float, corner_tol: float = 0.5, pad_value: bool = False):
    """Mask of pixels in `phase` that belong to features narrower than d_min_mm (per layer).

    pad_value is what lies beyond the grid edge: False for material, True for the void phase (the
    space around a part is open), so the grid edge never reads as a thin feature.
    """
    ndi = _ndi()
    dx, dy, _ = h
    r = d_min_mm / 2.0
    pad = int(np.ceil(r / min(dx, dy))) + 2
    p = np.pad(phase, ((pad, pad), (pad, pad), (0, 0)), constant_values=pad_value)
    opened = ndi.binary_opening(p, structure=_disc(r, dx, dy))
    residue = p & ~opened
    if not residue.any():
        return np.zeros_like(phase)
    # distance (in-plane only) from each residue pixel to the kept set; z sampling huge keeps it per layer
    dist = ndi.distance_transform_edt(~opened, sampling=(dx, dy, 1e9))
    lab, n = ndi.label(residue, structure=_layer_structure())
    far = ndi.maximum(dist, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = np.asarray(far) > corner_tol * r
    out = keep[lab]
    return out[pad:-pad, pad:-pad]


def _width_result(rule, phase_name, occ_phase, h, d_min, origin, provisional, corner_tol):
    thin = thin_regions(occ_phase, h, d_min, corner_tol, pad_value=(phase_name == "void"))
    px = h[0] * h[1]
    metrics = {"d_min_mm": d_min, "pixel_mm": [h[0], h[1]], "thin_area_mm2_summed_over_layers": float(thin.sum() * px),
               "layers_affected": int(thin.any(axis=(0, 1)).sum()), "corner_tol_r": corner_tol}
    does_not = (f"Bead counts or gap fill in the real toolpaths (T level); stubs and pinches shorter than "
                f"about {corner_tol} x {d_min / 2:.2f} mm; widths finer than one pixel ({h[0]} mm).")
    if thin.any():
        lo, hi = _box(thin, h, origin)
        metrics["bbox_print_mm"] = [lo, hi]
        what = "solid features" if phase_name == "material" else "clear gaps"
        msg = (f"{rule} FAIL: {what} narrower than {d_min:.2f} mm on {metrics['layers_affected']} layer(s) "
               f"({metrics['thin_area_mm2_summed_over_layers']:.1f} mm2 summed over layers), print-frame "
               f"X {lo[0]:.1f}..{hi[0]:.1f}, Y {lo[1]:.1f}..{hi[1]:.1f}, Z {lo[2]:.2f}..{hi[2]:.2f} mm. "
               + ("The slicer may drop or only partly print them." if phase_name == "material"
                  else "Neighbouring beads may fuse across them."))
        fixes = ([f"thicken to >= {d_min:.2f} mm", "remove the feature", "merge it into a neighbour"]
                 if phase_name == "material" else [f"open the gap to >= {d_min:.2f} mm", "close the gap fully"])
        return CheckResult(rule, "M", Verdict.FAIL, msg, provisional, metrics, fixes, "", does_not)
    msg = f"{rule} PASS: no {phase_name} feature narrower than {d_min:.2f} mm on any layer (pixel {h[0]} mm)."
    return CheckResult(rule, "M", Verdict.PASS, msg, provisional, metrics, [],
                       f"Every {phase_name} feature admits a {d_min:.2f} mm disc on every layer.", does_not)


def check_wall(occ, h, d_min_mm: float = 0.84, *, origin=(0, 0, 0), provisional=True, corner_tol=0.5):
    """WALL-001: solid features at least d_min (default 2w = 0.84 mm) wide in XY."""
    return _width_result("WALL-001", "material", np.asarray(occ, bool), h, d_min_mm, origin, provisional, corner_tol)


def check_gap(occ, h, d_min_mm: float = 0.84, *, origin=(0, 0, 0), provisional=True, corner_tol=0.5):
    """GAP-001: clear gaps at least d_min wide in XY (the void phase, open space around the part included)."""
    return _width_result("GAP-001", "void", ~np.asarray(occ, bool), h, d_min_mm, origin, provisional, corner_tol)


def check_bridge(occ, h, max_span_mm: float = 10.0, *, origin=(0, 0, 0), bed_layer: int | None = None,
                 provisional=True, min_region_mm2: float | None = None) -> CheckResult:
    """BRG-001 (M): per layer, the span of material printed over nothing.

    For each connected region of a layer that has no material directly below it, the span estimate is
    2 x the largest in-plane distance from a region pixel to material that is supported in the same layer
    (a bridge anchored at both ends has its midpoint L/2 from an anchor; a ceiling anchored all round is
    measured across its short direction). One-sided cantilevers read as twice their length (conservative;
    OVH-001 governs those). A region with no supported material in its layer cannot bridge at all.
    """
    ndi = _ndi()
    occ = np.asarray(occ, bool)
    dx, dy, dz = h
    zs = np.flatnonzero(occ.any(axis=(0, 1)))
    if zs.size == 0:
        return CheckResult("BRG-001", "M", Verdict.NOT_CHECKED, "BRG-001 NOT_CHECKED: the grid is empty.", provisional)
    bed = int(zs[0]) if bed_layer is None else bed_layer
    min_region = min_region_mm2 if min_region_mm2 is not None else 4 * dx * dy
    worst, regions = None, []
    for k in range(bed + 1, occ.shape[2]):
        layer = occ[:, :, k]
        if not layer.any():
            continue
        air = layer & ~occ[:, :, k - 1]
        if not air.any():
            continue
        anchored = layer & occ[:, :, k - 1]
        lab, n = ndi.label(air)
        dist = ndi.distance_transform_edt(~anchored, sampling=(dx, dy)) if anchored.any() else None
        for i in range(1, n + 1):
            reg = lab == i
            area = float(reg.sum() * dx * dy)
            if area < min_region:
                continue
            span = float("inf") if dist is None else 2.0 * float(dist[reg].max())
            idx = np.argwhere(reg)
            lo = (np.asarray(origin)[:2] + idx.min(axis=0) * (dx, dy)).round(3).tolist()
            hi = (np.asarray(origin)[:2] + (idx.max(axis=0) + 1) * (dx, dy)).round(3).tolist()
            r = {"layer": k, "z_mm": round(float(origin[2] + k * dz), 4), "span_mm": span, "area_mm2": area,
                 "bbox_xy_mm": [lo, hi]}
            regions.append(r)
            if worst is None or span > worst["span_mm"]:
                worst = r
    over = [r for r in regions if r["span_mm"] > max_span_mm]
    metrics = {"max_span_mm": max_span_mm, "regions": len(regions), "over_limit": over[:20],
               "worst": worst}
    does_not = ("Bridge direction, anchor quality, sag, or what Orca's bridge detection does (T level); "
                "obstacle-aware spans (distances are straight lines in the layer).")
    if over:
        w = max(over, key=lambda r: r["span_mm"])
        span_txt = "has no anchor in its layer" if np.isinf(w["span_mm"]) else f"spans about {w['span_mm']:.1f} mm"
        msg = (f"BRG-001 FAIL: {len(over)} unsupported region(s) exceed the {max_span_mm:.0f} mm bridge limit. "
               f"Worst: layer {w['layer']} (Z {w['z_mm']:.2f} mm) {span_txt}, XY {w['bbox_xy_mm'][0]}..{w['bbox_xy_mm'][1]}.")
        return CheckResult("BRG-001", "M", Verdict.FAIL, msg, provisional, metrics,
                           ["add a pillar or rib under the span", "slope the ceiling to >= 50 deg (self-supporting)",
                            "split the span with an intermediate anchor"], "", does_not)
    longest = "none" if worst is None else f"{worst['span_mm']:.1f} mm"
    msg = f"BRG-001 PASS: every unsupported region is anchored and spans <= {max_span_mm:.0f} mm (longest {longest})."
    return CheckResult("BRG-001", "M", Verdict.PASS, msg, provisional, metrics, [],
                       f"No layer region over air spans more than {max_span_mm:.0f} mm between anchors.", does_not)
