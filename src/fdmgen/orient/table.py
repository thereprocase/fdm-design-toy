"""Ranked orientation table, schema `fdmgen/orientation-table@0.1` (PLAN P1, D8, D16).

Every column is {value, unit, rule, level, verdict, provisional, fidelity} so a reader (or a UI) can
show what each number does and does not establish. Ranking: feasible first (BED-001 fit, BED-002
contact and stability), then OVH-001 failing area, then F_L p99 when a stress field is given, then
height. The Pareto front is over (OVH-001 failing area, F_L p99) among feasible poses.
Never a bare PASS: a pose that is ranked first is "best of the checked columns", nothing more.
"""
from __future__ import annotations

import numpy as np

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
                interfaces=None, keep_outs=None) -> dict:
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
        "interfaces": [{k: i[k] for k in ("id", "type", "axis", "role", "support", "roof_variant", "center_xy_mm",
                                          "center_yz_mm", "d_mm", "seat_radius_mm") if k in i}
                       for i in (interfaces or [])],
        **({"keep_outs": [dict(ko) for ko in keep_outs]}
           if keep_outs is not None else {}),
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


def add_toolpath_columns(table: dict, vertices, gcode_by_id: dict) -> dict:
    """Attach T-level columns from real slices of individual poses (OVH-001 T and credited material).

    gcode_by_id maps candidate id -> G-code path of that pose sliced as exported by --export-poses.
    The object's placement is measured against the pose's own footprint; a mismatch raises.
    """
    import re
    from pathlib import Path

    from ..catalog.checks.proc import settings_from_gcode
    from ..catalog.checks.toolpath import locate
    from ..gcode import credit, extruder_offset, read_gcode

    V0 = np.asarray(vertices, float)
    for c in table["candidates"]:
        path = gcode_by_id.get(c["id"])
        if path is None:
            continue
        text = Path(path).read_text(encoding="utf-8")
        tp = read_gcode(text)
        cfg = settings_from_gcode(text)
        gen = re.search(r"^; generated by (\S+) (\S+)", text, re.MULTILINE)
        V = V0 @ np.asarray(c["R_design_to_print"]).T + np.asarray(c["t_mm"])
        shift = locate(tp, V.min(axis=0)[:2], V.max(axis=0)[:2], extruder_offset(text))
        cr = credit(tp)
        fid = (f"{gen.group(1) if gen else 'slicer'} {gen.group(2) if gen else ''}: support {cfg.get('enable_support')}, "
               f"threshold {cfg.get('support_threshold_angle')}, type {cfg.get('support_type')}, "
               f"profile {cfg.get('print_settings_id')} / {cfg.get('filament_settings_id')}; placement shift "
               f"{np.round(shift, 3).tolist()} mm")
        n = cr["support_segments"]
        c["columns"]["t_support_segments"] = _col(n, "count", "OVH-001", "T", "PASS" if n == 0 else "FAIL", False, fid)
        c["columns"]["t_support_volume_mm3"] = _col(cr["support_and_aux_volume_mm3"], "mm3", "OVH-001", "T", None, False, fid)
        c["columns"]["t_credited_mm3"] = _col(cr["structurally_credited_extrusion_volume_mm3"], "mm3", "STR-001", "T",
                                              None, False, fid + "; thick bridges and support excluded")
    return table


SLICE_KINDS = ("shell-only", "project")
SHELL_KINDS = SLICE_KINDS


def _root_table_sha(table: dict, table_sha256: str) -> str:
    """Receipts are measured against the pinned table; an enriched table names it in enriched.from_table_sha256."""
    return (table.get("enriched") or {}).get("from_table_sha256") or table_sha256


def _pair(table: dict, root_sha: str, by_id: dict, rec: dict, rec_sha: str, kind: str, schema: str,
          rule: str, column: str) -> dict:
    """The candidate a receipt belongs to, or ValueError: never relabel a receipt to another table or pose."""
    if rec.get("schema") != schema:
        raise ValueError(f"receipt {rec_sha[:12]}: schema {rec.get('schema')!r}, need {schema}")
    if kind not in SLICE_KINDS:
        raise ValueError(f"receipt {rec_sha[:12]}: slice kind {kind!r}, use one of {SLICE_KINDS}")
    if not all(k in rec for k in ("table", "mesh", "pose")):
        raise ValueError(f"receipt {rec_sha[:12]} records no table, mesh and pose, so it cannot be paired with a pose")
    if rec["table"]["sha256"] != root_sha:
        raise ValueError(f"receipt {rec_sha[:12]} was measured against table {rec['table']['sha256'][:12]}, "
                         f"not this one ({root_sha[:12]})")
    if rec["mesh"]["sha256"] != table["mesh"]["sha256"]:
        raise ValueError(f"receipt {rec_sha[:12]} measured mesh {rec['mesh']['sha256'][:12]}, "
                         f"the table's body is {table['mesh']['sha256'][:12]}")
    pose = rec["pose"]["id"]
    c = by_id.get(pose)
    if c is None:
        raise ValueError(f"receipt {rec_sha[:12]}: pose {pose!r} is not in the table")
    if rec["pose"]["R_design_to_print"] != c["R_design_to_print"] or rec["pose"]["t_mm"] != c["t_mm"]:
        raise ValueError(f"receipt {rec_sha[:12]}: pose {pose} R/t differ from the table's")
    if column in c["columns"]:
        raise ValueError(f"two receipts for pose {pose}; give one per pose")
    res = rec["result"]
    if (res.get("rule"), res.get("level")) != (rule, "T"):
        raise ValueError(f"receipt {rec_sha[:12]}: result is {res.get('rule')} {res.get('level')}, not {rule} T")
    return c


def _enrich(out: dict, root_sha: str, columns: list[str], key: str, used: list[dict], does_not: str) -> None:
    prev = out.get("enriched")
    if prev is None:
        out["enriched"] = {"from_table_sha256": root_sha, "columns_added": columns, key: used, "does_not_establish": does_not}
        return
    prev["columns_added"] = prev["columns_added"] + [c for c in columns if c not in prev["columns_added"]]
    prev[key] = used


def _slice_fidelity(kind, g):
    return (f"{kind} slice {g['gcode_sha256'][:12]} ({g.get('generator')} {g.get('version')}, "
            f"{g.get('print_settings_id')} / {g.get('filament_settings_id')})")


def add_shell_columns(table: dict, table_sha256: str, receipts: list[tuple[dict, str, str]]) -> dict:
    """A new table with a T-level SHELL-001 column from shell-check@0.2 receipts; the input is not modified.

    receipts: (receipt dict, receipt sha256, slice kind "shell-only" | "project"). A receipt is accepted only if
    it was measured against the root pinned table (this table, or the one an enriched table names), its mesh
    and this pose (R and t equal), so a receipt is never relabelled. Poses without a receipt get no column.
    """
    import copy

    if table.get("mesh", {}).get("sha256") is None:
        raise ValueError("the table records no mesh sha256, so receipts cannot be matched to its body")
    out = copy.deepcopy(table)
    root = _root_table_sha(table, table_sha256)
    by_id = {c["id"]: c for c in out["candidates"]}
    used = []
    for rec, rec_sha, kind in receipts:
        c = _pair(table, root, by_id, rec, rec_sha, kind, "fdmgen/shell-check@0.2", "SHELL-001", "t_shell_thin_fraction")
        res, g, m = rec["result"], rec["gcode"], rec["method"]
        frac = res["metrics"]["thin_fraction"]
        if not (isinstance(frac, (int, float)) and 0.0 <= frac <= 1.0):
            raise ValueError(f"receipt {rec_sha[:12]}: thin_fraction {frac!r} is not a fraction in 0..1")
        fid = (f"{_slice_fidelity(kind, g)}; raster {rec['grid']['cell_mm']} mm, "
               f"caps {m['deposit']['caps']}, {m['surface_samples']} surface samples, seed {m['seed']}, "
               f"limit {m['thin_fraction_limit']}")
        col = _col(frac, "fraction", "SHELL-001", "T", res["verdict"], res["provisional"], fid)
        col["receipt"] = {"sha256": rec_sha, "slice_kind": kind, "gcode_sha256": g["gcode_sha256"],
                          "source_sha256": rec["source_sha256"]}
        # coverage: the fraction is over measured samples only, so partial coverage must travel with it
        col["coverage"] = {"samples_requested": m["surface_samples"], "measured": res["metrics"]["samples"],
                           "unmeasured": res["metrics"]["unmeasured"],
                           "clipped_outside_grid_mm3": rec["grid"]["clipped_outside_grid_mm3"]}
        c["columns"]["t_shell_thin_fraction"] = col
        used.append({"pose": c["id"], "receipt_sha256": rec_sha, "slice_kind": kind})
    _enrich(out, root, ["t_shell_thin_fraction"], "shell_receipts", used,
            "anything about poses without a receipt, or about a different slice of the same pose; "
            "the column is one slice's measured shell")
    return out


def add_bridge_columns(table: dict, table_sha256: str, receipts: list[tuple[dict, str, str]]) -> dict:
    """A new table with T-level BRG-001 columns (longest external and internal bridge span) from bridge-check@0.2
    receipts bound to a pose; same pairing rules as add_shell_columns. Each column has its own verdict against
    its own limit; the receipt's overall verdict is kept in the receipt block."""
    import copy
    import math

    if table.get("mesh", {}).get("sha256") is None:
        raise ValueError("the table records no mesh sha256, so receipts cannot be matched to its body")
    out = copy.deepcopy(table)
    root = _root_table_sha(table, table_sha256)
    by_id = {c["id"]: c for c in out["candidates"]}
    used = []
    names = ("t_bridge_span_external_mm", "t_bridge_span_internal_mm")
    for rec, rec_sha, kind in receipts:
        c = _pair(table, root, by_id, rec, rec_sha, kind, "fdmgen/bridge-check@0.2", "BRG-001", names[0])
        res, g, m = rec["result"], rec["gcode"], rec["method"]
        mt = res["metrics"]
        fid = f"{_slice_fidelity(kind, g)}; layer-below raster {m['cell_mm']} mm, caps {m['caps']}, support density {m['support_density']}"
        cover = {k: mt[k] for k in ("bridge_roads", "external_roads", "internal_roads", "max_cantilever_mm",
                                    "bridge_layers_z_mm")}
        cover["cell_mm"] = m["cell_mm"]
        for name, key, lim in ((names[0], "max_span_external_mm", m["max_span_external_mm"]),
                               (names[1], "max_span_internal_mm", m["max_span_internal_mm"])):
            v = mt[key]
            if not (isinstance(v, (int, float)) and math.isfinite(v) and v >= 0):
                raise ValueError(f"receipt {rec_sha[:12]}: {key} {v!r} is not a non-negative length")
            col = _col(v, "mm", "BRG-001", "T", "FAIL" if v > lim else "PASS", res["provisional"], fid)
            col["limit_mm"] = lim
            col["receipt"] = {"sha256": rec_sha, "slice_kind": kind, "gcode_sha256": g["gcode_sha256"],
                              "overall_verdict": res["verdict"], "source_sha256": rec["source_sha256"]}
            col["coverage"] = cover
            c["columns"][name] = col
        used.append({"pose": c["id"], "receipt_sha256": rec_sha, "slice_kind": kind})
    _enrich(out, root, list(names), "bridge_receipts", used,
            "anything about poses without a receipt, or about a different slice of the same pose; "
            "the columns are one slice's measured spans")
    return out
