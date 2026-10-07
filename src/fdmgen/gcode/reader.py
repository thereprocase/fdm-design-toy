"""Canonical Orca G-code reader and the credited-material split.

Ported from spool-wall-rack@14338e9:analysis/rev-g2/plastic_shape.py (`read_paths`), keeping its
semantics exactly where they define the credited volume (P0-A parity):
- extrusion volume of a move = E x filament cross-section; relative (M83) or absolute (M82) E;
- only moves that extrude (E > 0) and move in XY (> 1e-7 mm) are material; retractions and E-only
  moves are not;
- moves between `; printing object` and `; stop printing object` are part material; the rest
  (priming lines) is spent plastic only;
- thick bridges (a role containing "bridge" with height above the nominal layer height) are spent
  plastic with no structural credit; everything else in the object is credited;
- Orca's 0.199999 / 0.200001 height comments are normalised to the nominal height.
Changes from the source, each covered by a test:
- G2/G3 arcs (I/J centre form, XY plane) are read and split into chords with E shared by length; the
  source parsed only G0/G1/G92, so arc-fitted G-code silently lost material;
- the footer check is part of the library call (`read_gcode(..., footer_rel_tol=...)` raises), where
  the source checked it only in `main()`;
- no geometry library is needed; footprints and frames live elsewhere.
Coordinates stay in the G-code frame here; see frames.py for the chain back to the model.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_WORD = re.compile(r"([XYZEIJRF])([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")


class FooterMismatch(ValueError):
    """The extrusion the reader found does not add up to the slicer's own footer total."""


@dataclass
class Toolpath:
    start: np.ndarray            # (n, 3) G-code frame, mm
    end: np.ndarray              # (n, 3)
    role: np.ndarray             # (n,) str, Orca ;TYPE: role
    width: np.ndarray            # (n,) mm, declared line width
    height: np.ndarray           # (n,) mm, declared height, normalised to nominal within 1e-5
    declared_height: np.ndarray  # (n,) mm, as written
    volume: np.ndarray           # (n,) mm3, E x filament area
    in_object: np.ndarray        # (n,) bool, between printing-object markers
    from_arc: np.ndarray         # (n,) bool, chord of a G2/G3 move
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.volume)


def _arc_chords(p0, p1, i, j, clockwise, max_chord_angle):
    """Chord end points of an XY arc from p0 to p1 about p0 + (i, j) (Z interpolated).

    G-code rounds coordinates (Orca: 0.001 mm), so start and end radii differ slightly; like printer
    firmware, the radius is interpolated along the sweep so the arc ends exactly at p1. A mismatch
    above 0.01 mm (or 1 % of the radius) is a malformed arc and raises.
    """
    cx, cy = p0[0] + i, p0[1] + j
    r0 = math.hypot(p0[0] - cx, p0[1] - cy)
    r1 = math.hypot(p1[0] - cx, p1[1] - cy)
    if r0 < 1e-9 or abs(r0 - r1) > max(0.01, 0.01 * r0):
        raise ValueError(f"inconsistent arc: radius {r0:.6f} at start, {r1:.6f} at end")
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    sweep = a1 - a0
    if clockwise and sweep >= 0:
        sweep -= 2 * math.pi
    if not clockwise and sweep <= 0:
        sweep += 2 * math.pi
    n = max(1, math.ceil(abs(sweep) / max_chord_angle))
    t = np.arange(1, n + 1) / n
    pts = np.empty((n, 3))
    r = r0 + (r1 - r0) * t
    pts[:, 0] = cx + r * np.cos(a0 + sweep * t)
    pts[:, 1] = cy + r * np.sin(a0 + sweep * t)
    pts[:, 2] = p0[2] + (p1[2] - p0[2]) * t
    pts[-1] = p1
    return pts


def read_gcode(source, *, nominal_height: float = 0.2, footer_rel_tol: float | None = 1e-3,
               arc_chord_deg: float = 5.0, layer_tol: float = 1e-3) -> Toolpath:
    """Read extrusion segments from Orca G-code (a path or the text itself).

    footer_rel_tol: raise FooterMismatch when all moving extrusion (object + priming) differs from the
    footer `filament used [cm3]` by more than this; None skips the check (and says so in meta).
    """
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file()):
        raw = Path(source).read_bytes()
    else:
        raw = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    text = raw.decode("utf-8")
    m = re.search(r"; filament_diameter: ([\d.]+)", text) or re.search(r"^; filament_diameter = ([\d.]+)", text, re.MULTILINE)
    if not m:
        raise ValueError("no filament_diameter in the G-code; cannot convert E to volume")
    diameter = float(m.group(1))
    area = math.pi * diameter ** 2 / 4
    max_chord = math.radians(arc_chord_deg)

    pos = np.zeros(3)
    relative_e, absolute_xyz, prev_e = True, True, 0.0
    role, width, height, layer_z = "Custom", 0.45, nominal_height, None
    starts, ends, roles, widths, heights, declared, vols, inobj, arcs = [], [], [], [], [], [], [], [], []
    active = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("; printing object"):
            active = True
        elif line.startswith("; stop printing object"):
            active = False
        elif line.startswith((";TYPE:", "; FEATURE:")):
            role = line.split(":", 1)[1].strip()
        elif line.startswith((";WIDTH:", "; LINE_WIDTH:")):
            width = float(line.split(":", 1)[1])
        elif line.startswith((";HEIGHT:", "; LAYER_HEIGHT:")):
            height = float(line.split(":", 1)[1])
        elif line.startswith((";Z:", "; Z_HEIGHT:")):
            layer_z = float(line.split(":", 1)[1])
        code = line.split(";", 1)[0].strip()
        if not code:
            continue
        cmd = code.split(None, 1)[0]
        if cmd == "M83":
            relative_e = True
        elif cmd == "M82":
            relative_e = False
        elif cmd == "G90":
            absolute_xyz = True
        elif cmd == "G91":
            absolute_xyz = False
        elif cmd in ("G0", "G1", "G2", "G3", "G92"):
            f = {k: float(v) for k, v in _WORD.findall(code[len(cmd):])}
            if cmd == "G92":
                if "E" in f:
                    prev_e = f["E"]
                for a, k in enumerate("XYZ"):
                    if k in f:
                        pos[a] = f[k]
                continue
            new = pos.copy()
            for a, k in enumerate("XYZ"):
                if k in f:
                    new[a] = f[k] if absolute_xyz else new[a] + f[k]
            e = f.get("E", 0.0) if relative_e else (f["E"] - prev_e if "E" in f else 0.0)
            if "E" in f:
                prev_e = f["E"] if not relative_e else prev_e + f["E"]
            is_arc = cmd in ("G2", "G3")
            if is_arc and "R" in f:
                raise ValueError(f"line {lineno}: R-form arcs are not supported; Orca writes I/J arcs")
            if e > 0 and (np.linalg.norm(new[:2] - pos[:2]) > 1e-7 or is_arc):
                if active:
                    if layer_z is None or abs(new[2] - layer_z) > layer_tol:
                        raise ValueError(f"line {lineno}: extruding at Z {new[2]} but the layer comment says {layer_z}")
                    if abs(new[2] - pos[2]) > layer_tol:
                        raise ValueError(f"line {lineno}: non-planar extruding move needs a 3D sweep")
                if is_arc:
                    pts = _arc_chords(pos, new, f.get("I", 0.0), f.get("J", 0.0), cmd == "G2", max_chord)
                    seg0 = np.vstack([pos, pts[:-1]])
                    lens = np.linalg.norm(pts - seg0, axis=1)
                    share = lens / lens.sum()
                else:
                    pts, seg0, share = new[None], pos[None], np.ones(1)
                for a, b, s in zip(seg0, pts, share):
                    starts.append(a.copy())
                    ends.append(b.copy())
                    vols.append(e * s * area if is_arc else e * area)
                    roles.append(role)
                    widths.append(width)
                    heights.append(nominal_height if abs(height - nominal_height) < 1e-5 else height)
                    declared.append(height)
                    inobj.append(active)
                    arcs.append(is_arc)
            pos = new
    tp = Toolpath(np.asarray(starts).reshape(-1, 3), np.asarray(ends).reshape(-1, 3), np.asarray(roles),
                  np.asarray(widths), np.asarray(heights), np.asarray(declared), np.asarray(vols),
                  np.asarray(inobj, bool), np.asarray(arcs, bool))
    footer = re.search(r"; filament used \[cm3\] = ([\d.]+)", text)
    total = float(tp.volume.sum())
    tp.meta = {"gcode_sha256": hashlib.sha256(raw).hexdigest(), "filament_diameter_mm": diameter,
               "moving_extrusion_volume_mm3": total,
               "object_moving_extrusion_volume_mm3": float(tp.volume[tp.in_object].sum()),
               "nonobject_moving_extrusion_volume_mm3": float(tp.volume[~tp.in_object].sum()),
               "arc_chords": int(tp.from_arc.sum()), "nominal_height_mm": nominal_height,
               "footer_volume_mm3": float(footer.group(1)) * 1000 if footer else None}
    if footer_rel_tol is not None:
        if footer is None:
            raise FooterMismatch("the G-code has no '; filament used [cm3]' footer, so its extrusion total cannot "
                                 "be checked; pass footer_rel_tol=None only if you accept that")
        rel = abs(total / tp.meta["footer_volume_mm3"] - 1)
        tp.meta["footer_relative_difference"] = rel
        if rel > footer_rel_tol:
            raise FooterMismatch(
                f"the reader found {total:.3f} mm3 of moving extrusion but the slicer's footer says "
                f"{tp.meta['footer_volume_mm3']:.3f} mm3 (relative difference {rel:.2e} > {footer_rel_tol:g}). "
                "Some extrusion was not understood (arc moves, unusual commands?) and no volume from this file "
                "can be trusted.")
    else:
        tp.meta["footer_check"] = "skipped by caller"
    return tp


def credit(tp: Toolpath, *, nominal_height: float | None = None, thick_margin: float = 1e-4) -> dict:
    """Split object material into credited and sacrificial (thick bridges); priming is spent only.

    A segment is a thick bridge when its role contains "bridge" and its height exceeds the nominal
    layer height by more than thick_margin (0.2001 mm in the source). Sparse infill in an object is an
    error for problems declared at 0 % infill, so it is reported, not silently credited.
    """
    h0 = tp.meta.get("nominal_height_mm", 0.2) if nominal_height is None else nominal_height
    obj = tp.in_object
    low = np.char.lower(tp.role.astype(str))
    thick = obj & (np.char.find(low, "bridge") >= 0) & (tp.height > h0 + thick_margin)
    # support, skirt, brim and prime tower are never part (absent from every archived parity slice)
    aux = obj & ((np.char.find(low, "support") >= 0) | np.isin(low, ["skirt", "brim", "prime tower", "wipe tower"]))
    credited = obj & ~thick & ~aux
    return {
        "structurally_credited_extrusion_volume_mm3": float(tp.volume[credited].sum()),
        "sacrificial_thick_bridge_extrusion_volume_mm3": float(tp.volume[thick].sum()),
        "nonobject_spent_volume_mm3": float(tp.volume[~obj].sum()),
        "support_and_aux_volume_mm3": float(tp.volume[aux].sum()),
        "support_segments": int((obj & (np.char.find(low, "support") >= 0)).sum()),
        "thick_bridge_segments": int(thick.sum()),
        "thick_bridge_heights_mm": sorted(set(tp.height[thick].tolist())),
        "sparse_infill_volume_mm3": float(tp.volume[obj & (tp.role == "Sparse infill")].sum()),
        "credited_mask": credited,
        "policy": ("Thick bridges, priming lines, support, skirt, brim and prime tower are spent plastic only: "
                   "no stiffness, strength or bond credit."),
    }
