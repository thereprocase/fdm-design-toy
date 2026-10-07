"""Candidate print poses (PLAN D8): stable resting poses on convex-hull facets, axes, sphere samples.

A pose is given by its build direction d in the design frame: the part is rotated so d points to +Z
of the print frame and dropped onto the bed. d and -d are different poses for printability (the
inter-layer index alone is even in d).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import ConvexHull


@dataclass
class Pose:
    id: str
    kind: str                      # stable_facet | axis | sphere | user
    d: np.ndarray                  # build direction, design frame, unit
    meta: dict = field(default_factory=dict)


def rotation_to_z(d) -> np.ndarray:
    """Proper rotation R with R @ d = +Z (shortest arc; a 180 deg turn about X for d = -Z)."""
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    z = np.array([0.0, 0.0, 1.0])
    v, c = np.cross(d, z), float(d @ z)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1.0 + c)


def place(vertices, d):
    """Vertices in the print frame for build direction d (bed at z = 0), plus (R, t): p = R x + t."""
    R = rotation_to_z(d)
    V = np.asarray(vertices, float) @ R.T
    t = np.array([0.0, 0.0, -V[:, 2].min()])
    return V + t, R, t


def fibonacci_directions(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.c_[np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)]


def hull_facets(vertices, *, angle_tol_deg: float = 0.5, offset_tol_mm: float = 0.05):
    """Planar facets of the convex hull: (outward normal, area mm2), coplanar triangles merged."""
    V = np.asarray(vertices, float)
    hull = ConvexHull(V)
    tri = V[hull.simplices]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2
    eq = hull.equations                               # n . x + offset <= 0 inside, n outward unit
    cos_tol = np.cos(np.radians(angle_tol_deg))
    facets = []                                       # [normal_sum, offset, area]
    for k in np.argsort(-area):
        n, off = eq[k, :3], eq[k, 3]
        for f in facets:
            fn = f[0] / np.linalg.norm(f[0])
            if fn @ n >= cos_tol and abs(f[1] - off) <= offset_tol_mm:
                f[0] += n * area[k]
                f[2] += area[k]
                break
        else:
            facets.append([n * area[k], off, area[k]])
    return [(f[0] / np.linalg.norm(f[0]), float(f[2])) for f in sorted(facets, key=lambda f: -f[2])]


def candidate_poses(vertices, *, min_facet_area_mm2: float = 100.0, axes: bool = True, sphere: int = 0,
                    user=()) -> list[Pose]:
    """Stable facet poses (facet down on the bed), the six axis poses, optional sphere samples, user poses.

    Duplicate directions (within 0.5 deg) keep the first, most specific label.
    """
    poses = [Pose(f"facet-{i:02d}", "stable_facet", -n, {"facet_area_mm2": a})
             for i, (n, a) in enumerate(hull_facets(vertices)) if a >= min_facet_area_mm2]
    if axes:
        for name, d in (("+x", (1, 0, 0)), ("-x", (-1, 0, 0)), ("+y", (0, 1, 0)), ("-y", (0, -1, 0)),
                        ("+z", (0, 0, 1)), ("-z", (0, 0, -1))):
            poses.append(Pose(f"axis{name}", "axis", np.array(d, float)))
    poses += [Pose(f"sphere-{i:04d}", "sphere", d) for i, d in enumerate(fibonacci_directions(sphere))] if sphere else []
    poses += [Pose(f"user-{i}", "user", np.asarray(d, float) / np.linalg.norm(d)) for i, d in enumerate(user, 1)]
    out: list[Pose] = []
    for p in poses:
        dup = next((q for q in out if q.d @ p.d >= np.cos(np.radians(0.5))), None)
        if dup is None:
            out.append(p)
        else:
            dup.meta.setdefault("also", []).append(p.id)
    return out
