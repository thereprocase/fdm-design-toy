"""Assemble a design report: lint, catalog checks on the body in a chosen pose, orientation summary.

Every result keeps its level, verdict, provisional flag and its establishes / does-not-establish text,
and the report states the highest rung of the verdict ladder (PLAN D16) the evidence reaches. Per-layer
raster checks can run over z-slabs in worker processes: every one of them is strictly per layer (the
bridge check also reads the layer below, so each slab carries one layer of overlap), so the split is exact.
"""
from __future__ import annotations

import multiprocessing as mp

import numpy as np

from ..catalog import CheckResult, Verdict, governing
from ..catalog.checks import layers, ovh

LADDER = ("GEOMETRY", "TOOLPATH", "SCREEN", "FE_3D", "COUPON", "PRINTED", "QUALIFIED")
_SLAB = {}


def _slab(args):
    k0, k1, d_min, line_w, max_span = args
    occ, h, org = _SLAB["occ"], _SLAB["h"], _SLAB["origin"]
    lo = max(k0 - 1, 0)
    sub = occ[:, :, lo:k1]
    keep = slice(k0 - lo, None)
    o = (org[0], org[1], org[2] + lo * h[2])
    wall = layers.thin_regions(sub[:, :, keep], h, d_min)
    gap = layers.thin_regions(~sub[:, :, keep], h, d_min, pad_value=True)
    bead = layers.check_bead_bands(sub[:, :, keep], h, line_width_mm=line_w,
                                   origin=(org[0], org[1], org[2] + k0 * h[2]))
    brg = layers.check_bridge(sub, h, max_span, origin=o, bed_layer=0 if k0 > 0 else None)

    def summ(m):
        if not m.any():
            return None
        idx = np.argwhere(m)
        base = np.array([org[0], org[1], org[2] + k0 * h[2]])
        return {"area": float(m.sum() * h[0] * h[1]), "layers": int(m.any(axis=(0, 1)).sum()),
                "lo": (idx.min(0) * np.asarray(h) + base).tolist(), "hi": ((idx.max(0) + 1) * np.asarray(h) + base).tolist()}
    return {"wall": summ(wall), "gap": summ(gap), "bead": bead.metrics.get("near_edge", {}),
            "bead_verdict": bead.verdict.value, "brg_over": brg.metrics.get("over_limit", []), "brg_worst": brg.metrics.get("worst")}


def layer_checks(occ, h, origin, *, d_min_mm=0.84, line_width_mm=0.42, max_span_mm=10.0, workers=1) -> list[CheckResult]:
    """WALL-001, GAP-001, WALL-002 and BRG-001 on a print-frame occupancy grid, optionally over z-slabs in parallel."""
    _SLAB.update(occ=occ, h=tuple(float(x) for x in h), origin=tuple(float(x) for x in origin))
    nz = occ.shape[2]
    step = max(1, -(-nz // max(1, workers)))
    jobs = [(k, min(k + step, nz), d_min_mm, line_width_mm, max_span_mm) for k in range(0, nz, step)]
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            parts = pool.map(_slab, jobs)
    else:
        parts = [_slab(j) for j in jobs]
    out = []
    px = f"{h[0]} x {h[1]} x {h[2]} mm cells"
    for key, rule, what in (("wall", "WALL-001", "solid features"), ("gap", "GAP-001", "clear gaps")):
        ps = [p[key] for p in parts if p[key]]
        lim = "Bead counts in the real toolpaths (T level); features under 0.2 mm2 per layer; widths finer than one cell."
        if ps:
            area = sum(p["area"] for p in ps)
            lo = np.min([p["lo"] for p in ps], 0).round(2).tolist()
            hi = np.max([p["hi"] for p in ps], 0).round(2).tolist()
            out.append(CheckResult(rule, "M", Verdict.FAIL,
                                   f"{rule} FAIL: {what} narrower than {d_min_mm} mm on {sum(p['layers'] for p in ps)} layers "
                                   f"({area:.1f} mm2 summed), print-frame box {lo}..{hi} ({px}).", True,
                                   {"area_mm2": area, "bbox_print_mm": [lo, hi]}, [], "", lim))
        else:
            out.append(CheckResult(rule, "M", Verdict.PASS, f"{rule} PASS: no {what} narrower than {d_min_mm} mm ({px}).",
                                   True, {}, [], f"Every {what[:-1]} admits a {d_min_mm} mm disc on every layer.", lim))
    near = {}
    for p in parts:
        for e, v in p["bead"].items():
            if e not in near or v["length_mm"] > near[e]["length_mm"]:
                near[e] = v
    bead_fail = any(p["bead_verdict"] == "FAIL" for p in parts)
    out.append(CheckResult("WALL-002", "M", Verdict.FAIL if bead_fail else Verdict.PASS,
                           (f"WALL-002 FAIL: thin features run along Arachne bead-count edges: {near}" if bead_fail else
                            "WALL-002 PASS: no thin feature runs along a bead-count edge for 2 mm or more."), True,
                           {"near_edge": near}, [], "", "The bead count Orca actually chose (T level)."))
    over = sorted((o for p in parts for o in p["brg_over"]), key=lambda o: -o["span_mm"])
    worst = max((p["brg_worst"] for p in parts if p["brg_worst"]), key=lambda w: w["span_mm"], default=None)
    out.append(CheckResult("BRG-001", "M", Verdict.FAIL if over else Verdict.PASS,
                           (f"BRG-001 FAIL: {len(over)} regions exceed {max_span_mm} mm; worst {over[0]['span_mm']:.1f} mm at "
                            f"layer {over[0]['layer']}." if over else
                            f"BRG-001 PASS: longest anchored span {worst['span_mm']:.1f} mm." if worst else
                            "BRG-001 PASS: nothing printed over air."), True,
                           {"over_limit": over[:10], "worst": worst}, [], "",
                           "Bridge direction, anchor quality and sag (T and P levels)."))
    return out


def run_report(problem: dict, vertices, faces, candidate: dict, *, raster_px=0.1, workers=1, lint_findings=()) -> dict:
    """All checks for the body (design frame) placed by the candidate's R/t."""
    import trimesh

    from ..catalog.checks.keepout import check_body
    from ..geom.voxel import voxelise
    R, t = np.asarray(candidate["R_design_to_print"]), np.asarray(candidate["t_mm"])
    V = np.asarray(vertices, float) @ R.T + t
    F = np.asarray(faces)
    results = [ovh.check_mesh(V, F, 50.0)]
    occ5, g5 = voxelise(trimesh.Trimesh(V, F, process=False), h=(0.503, 0.503, 0.6), multiple=1)
    results.append(ovh.check_voxel(occ5, g5.h, 50.0, origin=g5.origin))
    occ, g = voxelise(trimesh.Trimesh(V, F, process=False), h=(raster_px, raster_px, 0.2), multiple=1)
    results += layer_checks(occ, g.h, g.origin, workers=workers)
    results += check_body(vertices, faces, problem.get("keep_outs"), interfaces=problem.get("interfaces"))
    cols = candidate["columns"]
    rung = "GEOMETRY"
    if any(k.startswith("t_") for k in cols):
        rung = "TOOLPATH"
    return {"problem": problem.get("id"), "candidate": candidate, "results": results, "lint": list(lint_findings),
            "ladder_rung": rung, "raster": {"px_mm": raster_px, "dz_mm": 0.2, "cells": int(occ.size)}}


def render_markdown(rep: dict, provenance: dict | None = None) -> str:
    c = rep["candidate"]
    gov = governing(rep["results"])
    lines = [f"# Design report: {rep['problem']}, pose {c['id']}", ""]
    for k, v in (provenance or {}).items():
        lines.append(f"- **{k}:** {v}")
    rung = rep["ladder_rung"]
    lines += ["", f"**Evidence reached: {rung}** on the ladder " + " → ".join(
        f"**{r}**" if r == rung else r for r in LADDER) + ". Nothing here is physically qualified.", ""]
    if rep["lint"]:
        lines += ["## Problem lint", ""] + [f"- {f}" for f in rep["lint"]] + [""]
    lines += ["## Summary by rule (highest level that ran governs)", "", "| Rule | Level | Verdict | Provisional |", "|---|---|---|---|"]
    for rule, r in sorted(gov.items()):
        lines.append(f"| {rule} | {r.level} | {r.verdict.value} | {'yes' if r.provisional else 'no'} |")
    cols = c["columns"]
    reasons = "; ".join(c["reasons"]) or "fits, stable, enough contact"
    lines += ["", "## Orientation", "",
              f"Build direction (design frame) {c['build_dir_design']}, rank {c['rank']}, feasible: {c['feasible']} ({reasons})."]
    for key in ("ovh_fail_mm2", "F_L_max", "F_L_max_vendor_corner", "t_support_segments"):
        if key in cols and cols[key]["value"] is not None:
            v = cols[key]
            lines.append(f"- {key}: {v['value']:.4g} ({v['rule']} {v['level']}, {v['verdict']}; {v['fidelity']})")
    lines += ["", "## Checks", ""]
    for r in rep["results"]:
        lines += [f"### {r.rule} ({r.level}): {r.verdict.value}{' (PROVISIONAL)' if r.provisional and r.verdict in (Verdict.PASS, Verdict.FAIL) else ''}",
                  "", r.message, ""]
        if r.fixes:
            lines.append("Fixes: " + "; ".join(r.fixes))
        if r.establishes:
            lines.append(f"Establishes: {r.establishes}")
        if r.does_not_establish:
            lines.append(f"Does not establish: {r.does_not_establish}")
        lines.append("")
    rs = rep["raster"]
    lines += [f"Raster checks ran on {rs['px_mm']} x {rs['px_mm']} x {rs['dz_mm']} mm cells ({rs['cells']:,} cells)."]
    return "\n".join(lines) + "\n"
