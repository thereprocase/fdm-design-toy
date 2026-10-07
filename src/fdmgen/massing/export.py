"""Turn a validated massing plan (fdmgen.planning.PlanningDraft) into an Orca project 3MF.

Body = the problem's body mesh in the chosen pose, printed with the plan's walls and skin and 0 % sparse
infill (sparse infill is never credited, PLAN D12). Each helper box becomes a modifier at 100 % infill.
Per-modifier settings are only those the capability file records as honoured for this profile context;
anything else is refused in plain language. MOD-001 is checked on the helper geometry before export.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import yaml

from ..catalog import CheckResult, Verdict, load_rules
from ..slicer.threemf import Part, write_project

HELPER_SETTINGS = {"sparse_infill_density": "100%"}       # the exact value the capability probe measured
_BOX_FACES = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                       [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])


def load_capabilities(path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _box_faces(v):
    tri = v[_BOX_FACES]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()
    return _BOX_FACES if vol > 0 else _BOX_FACES[:, ::-1]


def _bonding(helpers, body_vertices, body_faces, shell_band_mm, samples) -> list[CheckResult]:
    """Sampled contact between each helper and the printed shell band (the body is printed at 0 % infill,
    so the inside of the envelope is air except for the walls and skins near its surface)."""
    import trimesh
    body = trimesh.Trimesh(body_vertices, body_faces, process=False)
    blo, bhi = np.min(body_vertices, axis=0), np.max(body_vertices, axis=0)
    g = (np.arange(samples) + 0.5) / samples - 0.5
    grid = np.array(np.meshgrid(g, g, g, indexing="ij")).reshape(3, -1).T
    out = []
    for h in helpers:
        lo, hi = h.center_mm - h.size_mm / 2, h.center_mm + h.size_mm / 2
        if np.any(hi < blo) or np.any(lo > bhi):
            out.append(CheckResult("MOD-001", "M", Verdict.FAIL,
                                   f"MOD-001 FAIL: helper {h.id} lies entirely outside the body's bounding box, so it "
                                   "cannot touch printed material and a modifier there prints nothing.", True,
                                   {"helper": h.id}, ["move the helper into the body"]))
            continue
        pts = h.center_mm + grid * h.size_mm
        sd = trimesh.proximity.signed_distance(body, pts)       # > 0 inside the body, distance to its surface
        in_band = int(((sd >= 0) & (sd <= shell_band_mm)).sum())
        straddles = bool((sd > 0).any() and (sd < 0).any())
        metrics = {"helper": h.id, "samples": len(pts), "in_shell_band": in_band, "straddles_surface": straddles,
                   "shell_band_mm": shell_band_mm}
        if in_band or straddles:
            out.append(CheckResult("MOD-001", "M", Verdict.PASS,
                                   f"MOD-001 bonding (sampled): {in_band} of {len(pts)} sample points of helper {h.id} lie "
                                   f"in the printed shell band (<= {shell_band_mm:.2f} mm under the body surface)"
                                   + (" and the helper crosses the body surface" if straddles else "") + ".", True, metrics,
                                   [], "Sampled points of the helper meet the shell band.",
                                   "A continuous bond in the slice; read the sliced roads back to confirm it."))
        else:
            out.append(CheckResult("MOD-001", "M", Verdict.NOT_CHECKED,
                                   f"MOD-001 bonding NOT_CHECKED: no sample point of helper {h.id} lies in the printed shell "
                                   f"band (<= {shell_band_mm:.2f} mm under the body surface). It may float in the 0 % "
                                   "interior, but sampling cannot rule out contact between samples; move it against a "
                                   "wall or skin, or confirm in the slice.", True, metrics,
                                   ["place the helper so it touches a wall or skin"]))
    return out


def check_helpers(helpers, body_vertices=None, body_faces=None, *, gap_min_mm=None, samples=8,
                  shell_band_mm: float = 0.8) -> list[CheckResult]:
    """MOD-001 (M) on design-frame helper boxes: size, pairwise separation or overlap, and sampled contact
    with the printed shell band (shell_band_mm: how far under the surface walls and skins reach)."""
    d = gap_min_mm if gap_min_mm is not None else load_rules()["MOD-001"].parameters["boundary_gap_min_mm"]["value"]
    out = []
    small = [(h.id, float(np.min(h.size_mm))) for h in helpers if np.min(h.size_mm) < d]
    if small:
        out.append(CheckResult("MOD-001", "M", Verdict.FAIL,
                               "MOD-001 FAIL: helper(s) " + ", ".join(f"{i} (smallest edge {s:.2f} mm)" for i, s in small)
                               + f" are thinner than {d:.2f} mm; the slicer may drop them or print slivers.",
                               True, {"too_small": small}, [f"make every helper edge at least {d:.2f} mm"]))
    pairs = []
    for i in range(len(helpers)):
        for j in range(i + 1, len(helpers)):
            a, b = helpers[i], helpers[j]
            ov = np.minimum(a.center_mm + a.size_mm / 2, b.center_mm + b.size_mm / 2) - \
                np.maximum(a.center_mm - a.size_mm / 2, b.center_mm - b.size_mm / 2)
            if np.all(ov > 0):
                if ov.min() < d:
                    pairs.append((a.id, b.id, f"overlap only {ov.min():.2f} mm"))
            else:
                gap = float(np.linalg.norm(np.maximum(0.0, -ov)))
                if gap < d:
                    pairs.append((a.id, b.id, f"{gap:.2f} mm apart"))
    if pairs:
        out.append(CheckResult("MOD-001", "M", Verdict.FAIL,
                               "MOD-001 FAIL: helper boundaries closer than " + f"{d:.2f} mm without overlapping by that much: "
                               + "; ".join(f"{a} / {b} {why}" for a, b, why in pairs) + ". Thin slivers between modifiers print badly.",
                               True, {"pairs": pairs}, [f"overlap by >= {d:.2f} mm or separate by >= {d:.2f} mm", "or merge them"]))
    if body_vertices is not None:
        out += _bonding(helpers, body_vertices, body_faces, shell_band_mm, samples)
    if not out:
        out.append(CheckResult("MOD-001", "M", Verdict.PASS, f"MOD-001 PASS: helper sizes and spacing respect {d:.2f} mm.", True))
    return out


def export_plan(plan, body_vertices, body_faces, template: bytes, capabilities: dict, *, layer_height_mm=0.2,
                helper_settings=None, allow_unmeasured_values: bool = False, interfaces=None,
                keep_outs=None) -> tuple[bytes, dict]:
    """Orca 3MF bytes and a report for a validated plan; raises ValueError on a refused setting."""
    settings = dict(helper_settings or HELPER_SETTINGS)
    t_sha = hashlib.sha256(template).hexdigest()
    ctx_match = capabilities["context"].get("template_3mf_sha256") == t_sha
    recs = capabilities["settings"]
    evidence, refused = {}, {}
    for k, v in settings.items():
        exact = [r for r in recs if r["status"] == "honoured" and str(r["requested"].get(k)) == str(v)]
        if exact:
            evidence[k] = {"value": v, "evidence": "measured" if ctx_match else "unverified: other profile context",
                           "receipt": exact[0]["receipt"]["gcode_sha256"]}
        elif any(r["key"] == k and r["status"] == "ignored" for r in recs):
            refused[k] = "ignored by the slicer"
        elif any(r["key"] == k and r["status"] == "honoured" for r in recs):
            if allow_unmeasured_values:
                evidence[k] = {"value": v, "evidence": "unverified: the key was measured at other values"}
            else:
                refused[k] = f"value {v!r} not measured"
        else:
            refused[k] = "not measured"
    if refused:
        raise ValueError("these per-helper settings cannot be used: " + ", ".join(f"{k} ({why})" for k, why in refused.items())
                         + "; see the capability file for what this slicer honours on a modifier")
    skin_layers = int(np.ceil(plan.skin_mm / layer_height_mm - 1e-9))
    object_settings = {"wall_loops": int(plan.walls), "top_shell_layers": skin_layers, "bottom_shell_layers": skin_layers,
                       "top_shell_thickness": 0, "bottom_shell_thickness": 0, "sparse_infill_density": "0%"}
    parts = [Part("BODY print", plan.to_print(body_vertices), np.asarray(body_faces))]
    for h in ([] if plan.shell_only else plan.helpers):
        v = plan.to_print(h.corners_design_mm())
        parts.append(Part(f"{h.id} MODIFIER 100%", v, _box_faces(v), "modifier_part", settings))
    data = write_project(template, parts, object_name=f"{plan.problem} {plan.candidate_id} massing",
                         object_settings=object_settings)
    band = max(plan.walls * 0.42, plan.skin_mm)            # walls (about one line width each) or skins, whichever reaches further
    checks = [] if plan.shell_only else check_helpers(plan.helpers, body_vertices, body_faces, shell_band_mm=band)
    if not plan.shell_only:
        checks += check_keep_clear(plan.helpers, interfaces)
        if keep_outs:
            from ..catalog.checks.keepout import check_boxes
            bv = np.asarray(body_vertices, float)
            boxes = {h.id: (h.center_mm - h.size_mm / 2, h.center_mm + h.size_mm / 2) for h in plan.helpers}
            checks += check_boxes(boxes, keep_outs, bv.min(axis=0), bv.max(axis=0), interfaces=interfaces)
    report = {
        "schema": "fdmgen/massing-export@0.1",
        "plan": {"draft_sha256": plan.draft_sha256, "table_sha256": plan.table_sha256, "mesh_sha256": plan.mesh_sha256,
                 "problem": plan.problem, "candidate_id": plan.candidate_id},
        "template_3mf_sha256": t_sha, "project_3mf_sha256": hashlib.sha256(data).hexdigest(),
        "capability_context_matches_template": ctx_match,
        "settings_evidence": evidence,
        "object_settings": object_settings,
        "body_print_bbox_mm": [plan.to_print(body_vertices).min(axis=0).round(3).tolist(),
                               plan.to_print(body_vertices).max(axis=0).round(3).tolist()],
        "skin_note": f"{plan.skin_mm} mm skin -> {skin_layers} layers of {layer_height_mm} mm",
        "helpers": [{"id": h.id, "settings": settings,
                     "print_bbox_mm": [plan.to_print(h.corners_design_mm()).min(axis=0).round(3).tolist(),
                                       plan.to_print(h.corners_design_mm()).max(axis=0).round(3).tolist()]}
                    for h in ([] if plan.shell_only else plan.helpers)],
        "checks": [c.to_dict() for c in checks],
        "establishes": "A sliceable project carrying the plan's pose, shell and helper intent, with MOD-001 geometry checks.",
        "does_not_establish": "That the slice credits the helpers as intended (slice it and read it back), or any strength.",
    }
    if not ctx_match:
        report["warning"] = ("the capability file was measured with a different template profile; every per-helper "
                             "setting is unverified in this context")
    return data, report


def _slicer_context(text: str, tp) -> dict:
    """Who sliced it and with which profile: the G-code's own header and config block."""
    import re

    from ..catalog.checks.proc import settings_from_gcode
    cfg = settings_from_gcode(text)
    gen = re.search(r"^; generated by (\S+) (\S+)", text, re.MULTILINE)
    keys = ("printer_model", "print_settings_id", "filament_settings_id", "layer_height", "wall_loops",
            "sparse_infill_density", "filament_shrink", "enable_support")
    return {"gcode_sha256": tp.meta["gcode_sha256"], "generator": gen.group(1) if gen else None,
            "version": gen.group(2) if gen else None, **{k: cfg.get(k) for k in keys}}


def _solid_in_boxes(tp, off, shift, boxes):
    from ..slicer.modifier_spike import _fraction_in_box
    m = tp.in_object
    a = tp.start[m, :2] + off[:2] - shift
    b = tp.end[m, :2] + off[:2] - shift
    z, role, vol = tp.end[m, 2], tp.role[m], tp.volume[m]
    out = []
    for lo, hi in boxes:
        f = _fraction_in_box(a, b, lo[:2], hi[:2]) * ((z > lo[2]) & (z <= hi[2] + 1e-6))
        out.append(float((vol * f)[role == "Internal solid infill"].sum()))
    return out


def slice_evidence(report: dict, gcode_text: str, baseline_gcode_text: str | None = None, *,
                   min_fill_fraction: float = 0.10, min_attributable_mm: float = 0.84,
                   min_added_mm3: float = 0.5) -> dict:
    """T level: read the slice of an exported project back; per helper, the solid infill it added.

    With a slice of the shell-only project (same body and settings, no helpers) as the baseline, the
    helper's contribution is the difference in solid infill inside its box: below min_fill_fraction of the
    box volume, or below min_added_mm3 (about six bead segments one wall pair long; a fraction means
    nothing for a box smaller than a bead), is a FAIL (dropped, or outside the body). Without a baseline the body's own solid material
    (skins, internal plates) cannot be told apart from the helper's, so boxes thinner than
    min_attributable_mm are NOT_CHECKED and larger ones are judged on the absolute fill.
    A PASS says the helper added material in its box, not that it is continuous with the shell.
    """
    from ..catalog.checks.toolpath import locate
    from ..gcode import credit, extruder_offset, read_gcode
    tp = read_gcode(gcode_text)
    off = extruder_offset(gcode_text)
    slicer = _slicer_context(gcode_text, tp)
    (blo, bhi) = [np.asarray(b) for b in report["body_print_bbox_mm"]]
    shift = locate(tp, blo[:2], bhi[:2], off)
    boxes = [tuple(np.asarray(x) for x in h["print_bbox_mm"]) for h in report["helpers"]]
    solid = _solid_in_boxes(tp, off, shift, boxes)
    base, base_ctx, mismatch = None, None, []
    if baseline_gcode_text is not None:
        tb = read_gcode(baseline_gcode_text)
        ob = extruder_offset(baseline_gcode_text)
        base = _solid_in_boxes(tb, ob, locate(tb, blo[:2], bhi[:2], ob), boxes)
        base_ctx = _slicer_context(baseline_gcode_text, tb)
        mismatch = [k for k in ("generator", "version", "printer_model", "print_settings_id", "filament_settings_id",
                                "layer_height", "wall_loops", "sparse_infill_density")
                    if slicer.get(k) != base_ctx.get(k)]
    rows = []
    for k, h in enumerate(report["helpers"]):
        lo, hi = boxes[k]
        box = float(np.prod(hi - lo))
        added = solid[k] - (base[k] if base is not None else 0.0)
        frac = added / box if box > 0 else 0.0
        row = {"id": h["id"], "solid_infill_in_box_mm3": round(solid[k], 3), "box_volume_mm3": round(box, 3),
               "baseline_solid_infill_mm3": None if base is None else round(base[k], 3),
               "added_solid_mm3": round(added, 3), "added_fill_fraction": round(frac, 3)}
        if base is None and float(np.min(hi - lo)) < min_attributable_mm:
            row.update(verdict="NOT_CHECKED", message=(f"helper {h['id']}: its box is thinner than {min_attributable_mm} mm, "
                       "so its material cannot be told apart from the body's without a shell-only baseline slice"))
        elif frac >= min_fill_fraction and added >= min_added_mm3:
            row.update(verdict="PASS", message=f"helper {h['id']}: added {added:.1f} mm3 of solid infill ({100 * frac:.0f} % of its box)")
        else:
            row.update(verdict="FAIL", message=(f"helper {h['id']}: added only {added:.3f} mm3 of solid infill "
                       f"({100 * frac:.1f} % of its box; needs {100 * min_fill_fraction:.0f} % and {min_added_mm3} mm3); the slicer dropped it "
                       "or it lies outside the body"))
        rows.append(row)
    cr = credit(tp)
    return {"schema": "fdmgen/massing-slice-evidence@0.1", "tier": "S", "level": "T",
            "project_3mf_sha256": report["project_3mf_sha256"], "plan": report["plan"],
            "baseline": "shell-only slice" if base is not None else None,
            "slicer": slicer, "baseline_slicer": base_ctx,
            "baseline_context_mismatch": mismatch,
            "placement_shift_xy_mm": np.round(shift, 4).tolist(),
            "credited_mm3": round(cr["structurally_credited_extrusion_volume_mm3"], 1),
            "min_fill_fraction": min_fill_fraction, "min_added_mm3": min_added_mm3, "helpers": rows,
            "establishes": "How much solid infill each helper added in its box in the real slice (MOD-001 T).",
            "does_not_establish": "Bond continuity with the shell, or strength; physical testing is separate."}


_AXIS_PLANE = {"Z": ((0, 1), "center_xy_mm"), "X": ((1, 2), "center_yz_mm"), "Y": ((0, 2), "center_xz_mm")}


def _interface_radius(i: dict) -> tuple[float | None, str]:
    if i.get("type") == "rod_seat" and i.get("seat_radius_mm"):
        return float(max(i["seat_radius_mm"])), "rod seat modelled as a cylinder of its largest seat radius"
    if i.get("type") == "screw_clearance" and i.get("d_mm"):
        return float(i["d_mm"]) / 2, "screw bore modelled as a cylinder of its clearance diameter; washer and driver access are not modelled"
    return None, f"no keep-clear geometry for interface type {i.get('type')!r}"


def check_keep_clear(helpers, interfaces) -> list[CheckResult]:
    """One result per (helper, requested interface): the helper box must stay outside the interface's cylinder
    (radius + the helper's clearance_mm) around its axis. Exact for an axis-aligned box and an axis along X/Y/Z;
    interfaces without usable geometry are NOT_CHECKED, never dropped."""
    by_id = {i["id"]: i for i in (interfaces or [])}
    out = []
    for h in helpers:
        clearance = float(h.clearance_mm or 0.0)
        given = h.clearance_mm is not None
        note = "" if given else " No clearance was requested, so 0 mm is used."
        for iid in h.interface_ids:
            base = {"helper_id": h.id, "interface_id": iid, "clearance_mm": clearance, "clearance_given": given}
            i = by_id.get(iid)
            if i is None:
                out.append(CheckResult("KEEP-CLEAR", "M", Verdict.NOT_CHECKED,
                                       f"KEEP-CLEAR NOT_CHECKED: helper {h.id} names interface {iid}, which the table does not define.",
                                       True, base))
                continue
            r, model = _interface_radius(i)
            plane = _AXIS_PLANE.get(str(i.get("axis", "")).upper())
            if r is None or plane is None or plane[1] not in i:
                out.append(CheckResult("KEEP-CLEAR", "M", Verdict.NOT_CHECKED,
                                       f"KEEP-CLEAR NOT_CHECKED: helper {h.id} vs {iid}: {model if r is None else 'axis or centre missing'}.",
                                       True, {**base, "model": model}))
                continue
            (a, b), key = plane
            p = np.asarray(i[key], float)
            lo = (h.center_mm - h.size_mm / 2)[[a, b]]
            hi = (h.center_mm + h.size_mm / 2)[[a, b]]
            d = float(np.linalg.norm(np.maximum(0.0, np.maximum(lo - p, p - hi))))
            need = r + clearance
            m = {**base, "model": model, "distance_mm": round(d, 3), "required_mm": round(need, 3)}
            if d < need - 1e-9:
                out.append(CheckResult("KEEP-CLEAR", "M", Verdict.FAIL,
                                       f"KEEP-CLEAR FAIL: helper {h.id} comes within {d:.2f} mm of the {iid} axis; keeping "
                                       f"{iid} clear needs {need:.2f} mm ({r:.2f} mm {model.split(' modelled')[0]} + "
                                       f"{clearance:.2f} mm clearance).{note}", True, m,
                                       [f"move or shrink helper {h.id} by at least {need - d:.2f} mm away from {iid}"], "",
                                       "Printed fit and assembly access."))
            else:
                out.append(CheckResult("KEEP-CLEAR", "M", Verdict.PASS,
                                       f"KEEP-CLEAR PASS (modelled): helper {h.id} stays {d:.2f} mm from the {iid} axis "
                                       f"(needs {need:.2f} mm; {model}).{note}", True, m, [],
                                       "The helper box stays outside the modelled interface cylinder plus clearance.",
                                       "Printed fit, washer/driver access, or anything the cylinder model leaves out."))
    return out
