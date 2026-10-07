"""Ranked orientation table, schema `fdmgen/orientation-table@0.1` (PLAN P1, D8, D16).

Every column is {value, unit, rule, level, verdict, provisional, fidelity} so a reader (or a UI) can
show what each number does and does not establish. Ranking: feasible first (BED-001 fit, BED-002
contact and stability), then OVH-001 failing area, then F_L p99 when a stress field is given, then
height. The Pareto front is over (OVH-001 failing area, F_L p99) among feasible poses.
Never a bare PASS: a pose that is ranked first is "best of the checked columns", nothing more.
"""
from __future__ import annotations

from ..catalog import load_rules
from .failure import StressField, prescreen
from .interfaces import interface_roofs
from .poses import candidate_poses
from .printability import mesh_volume_centroid, pose_columns

SCHEMA = "fdmgen/orientation-table@0.1"


def _param_values(rule) -> dict:
    return {k: v["value"] for k, v in rule.parameters.items()}


def _col(value, unit, rule, level, verdict=None, provisional=True, fidelity="geometry"):
    return {"value": value, "unit": unit, "rule": rule, "level": level, "verdict": verdict,
            "provisional": provisional, "fidelity": fidelity}


def build_table(vertices, faces, *, card=None, stress: StressField | None = None, sf: float = 4.0,
                sphere: int = 0, user=(), voxel: bool = False, provenance: dict | None = None,
                interfaces=None) -> dict:
    rules = load_rules()
    bed = _param_values(rules["BED-001"])
    stab = _param_values(rules["BED-002"])
    alpha = rules["OVH-001"].parameters["alpha_min_deg"]["value"]
    max_span = rules["BRG-001"].parameters["max_span_external_mm"]["value"]
    _, centroid = mesh_volume_centroid(vertices, faces)
    poses = candidate_poses(vertices, sphere=sphere, user=user)
    fl = fl_v = None
    if stress is not None and card is not None:
        corners = card.strength_corners()
        st = corners["design"]
        fl = prescreen(stress, [p.d for p in poses], st["Z_t"], st["S_il"], st["X_t"])
        vr = corners["vendor_ratio"]                       # the other corner (PLAN D10: report both)
        fl_v = prescreen(stress, [p.d for p in poses], vr["Z_t"], vr["S_il"][0], vr["X_t"])
    rows = []
    for i, p in enumerate(poses):
        c, place = pose_columns(vertices, faces, p.d, bed, stab, alpha_min_deg=alpha, centroid=centroid,
                                voxel=voxel, max_bridge_mm=max_span)
        cols = {
            "ovh_fail_mm2": _col(c["ovh_fail_mm2"], "mm2", "OVH-001", "M", c["ovh_verdict"]),
            "bridge_candidate_mm2": _col(c["bridge_candidate_mm2"], "mm2", "BRG-001", "M", None),
            "contact_mm2": _col(c["contact_mm2"], "mm2", "BED-002", "M", "PASS" if c["contact_ok"] else "FAIL"),
            "com_margin_mm": _col(c["com_margin_mm"], "mm", "BED-002", "M", "PASS" if c["stable"] else "FAIL"),
            "base_min_width_mm": _col(c["base_min_width_mm"], "mm", "BED-002", "M"),
            "height_mm": _col(c["height_mm"], "mm", "BED-001", "M"),
            "fits_bed": _col(c["fits_bed"], "1", "BED-001", "M", "PASS" if c["fits_bed"] else "FAIL",
                             fidelity="geometry; exclusion zone not modelled"),
        }
        if voxel:
            cols["v_unsupported_mm2"] = _col(c["v_unsupported_mm2"], "mm2", "OVH-001", "V")
            cols["brg_worst_span_mm"] = _col(c["brg_worst_span_mm"], "mm", "BRG-001", "V", c["brg_verdict"],
                                             fidelity="D5 grid, straight-line spans")
        else:
            cols["v_unsupported_mm2"] = _col(None, "mm2", "OVH-001", "V", "NOT_CHECKED")
            cols["brg_worst_span_mm"] = _col(None, "mm", "BRG-001", "V", "NOT_CHECKED")
        if fl is not None:
            fid = "FE prescreen: " + str((stress.meta or {}).get("model", "stress field as supplied"))
            ok = fl[i]["F_L_max"] <= 1.0 / sf
            cols["F_L_max"] = _col(fl[i]["F_L_max"], "1", "STR-001", "FE", "PASS" if ok else "FAIL", True, fid)
            cols["F_L_p99"] = _col(fl[i]["F_L_p99"], "1", "STR-001", "FE", None, True, fid)
            cols["F_L_max_at_mm"] = _col(fl[i]["F_L_max_at_mm"], "mm", "STR-001", "FE", None, True, fid)
            cols["F_L_max_vendor_corner"] = _col(fl_v[i]["F_L_max"], "1", "STR-001", "FE",
                                                 "PASS" if fl_v[i]["F_L_max"] <= 1.0 / sf else "FAIL", True,
                                                 fid + "; vendor-ratio Z_t corner (less conservative)")
        else:
            cols["F_L_max"] = _col(None, "1", "STR-001", "FE", "NOT_CHECKED", True, "no stress field supplied")
            cols["F_L_p99"] = _col(None, "1", "STR-001", "FE", "NOT_CHECKED", True, "no stress field supplied")
        roofs = interface_roofs(interfaces, p.d)
        cols["interface_roofs"] = _col(roofs["interfaces"], "1", "HOLE-001", "M", roofs["verdict"],
                                       fidelity=roofs["message"])
        reasons = []
        if not c["fits_bed"]:
            reasons.append(f"does not fit the bed: best spin {c['best_spin_deg']:.0f} deg gives "
                           f"{c['best_bbox_mm'][0]:.0f} x {c['best_bbox_mm'][1]:.0f} mm, height {c['height_mm']:.0f} mm")
        if not c["contact_ok"]:
            reasons.append(f"bed contact {c['contact_mm2']:.0f} mm2 is below {stab['contact_min_mm2']} mm2 or "
                           f"{100 * stab['contact_min_fraction']:.0f} % of the footprint")
        if not c["stable"]:
            reasons.append("may topple: centre of mass margin or height-to-base ratio outside BED-002")
        rows.append({"id": p.id, "kind": p.kind, "build_dir_design": [round(float(x), 9) for x in p.d],
                     "spin_deg": c["best_spin_deg"], "R_design_to_print": place["R"].round(12).tolist(),
                     "t_mm": place["t"].round(6).tolist(), "feasible": not reasons, "reasons": reasons,
                     "pareto": False, "rank": None, "designer_decision": None, "meta": p.meta, "columns": cols})
    feas = [r for r in rows if r["feasible"]]

    def key(r):
        fl99 = r["columns"]["F_L_p99"]["value"]
        return (r["columns"]["ovh_fail_mm2"]["value"], fl99 if fl99 is not None else 0.0,
                r["columns"]["height_mm"]["value"])
    for k, r in enumerate(sorted(feas, key=key)):
        r["rank"] = k
    for r in feas:
        a = (r["columns"]["ovh_fail_mm2"]["value"], r["columns"]["F_L_p99"]["value"] or 0.0)
        r["pareto"] = not any((o["columns"]["ovh_fail_mm2"]["value"] <= a[0] and (o["columns"]["F_L_p99"]["value"] or 0.0) <= a[1]
                               and (o["columns"]["ovh_fail_mm2"]["value"], o["columns"]["F_L_p99"]["value"] or 0.0) != a)
                              for o in feas)
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 0))
    return {
        "schema": SCHEMA, **(provenance or {}),
        "pose_convention": ("print = R_design_to_print @ design + t_mm. R is the complete rotation: the lift of "
                            "build_dir_design to +Z, then spin_deg about +Z (counter-clockwise seen from above). t puts "
                            "the lowest point on the bed (z = 0) and centres the footprint's bounding box on the bed "
                            "centre. Bed coordinates: origin at a bed corner, X and Y along the bed edges."),
        "bed": {"x_mm": bed["bed_x_mm"], "y_mm": bed["bed_y_mm"], "max_height_mm": bed["max_height_mm"],
                "margin_mm": bed["margin_mm"]},
        "feasible_scope": ("feasible covers BED-001 (fits the bed with margins) and BED-002 (contact, stability) only. "
                           "Every other column carries its own verdict; a feasible pose can still fail OVH-001."),
        "establishes": ("For each candidate pose: geometry-level printability (overhang area, flat ceilings, bed fit, "
                        "contact and stability) from the catalog checkers"
                        + (", and the inter-layer index F_L from the supplied stress field" if fl else "") + "."),
        "does_not_establish": ("What Orca will generate (T level) or how the part prints (P level); interface "
                               "variants such as teardrops per pose; strength beyond the supplied stress model; "
                               "the bed exclusion zone. A first rank means best of these columns only."),
        "candidates": rows,
    }
