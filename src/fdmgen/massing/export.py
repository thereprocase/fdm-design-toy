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

HELPER_SETTINGS = {"sparse_infill_density": "100%", "sparse_infill_pattern": "rectilinear"}
_BOX_FACES = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                       [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])


def load_capabilities(path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _box_faces(v):
    tri = v[_BOX_FACES]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()
    return _BOX_FACES if vol > 0 else _BOX_FACES[:, ::-1]


def check_helpers(helpers, body_vertices=None, body_faces=None, *, gap_min_mm=None, samples=6) -> list[CheckResult]:
    """MOD-001 (M) on design-frame helper boxes: size, pairwise separation or overlap, and bonding to the body."""
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
        import trimesh
        body = trimesh.Trimesh(body_vertices, body_faces, process=False)
        g = (np.arange(samples) + 0.5) / samples - 0.5
        grid = np.array(np.meshgrid(g, g, g, indexing="ij")).reshape(3, -1).T
        unbonded, fractions = [], {}
        for h in helpers:
            frac = float(body.contains(h.center_mm + grid * h.size_mm).mean())
            fractions[h.id] = round(frac, 3)
            if frac == 0.0:
                unbonded.append(h.id)
        if unbonded:
            out.append(CheckResult("MOD-001", "M", Verdict.FAIL,
                                   f"MOD-001 FAIL: helper(s) {', '.join(unbonded)} do not reach into the body; a modifier "
                                   "only acts inside the body, so these would print nothing.", True,
                                   {"inside_fraction": fractions}, ["move the helper into the body"]))
        else:
            out.append(CheckResult("MOD-001", "M", Verdict.PASS,
                                   f"MOD-001 bonding: every helper reaches into the body (sampled inside fractions {fractions}).",
                                   True, {"inside_fraction": fractions}))
    if not out:
        out.append(CheckResult("MOD-001", "M", Verdict.PASS, f"MOD-001 PASS: helper sizes and spacing respect {d:.2f} mm.", True))
    return out


def export_plan(plan, body_vertices, body_faces, template: bytes, capabilities: dict, *, layer_height_mm=0.2,
                helper_settings=None) -> tuple[bytes, dict]:
    """Orca 3MF bytes and a report for a validated plan; raises ValueError on a refused setting."""
    settings = dict(helper_settings or HELPER_SETTINGS)
    honoured = {s["key"] for s in capabilities["settings"] if s["status"] == "honoured"}
    ignored = {s["key"] for s in capabilities["settings"] if s["status"] == "ignored"}
    refused = {k: ("ignored by the slicer" if k in ignored else "not measured") for k in settings if k not in honoured}
    if refused:
        raise ValueError("these per-helper settings cannot be used: " + ", ".join(f"{k} ({why})" for k, why in refused.items())
                         + "; see the capability file for what this slicer honours on a modifier")
    t_sha = hashlib.sha256(template).hexdigest()
    ctx_match = capabilities["context"].get("template_3mf_sha256") == t_sha
    skin_layers = int(np.ceil(plan.skin_mm / layer_height_mm - 1e-9))
    object_settings = {"wall_loops": int(plan.walls), "top_shell_layers": skin_layers, "bottom_shell_layers": skin_layers,
                       "top_shell_thickness": 0, "bottom_shell_thickness": 0, "sparse_infill_density": "0%"}
    parts = [Part("BODY print", plan.to_print(body_vertices), np.asarray(body_faces))]
    for h in ([] if plan.shell_only else plan.helpers):
        v = plan.to_print(h.corners_design_mm())
        parts.append(Part(f"{h.id} MODIFIER 100%", v, _box_faces(v), "modifier_part", settings))
    data = write_project(template, parts, object_name=f"{plan.problem} {plan.candidate_id} massing",
                         object_settings=object_settings)
    checks = [] if plan.shell_only else check_helpers(plan.helpers, body_vertices, body_faces)
    report = {
        "schema": "fdmgen/massing-export@0.1",
        "plan": {"draft_sha256": plan.draft_sha256, "table_sha256": plan.table_sha256, "mesh_sha256": plan.mesh_sha256,
                 "problem": plan.problem, "candidate_id": plan.candidate_id},
        "template_3mf_sha256": t_sha, "project_3mf_sha256": hashlib.sha256(data).hexdigest(),
        "capability_context_matches_template": ctx_match,
        "object_settings": object_settings,
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
        report["warning"] = ("the capability file was measured with a different template profile; per-helper settings "
                             "are only known to be honoured in that context")
    return data, report
