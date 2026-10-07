"""Orientation-aware interfaces (PLAN D14, HOLE-001): which bores need a roof variant in a pose.

A bore whose axis lies within 45 deg of the layer plane prints with a roof (crown) that needs a
self-supporting variant, e.g. a teardrop with its crest along +Z of the print frame. Interfaces
declare `roof_variant: teardrop_auto` when the geometry can be generated per pose; without it the
frozen geometry's roof decides, and OVH-001 on the mesh is the check that sees it.
"""
from __future__ import annotations

import numpy as np

AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
ROOF_LIMIT_DEG = 45.0


def axis_vector(axis) -> np.ndarray:
    v = np.asarray(AXES[axis.upper()] if isinstance(axis, str) else axis, float)
    return v / np.linalg.norm(v)


def interface_roofs(interfaces, d) -> dict:
    """Per-pose HOLE-001 summary for the problem's interfaces (design frame) and build direction d."""
    d = np.asarray(d, float) / np.linalg.norm(d)
    rows, bad = [], []
    for i in interfaces or []:
        if "axis" not in i:
            continue
        a = axis_vector(i["axis"])
        tilt = float(np.degrees(np.arcsin(min(1.0, abs(float(a @ d))))))   # axis angle out of the layer plane
        needs = tilt < ROOF_LIMIT_DEG
        variant = i.get("roof_variant")
        rows.append({"id": i["id"], "axis_from_layer_plane_deg": round(tilt, 3), "needs_roof_variant": needs,
                     "roof_variant": variant})
        if needs and not variant:
            bad.append(i["id"])
    if bad:
        verdict = "FAIL"
        msg = (f"{', '.join(bad)}: axis within {ROOF_LIMIT_DEG:.0f} deg of the layer plane and no roof_variant declared; "
               "the frozen geometry's roof decides (see OVH-001), or declare teardrop_auto in problem.yaml")
    else:
        verdict = "PASS" if rows else "NOT_CHECKED"
        msg = "every interface is near-vertical or has a generated roof variant" if rows else "no interfaces declared"
    return {"verdict": verdict, "message": msg, "interfaces": rows, "missing_variant": bad}
