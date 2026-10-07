"""Stress-seeded helper proposals: a machine-made fdmgen.massing-plan.v0.3 draft for review (toward PLAN P2).

The seed is the inter-layer index F_L of a stress field in the chosen pose: clusters of the highest-F_L
cells become candidate helper boxes in the design frame. This is a proposal, not an optimum, and the
stress it reads is whatever the field is (for the R1 export: a FULL SOLID envelope, not the printed
shell and helpers). Clusters next to a modelled restraint are rejected and listed, because a clamped bore
or a roller face concentrates stress by modelling choice. Every helper names every declared interface
with an explicit clearance, so KEEP-CLEAR always runs on it; keep-outs and MOD-001 are checked
before a helper is kept. Nothing is dropped silently: rejected clusters and the reason are in
proposal.rejected, and "no viable helpers" is a stated status.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..catalog.checks.keepout import check_boxes
from ..orient.failure import interlayer_index

SCHEMA = "fdmgen.massing-plan.v0.3"
LABEL = ("stress-seeded proposal from the field named in proposal.stress; for the R1 export that is a full-solid "
         "envelope solve, not the printed shell and helpers; not an optimum; review before use")


def _axis_distance(lo, hi, iface) -> float | None:
    plane = {"Z": ((0, 1), "center_xy_mm"), "X": ((1, 2), "center_yz_mm")}.get(str(iface.get("axis", "")).upper())
    if plane is None or plane[1] not in iface:
        return None
    (a, b), key = plane
    p = np.asarray(iface[key], float)
    return float(np.linalg.norm(np.maximum(0.0, np.maximum(lo[[a, b]] - p, p - hi[[a, b]]))))


def _iface_radius(iface) -> float:
    if iface.get("seat_radius_mm"):
        return float(max(iface["seat_radius_mm"]))
    return float(iface.get("d_mm", 0.0)) / 2


def seed_draft(table: dict, table_bytes: bytes, body_vertices, stress, stress_bytes: bytes, card, *, pose_id=None,
               walls=4, skin_mm=1.6, quantile=0.97, min_cells=8, restraint_ids=(), wall_plane_x=0.0,
               restraint_margin_mm=4.8, clearance_mm=0.5, min_edge_mm=0.84, max_helpers=6,
               sensitivity_margins_mm=(0.0, 4.8, 9.6, 16.0)) -> dict:
    """Build the draft dict. `stress` is a fdmgen.orient.StressField in the design (installed) frame."""
    from scipy import ndimage as ndi
    cand = next(c for c in table["candidates"] if c["id"] == pose_id) if pose_id else table["candidates"][0]
    st = card.strength_corners()["design"]
    fl, _, _ = interlayer_index(stress.stress, cand["build_dir_design"], st["Z_t"], st["S_il"])
    z = stress.meta or {}
    idx = np.asarray(stress.cell_indices)
    cell = np.cbrt(np.median(stress.volume))
    thr = float(np.quantile(fl, quantile))
    grid = np.zeros(idx.max(axis=0) + 1, bool)
    grid[tuple(idx[fl >= thr].T)] = True
    lab, n = ndi.label(grid, structure=np.ones((3, 3, 3), bool))
    cell_lab = lab[tuple(idx.T)]
    bv = np.asarray(body_vertices, float)
    blo, bhi = bv.min(axis=0), bv.max(axis=0)
    ifs = {i["id"]: i for i in table.get("interfaces", [])}
    clusters = []
    for k in range(1, n + 1):
        sel = cell_lab == k
        if sel.sum() == 0:
            continue
        c = stress.centres[sel]
        lo = np.maximum(c.min(axis=0) - cell / 2, blo)
        hi = np.minimum(c.max(axis=0) + cell / 2, bhi)
        clusters.append({"cluster": k, "cells": int(sel.sum()), "F_L_max": float(fl[sel].max()),
                         "F_L_mean": float(fl[sel].mean()), "lo": lo, "hi": hi})
    clusters.sort(key=lambda r: -r["F_L_max"] * r["cells"])

    def select(margin):
        return _select(clusters, margin, ifs, restraint_ids, wall_plane_x, min_cells, min_edge_mm,
                       clearance_mm, max_helpers, table, blo, bhi)
    accepted, rejected = select(restraint_margin_mm)
    sensitivity = [{"restraint_margin_mm": m, "accepted_clusters": [a["cluster"] for a in select(m)[0]]}
                   for m in sensitivity_margins_mm]
    return _draft(table, table_bytes, cand, st, stress, stress_bytes, card, fl, thr, grid, cell, z, walls, skin_mm,
                  quantile, min_cells, restraint_ids, wall_plane_x, restraint_margin_mm, clearance_mm,
                  accepted, rejected, sensitivity)


def _select(clusters, restraint_margin_mm, ifs, restraint_ids, wall_plane_x, min_cells, min_edge_mm,
            clearance_mm, max_helpers, table, blo, bhi):
    accepted, rejected = [], []

    def reject(cl, reason):
        rejected.append({"cluster": cl["cluster"], "cells": cl["cells"], "F_L_max": round(cl["F_L_max"], 5),
                         "center_mm": ((cl["lo"] + cl["hi"]) / 2).round(2).tolist(),
                         "size_mm": (cl["hi"] - cl["lo"]).round(2).tolist(), "reason": reason})
    for cl in clusters:
        lo, hi = cl["lo"], cl["hi"]
        if cl["cells"] < min_cells:
            reject(cl, f"fewer than {min_cells} cells")
            continue
        near_r = [(rid, d - _iface_radius(ifs[rid])) for rid in restraint_ids if rid in ifs
                  for d in [_axis_distance(lo, hi, ifs[rid])] if d is not None]
        near_r.append(("wall_plane", float(lo[0] - wall_plane_x)))
        rid, rd = min(near_r, key=lambda x: x[1])
        if rd < restraint_margin_mm:
            reject(cl, f"restraint_adjacent: {rd:.1f} mm from {rid} (modelled restraint; stress there is partly a modelling artefact)")
            continue
        if np.min(hi - lo) < min_edge_mm:
            reject(cl, f"box thinner than {min_edge_mm} mm after clipping to the body")
            continue
        refs = sorted(ifs)                         # every interface, so KEEP-CLEAR runs explicitly on each
        blocked = [i for i in refs for d in [_axis_distance(lo, hi, ifs[i])]
                   if d is not None and d < _iface_radius(ifs[i]) + clearance_mm]
        if blocked:
            reject(cl, f"would not keep {', '.join(blocked)} clear by {clearance_mm} mm")
            continue
        ko = check_boxes({"x": (lo, hi)}, table.get("keep_outs"), blo, bhi, interfaces=list(ifs.values()))
        if any(r.verdict.value == "FAIL" for r in ko):
            reject(cl, "enters a keep-out: " + ", ".join(r.metrics["keep_out_id"] for r in ko if r.verdict.value == "FAIL"))
            continue
        clash = next((a for a in accepted if np.all(np.minimum(a["hi"], hi) > np.maximum(a["lo"], lo) - min_edge_mm)), None)
        if clash is not None:
            reject(cl, f"overlaps or sits within {min_edge_mm} mm of an accepted helper ({clash['id']}); MOD-001")
            continue
        if len(accepted) >= max_helpers:
            reject(cl, f"beyond the first {max_helpers} helpers")
            continue
        accepted.append({**cl, "id": f"seed-{len(accepted) + 1:02d}", "refs": refs, "nearest_restraint": [rid, round(rd, 2)]})
    return accepted, rejected


def _draft(table, table_bytes, cand, st, stress, stress_bytes, card, fl, thr, grid, cell, z, walls, skin_mm, quantile,
           min_cells, restraint_ids, wall_plane_x, restraint_margin_mm, clearance_mm, accepted, rejected,
           sensitivity):
    t_sha = hashlib.sha256(table_bytes).hexdigest()
    s_sha = hashlib.sha256(stress_bytes).hexdigest()
    scope = (f"full-solid stress field sha256 {s_sha[:12]} ({z.get('model', 'model not recorded')}); candidate, not "
             "load-path evidence; not an optimum")
    regions = [{"id": a["id"], "name": f"Stress-seeded helper {a['id'][-2:]}",
                "location": f"design-frame box {((a['lo'] + a['hi']) / 2).round(1).tolist()} mm; nearest restraint "
                            f"{a['nearest_restraint'][0]} at {a['nearest_restraint'][1]} mm",
                "purpose": (f"candidate stiffening of a high-F_L cluster (F_L max {a['F_L_max']:.4f}, {a['cells']} cells) "
                            f"in this pose; seeded from {scope}"),
                "keep_clear": {"interface_ids": a["refs"], "keep_out_ids": [k["id"] for k in table.get("keep_outs", [])],
                               "clearance_mm": clearance_mm,
                               "note": f"machine-set {clearance_mm} mm clearance to every declared interface"},
                "geometry": {"type": "box", "frame": "design", "center_mm": ((a["lo"] + a["hi"]) / 2).round(3).tolist(),
                             "size_mm": (a["hi"] - a["lo"]).round(3).tolist()},
                "geometry_status": "sketch"} for a in accepted]
    orientation = {**cand, "designer_decision": {"choice": "selected_for_planning", "candidate_id": cand["id"],
                                                 "table_sha256": t_sha, "rank_at_decision": cand.get("rank"),
                                                 "decided_by_role": "fdmgen massing-seed (machine proposal)",
                                                 "rationale": f"machine proposal for review, seeded from {scope}. {LABEL}"}}
    return {
        "schema": SCHEMA, "status": "draft_requires_verification",
        "source": {"orientation_table_sha256": t_sha, "orientation_schema": table["schema"], "problem": table["problem"],
                   "mesh": table["mesh"]},
        "orientation": orientation,
        "massing": {"body": "fixed", "walls": int(walls), "skin_mm": float(skin_mm), "helper_infill_percent": 100,
                    "sparse_infill_structural_credit": False, "shell_only": not regions, "helper_regions": regions},
        "outstanding_checks": ["Review every seeded helper; the seed is not an optimum",
                               "Export with fdmgen massing and resolve every FAIL / NOT_CHECKED",
                               "Slice and read back with fdmgen massing-evidence",
                               "Shell/helper stress, strength and physical testing remain separate"],
        "proposal": {
            "generator": "fdmgen.massing.seed", "label": LABEL,
            "status": "helpers_proposed" if regions else "no_viable_helpers",
            "stress": {"sha256": s_sha, "frame": stress.frame, "cells": len(fl),
                       "cell_mm": round(float(cell), 4), "grid": list(grid.shape),
                       **{k: z[k] for k in ("model", "receipt", "receipt_sha256", "load_total_N", "restraint_model",
                                            "material", "sampling") if k in z}},
            "card": {"id": card.id, "corner": "design", "Z_t_mpa": st["Z_t"], "S_il_mpa": st["S_il"]},
            "pose": {"id": cand["id"], "build_dir_design": cand["build_dir_design"]},
            "seed": {"quantile": quantile, "F_L_threshold": round(thr, 5), "min_cells": min_cells,
                     "restraint_ids": list(restraint_ids), "wall_plane_x_mm": wall_plane_x,
                     "restraint_margin_mm": restraint_margin_mm, "interface_refs": "all", "clearance_mm": clearance_mm},
            "accepted": [{"id": a["id"], "cluster": a["cluster"], "cells": a["cells"], "F_L_max": round(a["F_L_max"], 5),
                          "nearest_restraint": a["nearest_restraint"]} for a in accepted],
            "rejected": rejected,
            "sensitivity": sensitivity,
        },
    }


def load_stress_for_seed(path):
    """StressField plus the raw bytes and cell indices the seed needs."""
    from ..orient.failure import StressField
    sf = StressField.load(path)
    z = np.load(Path(path), allow_pickle=False)
    if "cell_indices" not in z.files:
        raise ValueError(f"{path}: the seed needs cell_indices (stress export schema v1)")
    sf.cell_indices = np.asarray(z["cell_indices"], int)
    return sf, Path(path).read_bytes()


def dumps(draft: dict) -> bytes:
    return (json.dumps(draft, indent=1) + "\n").encode("utf-8")
