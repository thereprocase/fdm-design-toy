"""P0-D: which settings an Orca 2.4.2 modifier volume really overrides (issue #6).

A controlled part: a 60 x 40 x 10 mm box body and one modifier box covering its +X end (the body's
outer walls pass through the modifier region). Each probe slices the same 3MF with one override on the
modifier and compares the extrusion inside the modifier region, per role, with a no-override baseline;
the rest of the body must stay unchanged. The 3MF is derived from an Orca-written template so its
project settings (printer, process, filament) are exactly the template's.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

BODY = ((-30.0, 30.0), (-20.0, 20.0), (0.0, 10.0))          # object frame relative to the body component, z on bed
MODIFIER = ((15.0, 35.0), (-25.0, 25.0), (0.0, 10.0))       # covers the +X end of the body and beyond it
NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


TAPER = ((-30.0, -0.3), (30.0, -1.2), (30.0, 1.2), (-30.0, 0.3))   # wall 0.6 -> 2.4 mm thick along X
TAPER_MODIFIER = ((0.0, 35.0), (-5.0, 5.0), (0.0, 10.0))           # covers the thick half


def _prism_mesh_xml(obj, poly_xy, z0, z1):
    """Closed prism from a convex CCW polygon in XY, extruded from z0 to z1 (outward wound)."""
    mesh = obj.find("m:mesh", NS)
    for child in list(mesh):
        mesh.remove(child)
    p = np.asarray(poly_xy, float)
    n = len(p)
    v = np.vstack([np.c_[p, np.full(n, z0)], np.c_[p, np.full(n, z1)]])
    tris = []
    for i in range(1, n - 1):
        tris += [(0, i + 1, i), (n, n + i, n + i + 1)]
    for i in range(n):
        j = (i + 1) % n
        tris += [(i, j, j + n), (i, j + n, i + n)]
    t = np.array(tris)
    vol = np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum()
    vs = ET.SubElement(mesh, f"{{{NS['m']}}}vertices")
    for x, y, z in v:
        ET.SubElement(vs, f"{{{NS['m']}}}vertex", x=f"{x:.6f}", y=f"{y:.6f}", z=f"{z:.6f}")
    ts = ET.SubElement(mesh, f"{{{NS['m']}}}triangles")
    for a, b, c in (t if vol > 0 else t[:, ::-1]):
        ET.SubElement(ts, f"{{{NS['m']}}}triangle", v1=str(a), v2=str(b), v3=str(c))


def _box_mesh_xml(obj, lo, hi):
    mesh = obj.find("m:mesh", NS)
    for child in list(mesh):
        mesh.remove(child)
    vs = ET.SubElement(mesh, f"{{{NS['m']}}}vertices")
    corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    for x, y, z in corners:
        ET.SubElement(vs, f"{{{NS['m']}}}vertex", x=f"{x:.6f}", y=f"{y:.6f}", z=f"{z:.6f}")
    ts = ET.SubElement(mesh, f"{{{NS['m']}}}triangles")
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for q in quads:
        tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    v = np.array(corners)
    t = np.array(tris)
    vol = np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum()
    for a, b, c in (t if vol > 0 else t[:, ::-1]):
        ET.SubElement(ts, f"{{{NS['m']}}}triangle", v1=str(a), v2=str(b), v3=str(c))


def _xf(s):
    return np.array([float(v) for v in s.split()]).reshape(4, 3)


def build_variant(template: bytes, overrides: dict | None = None, *, body: str = "box",
                  object_overrides: dict | None = None) -> tuple[bytes, dict]:
    """A 3MF with the probe body + one modifier carrying `overrides`; returns (bytes, geometry in plate frame).

    body = "box" (60 x 40 x 10 mm, modifier over one end) or "taper" (a 10 mm tall wall whose thickness
    grows from 0.6 to 2.4 mm, modifier over the thick half), which separates classic from Arachne walls.
    """
    zin = zipfile.ZipFile(io.BytesIO(template))
    for prefix, uri in (("", NS["m"]), ("p", "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"),
                        ("BambuStudio", "http://schemas.bambulab.com/package/2021")):
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(zin.read("3D/3dmodel.model"))
    comps = root.findall(".//m:component", NS)
    body_c, mod_c = comps[0], comps[1]
    parent = root.find(".//m:components", NS)
    keep_ids = {body_c.get("objectid"), mod_c.get("objectid")}
    for c in comps[2:]:
        parent.remove(c)
    T_body, T_mod = _xf(body_c.get("transform")), _xf(mod_c.get("transform"))
    B = _xf(root.find("m:build/m:item", NS).get("transform"))
    # body box in the body component's frame; the modifier box expressed in the modifier component's frame
    z0 = -T_body[3, 2]                                     # local z that lands on the bed
    if body == "taper":
        poly = np.asarray(TAPER)
        body_lo = np.array([poly[:, 0].min(), poly[:, 1].min(), z0])
        body_hi = np.array([poly[:, 0].max(), poly[:, 1].max(), z0 + 10.0])
        modbox = TAPER_MODIFIER
    elif body == "box":
        body_lo = np.array([BODY[0][0], BODY[1][0], z0 + BODY[2][0]])
        body_hi = np.array([BODY[0][1], BODY[1][1], z0 + BODY[2][1]])
        modbox = MODIFIER
    else:
        raise ValueError(f"unknown probe body {body!r}")
    shift = T_body[3] - T_mod[3]                            # same rotation (identity) in the template
    mod_lo = np.array([modbox[0][0], modbox[1][0], z0 + modbox[2][0]]) + shift
    mod_hi = np.array([modbox[0][1], modbox[1][1], z0 + modbox[2][1]]) + shift
    files = {}
    for name in zin.namelist():
        if name in ("Metadata/plate_1.gcode", "Metadata/plate_1.gcode.md5"):
            continue
        data = zin.read(name)
        if name.startswith("3D/Objects/") and name.endswith(".model"):
            oroot = ET.fromstring(data)
            res = oroot.find("m:resources", NS)
            for o in list(res.findall("m:object", NS)):
                if o.get("id") not in keep_ids:
                    res.remove(o)
                elif o.get("id") == body_c.get("objectid"):
                    if body == "taper":
                        _prism_mesh_xml(o, TAPER, body_lo[2], body_hi[2])
                    else:
                        _box_mesh_xml(o, body_lo, body_hi)
                else:
                    _box_mesh_xml(o, mod_lo, mod_hi)
            data = ET.tostring(oroot, xml_declaration=True, encoding="UTF-8")
        elif name == "Metadata/model_settings.config":
            croot = ET.fromstring(data)
            obj = croot.find("object")
            parts = obj.findall("part")
            for p in parts[2:]:
                obj.remove(p)
            mod = parts[1]
            for md in list(mod.findall("metadata")):
                if md.get("key") not in ("name", "matrix", "source_file", "source_object_id", "source_volume_id",
                                         "source_offset_x", "source_offset_y", "source_offset_z"):
                    mod.remove(md)
            for k, v in (overrides or {}).items():
                ET.SubElement(mod, "metadata", key=k, value=str(v))
            for k, v in (object_overrides or {}).items():      # positive controls: the same key on the whole object
                md = next((m for m in obj.findall("metadata") if m.get("key") == k), None)
                if md is None:
                    md = ET.Element("metadata", key=k)
                    obj.insert(1, md)
                md.set("value", str(v))
            data = ET.tostring(croot, xml_declaration=True, encoding="UTF-8")
        elif name == "3D/3dmodel.model":
            data = ET.tostring(root, xml_declaration=True, encoding="UTF-8")
        files[name] = data
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))    # reproducible bytes
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)

    def plate(lo, hi, T):
        c = np.array([[x, y, zz] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for zz in (lo[2], hi[2])])
        p = (c @ T[:3] + T[3]) @ B[:3] + B[3]
        return p.min(axis=0), p.max(axis=0)

    geo = {"body_plate_bbox": [a.tolist() for a in plate(body_lo, body_hi, T_body)],
           "modifier_plate_bbox": [a.tolist() for a in plate(mod_lo, mod_hi, T_mod)]}
    return out.getvalue(), geo


def _fraction_in_box(a, b, lo, hi):
    """Fraction of each XY segment a->b inside the axis-aligned box [lo, hi] (exact for straight segments)."""
    d = b - a
    t0, t1 = np.zeros(len(a)), np.ones(len(a))
    for k in range(2):
        with np.errstate(divide="ignore", invalid="ignore"):
            ta = (lo[k] - a[:, k]) / d[:, k]
            tb = (hi[k] - a[:, k]) / d[:, k]
        lo_t, hi_t = np.minimum(ta, tb), np.maximum(ta, tb)
        par = d[:, k] == 0
        inside = (a[:, k] >= lo[k]) & (a[:, k] <= hi[k])
        lo_t = np.where(par, np.where(inside, -np.inf, np.inf), lo_t)
        hi_t = np.where(par, np.where(inside, np.inf, -np.inf), hi_t)
        t0, t1 = np.maximum(t0, lo_t), np.minimum(t1, hi_t)
    return np.clip(t1 - t0, 0.0, 1.0)


def region_volumes(tp, offset, geo, *, margin_mm=0.5, away_mm=3.0) -> dict:
    """Extrusion volume per role inside the modifier part of the body, and in the body away from it.

    Each segment's volume is split by the length that lies in each region, so a long wall that the
    slicer splits at a region boundary in one slice and not in another is counted the same way.
    """
    (blo, bhi), (mlo, mhi) = [np.asarray(b) for b in geo["body_plate_bbox"]], [np.asarray(b) for b in geo["modifier_plate_bbox"]]
    m = tp.in_object
    a = tp.start[m, :2] + np.asarray(offset)[:2]
    b = tp.end[m, :2] + np.asarray(offset)[:2]
    f_body = _fraction_in_box(a, b, blo[:2] - 1, bhi[:2] + 1)
    f_mod = _fraction_in_box(a, b, mlo[:2] + margin_mm, mhi[:2] - margin_mm)
    f_near = _fraction_in_box(a, b, mlo[:2] - away_mm, mhi[:2] + away_mm)
    regions = {"inside": f_mod, "outside": np.clip(f_body - f_near, 0.0, 1.0)}
    role, vol, width = tp.role[m], tp.volume[m], tp.width[m]
    out = {}
    for name, frac in regions.items():
        roles = {}
        for r in np.unique(role[frac > 0]):
            sel = (role == r) & (frac > 0)
            w = frac[sel] * vol[sel]
            roles[str(r)] = {"volume_mm3": round(float(w.sum()), 4), "segments": int(sel.sum()),
                             "mean_width_mm": round(float(np.average(width[sel], weights=w)), 4) if w.sum() > 0 else None}
        out[name] = roles
    return out


def orca_version(text: str) -> str | None:
    m = re.search(r"^; generated by OrcaSlicer (\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


# --------------------------------------------------------------------------------------------------
# Probes, measurements and the capability file

PROBES = {
    "baseline": {},
    "sparse_infill_density=100%": {"sparse_infill_density": "100%"},
    "sparse_infill_density=40%": {"sparse_infill_density": "40%"},
    "sparse_infill_pattern=grid@40%": {"sparse_infill_density": "40%", "sparse_infill_pattern": "grid"},
    "wall_loops=1": {"wall_loops": "1"},
    "wall_loops=6": {"wall_loops": "6"},
    "top_shell_layers=2": {"top_shell_layers": "2", "top_shell_thickness": "0"},
    "bottom_shell_layers=2": {"bottom_shell_layers": "2", "bottom_shell_thickness": "0"},
    "top_shell_layers=15": {"top_shell_layers": "15", "top_shell_thickness": "0"},
    "wall_generator=classic": {"wall_generator": "classic"},
    "outer_wall_line_width=0.6": {"outer_wall_line_width": "0.6"},
    "inner_wall_line_width=0.6": {"inner_wall_line_width": "0.6"},
    "sparse_infill_line_width=0.6@40%": {"sparse_infill_density": "40%", "sparse_infill_line_width": "0.6"},
    "layer_height=0.1": {"layer_height": "0.1"},
}


def slug(name: str) -> str:
    return name.replace("=", "-").replace("%", "pc").replace("@", "-at-").replace(".", "p")


def wall_lines(tp, offset, geo, z=5.0) -> dict:
    """Distinct wall lines parallel to X (layer at z): at the body's end inside the modifier, at the far end, and
    along the internal boundary between the modifier region and the rest of the body."""
    (blo, bhi), (_mlo, mhi) = [np.asarray(b) for b in geo["body_plate_bbox"]], [np.asarray(b) for b in geo["modifier_plate_bbox"]]
    a, b = tp.start[:, :2] + np.asarray(offset)[:2], tp.end[:, :2] + np.asarray(offset)[:2]
    w = tp.in_object & np.isin(tp.role, ["Outer wall", "Inner wall"]) & (np.abs(tp.end[:, 2] - z) < 0.05)
    flat = w & (np.abs(a[:, 1] - b[:, 1]) < 1e-3) & (np.abs(a[:, 0] - b[:, 0]) > 10)
    y = a[:, 1]

    def count(mask):
        return len({round(float(v), 3) for v in y[mask]})
    return {"modifier_end": count(flat & (y < blo[1] + 3)), "far_end": count(flat & (y > bhi[1] - 3)),
            "internal_boundary": count(flat & (np.abs(y - mhi[1]) < 3))}


def infill_diagonal_fraction(tp, offset, geo) -> float | None:
    (mlo, mhi) = [np.asarray(b) for b in geo["modifier_plate_bbox"]]
    mid = (tp.start + tp.end)[:, :2] / 2 + np.asarray(offset)[:2]
    sel = tp.in_object & (tp.role == "Sparse infill") & np.all((mid >= mlo[:2] + 0.5) & (mid <= mhi[:2] - 0.5), axis=1)
    if not sel.any():
        return None
    d = tp.end[sel, :2] - tp.start[sel, :2]
    L = np.linalg.norm(d, axis=1)
    ang = np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 180
    diag = (np.abs(ang - 45) < 5) | (np.abs(ang - 135) < 5)
    return float(L[diag].sum() / L.sum())


def _tot(r):
    return sum(v["volume_mm3"] for v in r.values())


def capability_records(probes: dict, extras: dict) -> list[dict]:
    """One record per probe (except the baseline): requested vs measured, status, side effects, receipt."""
    base = probes["baseline"]["regions"]
    bw = extras["baseline"]["wall_lines"]
    recs = []
    for name, p in probes.items():
        if name == "baseline":
            continue
        ins, out = p["regions"]["inside"], p["regions"]["outside"]
        role_d = {k: round(ins.get(k, {}).get("volume_mm3", 0) - base["inside"].get(k, {}).get("volume_mm3", 0), 1)
                  for k in sorted(set(ins) | set(base["inside"]))}
        role_d = {k: v for k, v in role_d.items() if abs(v) >= 0.5}
        out_rel = (_tot(out) - _tot(base["outside"])) / _tot(base["outside"])
        key = name.split("=")[0]
        ex = extras[name]
        status, measured = "unknown", {}
        if key == "sparse_infill_density":
            want = p["overrides"]["sparse_infill_density"]
            measured = {"inside_role_delta_mm3": role_d}
            hit = role_d.get("Internal solid infill", 0) > 100 if want == "100%" else role_d.get("Sparse infill", 0) > 100
            status = "honoured" if hit else "ignored"
        elif key == "sparse_infill_pattern":
            measured = {"diagonal_length_fraction": round(ex["diagonal_fraction"], 3),
                        "default_pattern_diagonal_fraction": round(extras["sparse_infill_density=40%"]["diagonal_fraction"], 3)}
            status = "honoured" if ex["diagonal_fraction"] > 0.8 else "unknown"
        elif key == "wall_loops":
            want = int(p["overrides"]["wall_loops"])
            measured = {"wall_lines_modifier_end": ex["wall_lines"]["modifier_end"], "wall_lines_far_end": ex["wall_lines"]["far_end"],
                        "wall_lines_internal_boundary": ex["wall_lines"]["internal_boundary"],
                        "baseline_wall_lines": bw["modifier_end"]}
            status = "honoured" if ex["wall_lines"]["modifier_end"] == want and ex["wall_lines"]["far_end"] == bw["far_end"] else "unknown"
        elif key in ("top_shell_layers", "bottom_shell_layers"):
            measured = {"inside_role_delta_mm3": role_d}
            status = "honoured" if abs(role_d.get("Internal solid infill", 0)) > 100 else "ignored"
        elif key.endswith("line_width"):
            role = {"outer_wall_line_width": "Outer wall", "inner_wall_line_width": "Inner wall",
                    "sparse_infill_line_width": "Sparse infill"}[key]
            w = ins.get(role, {}).get("mean_width_mm")
            measured = {"mean_declared_width_mm": w}
            status = "honoured" if w is not None and abs(w - float(p["overrides"][key])) < 0.02 else "ignored"
        elif key == "layer_height":
            measured = {"layer_heights_mm": p["layer_heights"]}
            status = "ignored" if not role_d and 0.1 not in p["layer_heights"] else "honoured"
        elif key == "wall_generator":
            measured = {"inside_role_delta_mm3": role_d}
            status = "unknown" if not role_d else "honoured"
        effects = []
        if abs(out_rel) >= 0.005:
            effects.append(f"volume outside the modifier region changes by {100 * out_rel:+.1f} %")
        nb = ex["wall_lines"]["internal_boundary"]
        if nb > extras["baseline"]["wall_lines"]["internal_boundary"]:
            effects.append(f"{nb} wall lines appear along the internal boundary between the modifier region and the "
                           "body (the region gets its own perimeters, and so does the body next to it)")
        side = "; ".join(effects) or None
        note = None
        if key == "wall_generator" and status == "unknown":
            note = "the probe box has constant wall thickness, where classic and Arachne walls coincide; needs a tapered probe"
        recs.append({"key": key, "requested": p["overrides"], "status": status, "measured": measured,
                     "non_local_side_effect": side, "note": note,
                     "receipt": {"probe": name, "gcode_sha256": p["gcode_sha256"]}})
    return recs


def run_probes(template_path, workdir, orca_cmd: list[str], probes: dict | None = None, log=print) -> tuple[dict, dict]:
    """Build, slice and measure every probe. orca_cmd is the slicer command prefix (arrange/orient off added here)."""
    import hashlib
    import subprocess
    from pathlib import Path

    from ..gcode import extruder_offset, read_gcode
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    template = Path(template_path).read_bytes()
    results, extras = {}, {}
    for name, ov in (probes or PROBES).items():
        data, geo = build_variant(template, ov)
        f3 = work / f"{slug(name)}.3mf"
        f3.write_bytes(data)
        out = work / f"out-{slug(name)}"
        out.mkdir(exist_ok=True)
        r = subprocess.run([*orca_cmd, "--arrange", "0", "--orient", "0", "--slice", "0", "--outputdir", str(out), str(f3)],
                           capture_output=True, text=True, timeout=900, check=False)
        g = out / "plate_1.gcode"
        if r.returncode != 0 or not g.exists():
            raise RuntimeError(f"slicer failed on probe {name} (exit {r.returncode}): {(r.stdout + r.stderr)[-300:]}")
        text = g.read_text(encoding="utf-8")
        tp = read_gcode(text)
        off = extruder_offset(text)
        results[name] = {"overrides": ov, "orca": orca_version(text), "gcode_sha256": hashlib.sha256(g.read_bytes()).hexdigest(),
                         "geometry": geo, "regions": region_volumes(tp, off, geo),
                         "layer_heights": sorted({round(float(h), 3) for h in tp.declared_height[tp.in_object]})}
        extras[name] = {"wall_lines": wall_lines(tp, off, geo), "diagonal_fraction": infill_diagonal_fraction(tp, off, geo)}
        if name == "baseline":
            from ..catalog.checks.proc import settings_from_gcode
            cfg = settings_from_gcode(text)
            extras["_context"] = {k: cfg.get(k) for k in ("printer_model", "print_settings_id", "filament_settings_id",
                                                           "nozzle_diameter", "layer_height", "wall_loops",
                                                           "sparse_infill_density", "wall_generator")}
            extras["_context"]["template_3mf_sha256"] = hashlib.sha256(template).hexdigest()
        log(f"{name}: sliced")
    return results, extras


def capability_file(probes: dict, extras: dict) -> dict:
    ctx = dict(extras.get("_context", {}))
    ctx["slicer"] = "OrcaSlicer"
    ctx["version"] = probes["baseline"]["orca"]
    return {
        "schema": "fdmgen/slicer-capabilities@0.1",
        "scope": "per-volume overrides on a modifier_part in an Orca 3MF (Metadata/model_settings.config)",
        "context": ctx,
        "method": ("60 x 40 x 10 mm box body, one modifier box over its +Y end in the plate frame; one override per "
                   "slice; extrusion per role inside the modifier region (segments apportioned by length) compared "
                   "with a no-override baseline, and the rest of the body checked for side effects"),
        "status_meaning": {"honoured": "the slice changed inside the region as requested",
                           "ignored": "the slice did not change although the probe could show the change",
                           "unknown": "the probe could not tell; keep the setting visible as unchecked"},
        "settings": capability_records(probes, extras),
        "establishes": "What this Orca version does with these overrides in this profile context (tier S).",
        "does_not_establish": "Behaviour in other Orca versions or profiles, or how the printed regions perform.",
    }
