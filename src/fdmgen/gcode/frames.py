"""Frame chain from G-code back to the model (PLAN D3, frames table in research/final/frodo.md 2.1).

gcode G -> plate B: Orca subtracts the extruder offset when it writes moves, so add it back.
plate B -> model:   undo the 3MF build-item placement, model = (plate - t) @ R (R orthonormal).
model -> design:    undo `filament_shrink` (an XY scale about a centre) when the slice used one.
Ported from spool-wall-rack@14338e9:analysis/rev-g2/plastic_shape.py (`read_paths` transform lines).
The shrink centre is NOT known: it is a required argument rather than a guessed default. Measured on
Orca 2.4.2 (CLI, P1S profiles): setting filament_shrink to 99.46 % (project or filament preset) wrote the
key into the G-code but left every toolpath unscaled. So never undo a shrink because the config says
so; measure the scale with xy_scale_vs_model first.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile

import numpy as np


def build_transform_from_3mf(path) -> np.ndarray:
    """(4, 3) build-item transform of the single object in a sliced 3MF: rows 0-2 = R, row 3 = t."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    items = root.findall("{*}build/{*}item")
    if len(items) != 1:
        raise ValueError(f"expected one build item, found {len(items)}; per-object mapping is not implemented")
    xf = np.array([float(v) for v in items[0].attrib["transform"].split()]).reshape(4, 3)
    if not np.allclose(xf[:3] @ xf[:3].T, np.eye(3), atol=1e-6):
        raise ValueError("build transform is not a rotation (scaled or sheared placement)")
    if not np.allclose(xf[:3, 2], [0, 0, 1], atol=1e-6):
        raise ValueError("build transform tilts Z; the layers would not be the model's layers")
    return xf


def extruder_offset(gcode_text: str) -> np.ndarray:
    """The configured nozzle offset (Orca writes `; extruder_offset = 0x2`); zeros when absent."""
    m = re.search(r"^; extruder_offset = (.+)$", gcode_text, re.MULTILINE)
    off = np.zeros(3)
    if m:
        parts = m.group(1).strip().split(",")
        if len(parts) != 1:
            raise ValueError("several extruder offsets need per-tool mapping")
        off[:2] = [float(v) for v in parts[0].split("x")]
    return off


def gcode_to_model(points, xf: np.ndarray, offset) -> np.ndarray:
    """G-code coordinates -> model coordinates: restore the extruder offset, undo the placement."""
    return (np.asarray(points, float) + np.asarray(offset, float) - xf[3]) @ xf[:3].T


def undo_xy_shrink(points, shrink_percent: float, centre_xy) -> np.ndarray:
    """Undo Orca's `filament_shrink`: the slicer scaled XY by 100/p about centre_xy; scale back by p/100."""
    p = np.array(points, float, copy=True)
    s = shrink_percent / 100.0
    c = np.asarray(centre_xy, float)
    p[..., :2] = (p[..., :2] - c) * s + c
    return p


def _xf(s: str | None) -> np.ndarray:
    return np.array([float(v) for v in (s or "1 0 0 0 1 0 0 0 1 0 0 0").split()]).reshape(4, 3)


def placed_component_bbox(path, component: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """XYZ bounding box of one component (default the first, the body) as placed on the plate.

    Reads the object meshes under 3D/Objects/, applies the component transform and then the build-item
    transform (3MF row-vector convention, p' = p @ M[:3] + M[3]).
    """
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
        meshes = {}
        for name in z.namelist():
            if name.startswith("3D/Objects/") and name.endswith(".model"):
                for o in ET.fromstring(z.read(name)).findall(".//{*}object"):
                    meshes[o.get("id")] = np.array([[float(v.get(k)) for k in "xyz"]
                                                    for v in o.findall(".//{*}vertex")])
    comps = root.findall(".//{*}component")
    build = _xf(root.find("{*}build/{*}item").get("transform"))
    if comps:
        c = comps[component]
        T = _xf(c.get("transform"))
        v = meshes[c.get("objectid")] @ T[:3] + T[3]
    else:
        v = next(iter(meshes.values()))
    p = v @ build[:3] + build[3]
    return p.min(axis=0), p.max(axis=0)


def xy_scale_vs_model(tp, offset, model_lo, model_hi, half_width: float) -> dict:
    """Compare the object's G-code footprint (offset restored) with the placed model footprint.

    The outer-wall centreline sits half a line width inside the model edge, so the expected G-code
    extent is the model extent minus one line width. Returns per-axis scale (1.0 = unscaled) and the
    four side insets. This, not the `filament_shrink` key, decides whether a shrink undo is needed.
    """
    m = tp.in_object
    q = np.vstack([tp.start[m], tp.end[m]])[:, :2] + np.asarray(offset, float)[:2]
    lo, hi = q.min(axis=0), q.max(axis=0)
    mlo, mhi = np.asarray(model_lo, float)[:2], np.asarray(model_hi, float)[:2]
    scale = (hi - lo) / (mhi - mlo - 2 * half_width)
    return {"scale_xy": scale.tolist(), "inset_lo_xy": (lo - mlo).tolist(), "inset_hi_xy": (mhi - hi).tolist(),
            "gcode_bbox_xy": [lo.tolist(), hi.tolist()], "model_bbox_xy": [mlo.tolist(), mhi.tolist()]}
