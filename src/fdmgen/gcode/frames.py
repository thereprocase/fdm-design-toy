"""Frame chain from G-code back to the model (PLAN D3, frames table in research/final/frodo.md 2.1).

gcode G -> plate B: Orca subtracts the extruder offset when it writes moves, so add it back.
plate B -> model:   undo the 3MF build-item placement, model = (plate - t) @ R (R orthonormal).
model -> design:    undo `filament_shrink` (an XY scale about a centre) when the slice used one.
Ported from spool-wall-rack@14338e9:analysis/rev-g2/plastic_shape.py (`read_paths` transform lines).
The shrink centre is NOT known yet: P0-F determines it with a 100 % vs 99.46 % fixture pair, so it is
a required argument rather than a guessed default.
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
