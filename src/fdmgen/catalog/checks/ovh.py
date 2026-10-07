"""OVH-001 self-supporting slope: V (support stencil on the print-frame grid) and M (mesh triangles).

Angle convention: alpha = slope from horizontal. A flat underside has alpha = 0, a vertical wall 90.
For a downward-facing triangle with outward unit normal n (n_z < 0): alpha = arccos(-n_z).
"""
from __future__ import annotations

import numpy as np

from ..result import CheckResult, Verdict

STENCILS = {
    # in-plane offsets (i, j) of the cells one layer below that can support a cell
    "cross5": ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)),
    "box9": tuple((i, j) for i in (-1, 0, 1) for j in (-1, 0, 1)),   # banned for design (admits ~35 deg)
}


def stencil_alpha_deg(h, phi_deg, stencil: str = "cross5") -> float:
    """Shallowest slope the stencil accepts in azimuth phi on cells h = (dx, dy, dz).

    The lateral advance per layer in azimuth phi is h_S(phi) = max over offsets of s . (cos phi, sin phi),
    so alpha_min(phi) = atan(dz / h_S(phi)) (research/final/sauron.md section 4.7).
    """
    dx, dy, dz = h
    c, s = np.cos(np.radians(phi_deg)), np.sin(np.radians(phi_deg))
    reach = max(i * dx * c + j * dy * s for i, j in STENCILS[stencil])
    return 90.0 if reach <= 0 else float(np.degrees(np.arctan2(dz, reach)))


def stencil_worst_alpha_deg(h, stencil: str = "cross5", n: int = 721) -> float:
    return min(stencil_alpha_deg(h, p, stencil) for p in np.linspace(0.0, 360.0, n))


def _support_below(below: np.ndarray, stencil: str) -> np.ndarray:
    nx, ny = below.shape[:2]
    pad = np.pad(below, ((1, 1), (1, 1)) + ((0, 0),) * (below.ndim - 2))
    out = np.zeros_like(below)
    for i, j in STENCILS[stencil]:
        out |= pad[1 + i:1 + i + nx, 1 + j:1 + j + ny]
    return out


def check_voxel(occ: np.ndarray, h, alpha_min_deg: float = 50.0, *, stencil: str = "cross5",
                bed_layer: int | None = None, origin=(0.0, 0.0, 0.0), provisional: bool = True) -> CheckResult:
    """V level: every occupied cell above the bed layer must rest on the stencil one layer below.

    occ is a boolean (nx, ny, nz) grid in the print frame (z = build direction), as produced by
    fdmgen.geom.voxel.voxelise. The bed layer defaults to the lowest occupied layer.
    """
    occ = np.asarray(occ, bool)
    grid_alpha = stencil_worst_alpha_deg(h, stencil)
    zs = np.flatnonzero(occ.any(axis=(0, 1)))
    if zs.size == 0:
        return CheckResult("OVH-001", "V", Verdict.NOT_CHECKED, "OVH-001 V NOT_CHECKED: the grid is empty.",
                           provisional)
    bed = int(zs[0]) if bed_layer is None else bed_layer
    unsupported = np.zeros_like(occ)
    unsupported[:, :, bed + 1:] = occ[:, :, bed + 1:] & ~_support_below(occ[:, :, bed:-1], stencil)
    n_bad = int(unsupported.sum())
    cell_area = h[0] * h[1]
    metrics = {"grid_alpha_deg": round(grid_alpha, 3), "alpha_min_deg": alpha_min_deg, "stencil": stencil,
               "unsupported_cells": n_bad, "unsupported_area_mm2": n_bad * cell_area, "bed_layer": bed}
    does_not = ("Mesh-level slopes between grid cells, and what Orca will actually do; the M and T checks "
                "are authoritative.")
    if n_bad:
        idx = np.argwhere(unsupported)
        lo = np.asarray(origin) + idx.min(axis=0) * np.asarray(h)
        hi = np.asarray(origin) + (idx.max(axis=0) + 1) * np.asarray(h)
        metrics["bbox_print_mm"] = [lo.round(3).tolist(), hi.round(3).tolist()]
        msg = (f"OVH-001 V FAIL: {n_bad} cells ({n_bad * cell_area:.1f} mm2 of underside) have nothing under "
               f"them within the {stencil} stencil, so they overhang more steeply than this grid allows "
               f"(shallowest accepted slope {grid_alpha:.1f} deg from horizontal). Print-frame box "
               f"X {lo[0]:.1f}..{hi[0]:.1f}, Y {lo[1]:.1f}..{hi[1]:.1f}, Z {lo[2]:.2f}..{hi[2]:.2f} mm.")
        return CheckResult("OVH-001", "V", Verdict.FAIL, msg, provisional, metrics,
                           ["run the AM filter on this field", "add material underneath to reach the slope",
                            "mark the region support_allowed in problem.yaml with a reason"],
                           "Every occupied cell rests on the stencil below (or the bed).", does_not)
    if grid_alpha < alpha_min_deg - 1e-9:
        msg = (f"OVH-001 V NOT_CHECKED: every cell is supported, but this grid's {stencil} stencil only "
               f"guarantees {grid_alpha:.1f} deg, below the required {alpha_min_deg:.1f} deg. Use cells with "
               f"dx <= dz * tan({90 - alpha_min_deg:.0f} deg) or rely on the M check.")
        return CheckResult("OVH-001", "V", Verdict.NOT_CHECKED, msg, provisional, metrics,
                           ["re-voxelise with the D5 grid (0.503 x 0.503 x 0.6 mm)"], "", does_not)
    msg = (f"OVH-001 V PASS: every cell is supported; the {stencil} stencil on this grid guarantees "
           f">= {grid_alpha:.1f} deg from horizontal at every azimuth.")
    return CheckResult("OVH-001", "V", Verdict.PASS, msg, provisional, metrics, [],
                       f"No grid-resolved overhang flatter than {grid_alpha:.1f} deg.", does_not)


def _islands(faces: np.ndarray, mask: np.ndarray) -> list[np.ndarray]:
    """Connected groups (sharing a vertex) of the faces selected by mask, as arrays of face indices."""
    sel = np.flatnonzero(mask)
    if sel.size == 0:
        return []
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in sel:
        a, b, c = (find(int(v)) for v in faces[f])
        parent[b] = a
        parent[find(c)] = a
    roots = np.array([find(int(faces[f, 0])) for f in sel])
    return [sel[roots == r] for r in np.unique(roots)]


def check_mesh(vertices, faces, alpha_min_deg: float = 50.0, *, bed_tol_mm: float = 1e-3,
               min_island_area_mm2: float = 0.3, exclude_faces=None, provisional: bool = True,
               tol_deg: float = 0.05, bridge_alpha_max_deg: float = 0.5) -> CheckResult:
    """M level: area of downward triangles flatter than alpha_min, per triangle, grouped into islands.

    The mesh is in the print frame (z up, bed at the minimum z) with outward-oriented triangles.
    Faces lying on the bed and faces listed in exclude_faces (support_allowed regions) are skipped.
    Islands smaller than min_island_area_mm2 are reported but do not fail the check.
    tol_deg absorbs mesh precision: on a real bracket STL, faces designed at 50 deg measured
    49.96..49.9999 deg. Horizontal ceilings (alpha <= bridge_alpha_max_deg, off the bed) are printed as
    bridges, so they are reported as bridge candidates and left to BRG-001 (span and anchoring).
    """
    v = np.asarray(vertices, float)
    f = np.asarray(faces, np.int64)
    tri = v[f]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area2 = np.linalg.norm(cross, axis=1)
    signed_vol = np.einsum("ij,ij->i", tri[:, 0], cross).sum() / 6.0
    flipped = signed_vol < 0
    if flipped:                       # inward winding: flip normals so they point outwards
        cross = -cross
    ok = area2 > 0
    n = np.zeros_like(cross)
    n[ok] = cross[ok] / area2[ok, None]
    area = area2 / 2.0
    alpha = np.degrees(np.arccos(np.clip(-n[:, 2], -1.0, 1.0)))
    down = n[:, 2] < -1e-12
    on_bed = np.all(tri[:, :, 2] <= v[:, 2].min() + bed_tol_mm, axis=1)
    bad = down & ~on_bed & (alpha < alpha_min_deg - tol_deg) & ok
    if exclude_faces is not None:
        bad[np.asarray(exclude_faces)] = False
    flat = bad & (alpha <= bridge_alpha_max_deg)
    bad &= ~flat
    bridges = sorted(_islands(f, flat), key=lambda s: -area[s].sum())
    islands = sorted(_islands(f, bad), key=lambda s: -area[s].sum())
    rep = []
    for s in islands:
        pts = tri[s].reshape(-1, 3)
        rep.append({"area_mm2": float(area[s].sum()), "min_alpha_deg": float(alpha[s].min()),
                    "bbox_print_mm": [pts.min(axis=0).round(3).tolist(), pts.max(axis=0).round(3).tolist()]})
    failing = [r for r in rep if r["area_mm2"] >= min_island_area_mm2]
    total = float(sum(r["area_mm2"] for r in failing))
    bridge_rep = [{"area_mm2": float(area[s].sum()), "bbox_print_mm": [tri[s].reshape(-1, 3).min(axis=0).round(3).tolist(),
                                                                      tri[s].reshape(-1, 3).max(axis=0).round(3).tolist()]}
                  for s in bridges]
    bridge_area = float(sum(b["area_mm2"] for b in bridge_rep))
    metrics = {"alpha_min_deg": alpha_min_deg, "failing_area_mm2": total, "islands": rep,
               "min_island_area_mm2": min_island_area_mm2, "winding_flipped": bool(flipped),
               "downward_area_mm2": float(area[down & ~on_bed].sum()), "tol_deg": tol_deg,
               "bridge_candidates": bridge_rep, "bridge_candidate_area_mm2": bridge_area}
    handed = (f" {bridge_area:.1f} mm2 of horizontal ceilings in {len(bridge_rep)} region(s) are bridge candidates "
              "and are checked by BRG-001, not here.") if bridge_rep else ""
    does_not = "Whether Orca generates support (T level) or how the overhang prints on a real printer (P level)."
    if failing:
        big = failing[0]
        (x0, y0, z0), (x1, y1, z1) = big["bbox_print_mm"]
        msg = (f"OVH-001 M FAIL: {total:.1f} mm2 of downward faces are flatter than {alpha_min_deg:.0f} deg from "
               f"horizontal ({90 - alpha_min_deg:.0f} deg from vertical) in {len(failing)} island(s). Largest "
               f"island {big['area_mm2']:.1f} mm2, slope down to {big['min_alpha_deg']:.1f} deg, at print-frame "
               f"X {x0:.1f}..{x1:.1f}, Y {y0:.1f}..{y1:.1f}, Z {z0:.2f}..{z1:.2f} mm. Orca is likely to add support here."
               + handed)
        return CheckResult("OVH-001", "M", Verdict.FAIL, msg, provisional, metrics,
                           [f"steepen the underside to >= {alpha_min_deg:.0f} deg", "add a gusset or chamfer",
                            "use a teardrop for horizontal bores",
                            "mark the region support_allowed in problem.yaml with a reason"],
                           "", does_not)
    msg = (f"OVH-001 M PASS: no downward face island of >= {min_island_area_mm2} mm2 is flatter than "
           f"{alpha_min_deg:.0f} deg from horizontal (bed faces excluded)." + handed)
    return CheckResult("OVH-001", "M", Verdict.PASS, msg, provisional, metrics, [],
                       f"Every triangle off the bed slopes at >= {alpha_min_deg:.0f} deg or sits in a tiny island.",
                       does_not)
