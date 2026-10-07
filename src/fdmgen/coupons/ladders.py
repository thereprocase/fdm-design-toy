"""Overhang and bridge ladders (catalog OVH-001 / OVH-002 and BRG-001 calibration, issue #12).

Geometry is built in the print frame (bed at z = 0, +Z = build direction), in mm, as closed,
outward-wound triangle shells, one shell per solid; a plate is the union of disjoint shells.
- Overhang rung (alpha): a block standing on the bed whose +X side overhangs with an underside
  slope alpha from horizontal (the catalog's angle convention). Rungs 35..60 deg by 5 by default,
  which brackets the 50 deg design limit and Orca's 45 deg support threshold.
- Bridge rung (span): two pillars and a deck whose middle bridges `span` mm of air. Spans 6..40 mm
  by default, around the provisional 10 mm external / 18 mm internal BRG-001 limits.
Every rung's defining number is in its metadata, so checkers and slices can be read per rung.
"""
from __future__ import annotations

import numpy as np

OVERHANG_DEG = (35, 40, 45, 50, 55, 60)
BRIDGE_MM = (6, 10, 14, 18, 24, 30, 40)


def _prism_xz(poly, y0, depth):
    """Closed prism: convex CCW polygon in the XZ plane, extruded from y0 to y0 + depth (outward wound)."""
    p = np.asarray(poly, float)
    n = len(p)
    v = np.vstack([np.c_[p[:, 0], np.full(n, y0), p[:, 1]], np.c_[p[:, 0], np.full(n, y0 + depth), p[:, 1]]])
    f = []
    for i in range(1, n - 1):
        f += [(0, i, i + 1), (n, n + i + 1, n + i)]
    for i in range(n):
        j = (i + 1) % n
        f += [(i, j + n, j), (i, i + n, j + n)]
    f = np.array(f)
    tri = v[f]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()
    return v, (f if vol > 0 else f[:, ::-1])


def _box(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    return _prism_xz([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], y0, y1 - y0)


def _merge(shells):
    vs, fs, off = [], [], 0
    for v, f in shells:
        vs.append(v)
        fs.append(f + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


def overhang_ladder(angles=OVERHANG_DEG, *, height=10.0, base=6.0, depth=8.0, gap=6.0, origin=(0.0, 0.0)):
    shells, meta, x = [], [], origin[0]
    for a in angles:
        run = height / np.tan(np.radians(a))
        shells.append(_prism_xz([(x, 0), (x + base, 0), (x + base + run, height), (x, height)], origin[1], depth))
        meta.append({"id": f"ovh-{a:02d}", "kind": "overhang", "alpha_deg": float(a), "base_mm": float(base),
                     "underside_area_mm2": float(depth * height / np.sin(np.radians(a))),
                     "bbox_mm": [[x, origin[1], 0.0], [x + base + run, origin[1] + depth, height]]})
        x += base + run + gap
    return _merge(shells), meta


def bridge_ladder(spans=BRIDGE_MM, *, pillar=5.0, width=5.0, pillar_h=6.0, deck=1.2, pitch=12.0, origin=(0.0, 0.0)):
    shells, meta, y = [], [], origin[1]
    x0 = origin[0]
    for s in spans:
        xa, xb = x0 + pillar, x0 + pillar + s
        shells += [_box((x0, y, 0), (xa, y + width, pillar_h)),
                   _box((xb, y, 0), (xb + pillar, y + width, pillar_h)),
                   _box((x0, y, pillar_h), (xb + pillar, y + width, pillar_h + deck))]
        meta.append({"id": f"brg-{s:02d}", "kind": "bridge", "span_mm": float(s), "deck_z_mm": [pillar_h, pillar_h + deck],
                     "bridge_bbox_mm": [[xa, y, pillar_h], [xb, y + width, pillar_h + deck]],
                     "bbox_mm": [[x0, y, 0.0], [xb + pillar, y + width, pillar_h + deck]]})
        y += pitch
    return _merge(shells), meta


def _shift_meta(meta, d):
    out = []
    for m in meta:
        m = dict(m)
        for k in ("bbox_mm", "bridge_bbox_mm"):
            if k in m:
                m[k] = [[c + o for c, o in zip(p, d)] for p in m[k]]
        out.append(m)
    return out


def plate(*, overhang=OVERHANG_DEG, bridges=BRIDGE_MM, center_xy=(128.0, 128.0)):
    """Both ladders on one plate (overhang row in front, bridge rungs behind), its footprint box centred
    on center_xy (the P1S bed centre by default, clear of the 0..18 x 0..28 mm exclusion zone)."""
    (v1, f1), m1 = overhang_ladder(overhang)
    (v2, f2), m2 = bridge_ladder(bridges, origin=(0.0, 20.0))
    v, f = _merge([(v1, f1), (v2, f2)])
    d = [center_xy[0] - (v[:, 0].min() + v[:, 0].max()) / 2, center_xy[1] - (v[:, 1].min() + v[:, 1].max()) / 2, 0.0]
    return (v + d, f), _shift_meta(m1 + m2, d)
