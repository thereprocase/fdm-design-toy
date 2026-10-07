"""SHELL-001 at T level: printed shell thickness measured along the surface normal in the real slice.

The catalog makes T binding for SHELL-001: at least min_beads solid beads normal to every surface, after
the slicer's own shell logic. Input is a density grid of the slice's credited roads in the print frame
(fdmgen.gcode.occupancy) and the body mesh in the same frame. Surface points are sampled (area-weighted,
fixed seed) and the printed thickness is the equivalent solid thickness along the inward normal: the
integral of the capped density from the first material until the ray is empty for a full cell. The
requirement along a normal at slope alpha (0 = horizontal face, 90 = vertical) is the extent of min_beads
beads: min_beads x (bead_spacing sin alpha + layer cos alpha), with the flow spacing (not the nominal
width) between neighbouring walls: a 2-wall shell is about 0.81 mm.
Results are reported in slope bands, which is where the t(alpha) mid-slope thin band shows up.
"""
from __future__ import annotations

import numpy as np

from ..result import CheckResult, Verdict


def sample_surface(vertices, faces, n: int, seed: int = 0):
    """Area-weighted surface points and outward unit normals."""
    tri = np.asarray(vertices, float)[np.asarray(faces)]
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cr, axis=1)
    vol = np.einsum("ij,ij->i", tri[:, 0], cr).sum()
    nrm = (cr if vol > 0 else -cr) / np.maximum(area, 1e-30)[:, None]
    rng = np.random.default_rng(seed)
    k = rng.choice(len(tri), size=n, p=area / area.sum())
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    p = tri[k, 0] + u[:, None] * (tri[k, 1] - tri[k, 0]) + v[:, None] * (tri[k, 2] - tri[k, 0])
    return p, nrm[k], float(area.sum() / 2)


# The deposit raster point-samples each bead at (k + 0.5) / n fractions of its width and height. When a cell
# edge coincides exactly with those sample coordinates (round G-code numbers on a round grid), floor() ties
# split a layer unevenly between two cells and a ray at one height reads a 0.65 / 1.29 density alternation.
# Mass is conserved, but a single ray is not. Offsetting the grid by an irrational fraction of a micron makes
# exact ties impossible at G-code precision and moves nothing measurable.
TIE_BREAK_MM = 1e-4 * np.pi


def grid_origin(lo, pad_mm: float = 1.0):
    """Shell-check grid origin: pad below the body's lower corner, plus the tie-breaking offset."""
    return np.asarray(lo, float) - pad_mm + TIE_BREAK_MM


def march(density, origin, h, points, inward, *, step_mm=0.025, max_mm=4.0, threshold=0.5, entry_mm=None,
          empty=0.05):
    """Equivalent solid thickness (mm) along the inward normal: the integral of min(density, 1) from the first
    material until the ray has been empty (density < `empty`) for a full cell. Integrating instead of
    thresholding makes the result independent of where cell edges fall against bead edges (a threshold
    march on a raster a quarter of a bead wide aliases). Material must start within entry_mm (default 1.5
    cells) of the surface, else 0; nan where the ray leaves the grid. `threshold` is kept for the record."""
    h = np.broadcast_to(np.asarray(h, float), (3,))
    cell = float(h.max())
    entry = 1.5 * cell if entry_mm is None else entry_mm
    shape = np.asarray(density.shape)
    total = np.zeros(len(points))
    gap = np.zeros(len(points))
    entered = np.zeros(len(points), bool)
    alive = np.ones(len(points), bool)
    for s in np.arange(step_mm / 2, max_mm, step_mm):
        q = points + inward * s
        idx = np.floor((q - origin) / h).astype(int)
        inside = np.all((idx >= 0) & (idx < shape), axis=1)
        d = np.zeros(len(points))
        d[inside] = density[tuple(idx[inside].T)]
        total[alive & ~inside] = np.nan
        alive &= inside
        never = alive & ~entered & (d < empty) & (s > entry)
        total[never] = 0.0
        alive &= ~never
        entered |= alive & (d >= empty)
        on = alive & entered
        total[on] += np.minimum(d[on], 1.0) * step_mm
        gap[on] = np.where(d[on] < empty, gap[on] + step_mm, 0.0)
        alive &= ~(on & (gap >= cell))
        if not alive.any():
            break
    return total


def check_shell(density, origin, h, vertices, faces, *, n_samples=20000, min_beads=2, bead_spacing_mm=0.38,
                layer_mm=0.2, threshold=0.5, thin_fraction_limit=0.01, seed=0, provisional=True) -> CheckResult:
    p, n, area = sample_surface(vertices, faces, n_samples, seed)
    t = march(density, np.asarray(origin, float), h, p, -n, threshold=threshold)
    alpha = np.degrees(np.arccos(np.clip(np.abs(n[:, 2]), 0, 1)))
    need = min_beads * (bead_spacing_mm * np.sin(np.radians(alpha)) + layer_mm * np.cos(np.radians(alpha)))
    ok = np.isfinite(t)
    thin = ok & (t < need - 1e-9)
    bands = []
    for lo in range(0, 90, 10):
        b = ok & (alpha >= lo) & (alpha < lo + 10 if lo < 80 else alpha <= 90)
        if b.any():
            bands.append({"slope_deg": [lo, lo + 10], "samples": int(b.sum()), "thin_fraction": round(float(thin[b].mean()), 4),
                          "median_mm": round(float(np.median(t[b])), 3), "p05_mm": round(float(np.quantile(t[b], 0.05)), 3),
                          "required_mm": round(float(np.median(need[b])), 3)})
    frac = float(thin[ok].mean()) if ok.any() else float("nan")
    metrics = {"samples": int(ok.sum()), "unmeasured": int((~ok).sum()), "thin_fraction": round(frac, 4),
               "thin_area_mm2_est": round(frac * area, 1), "bands": bands, "min_beads": min_beads,
               "bead_spacing_mm": bead_spacing_mm, "layer_mm": layer_mm, "threshold": threshold}
    worst = max(bands, key=lambda b: b["thin_fraction"]) if bands else None
    does_not = ("Bond quality between those beads, or anything finer than the raster cell; the raster is an approximation "
                "of the slicer's roads.")
    if ok.any() and frac > thin_fraction_limit:
        msg = (f"SHELL-001 T FAIL: {100 * frac:.1f} % of the sampled surface (about {frac * area:.0f} mm2) has less than "
               f"{min_beads} beads of printed material along its normal; worst slope band {worst['slope_deg']} deg "
               f"({100 * worst['thin_fraction']:.0f} % thin, median {worst['median_mm']} mm vs {worst['required_mm']} mm needed).")
        return CheckResult("SHELL-001", "T", Verdict.FAIL, msg, provisional, metrics,
                           ["add walls or skins for those slopes, or check ensure_vertical_shell_thickness",
                            "or back the band with a helper volume"], "", does_not)
    msg = (f"SHELL-001 T PASS: {100 * frac:.1f} % of the sampled surface is thinner than {min_beads} beads "
           f"(limit {100 * thin_fraction_limit:.0f} %).")
    return CheckResult("SHELL-001", "T", Verdict.PASS, msg, provisional, metrics, [],
                       f"At least {min_beads} beads of printed material along the normal almost everywhere.", does_not)
