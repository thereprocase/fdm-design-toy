"""Known-answer tests for the v0 checkers: OVH-001 (V, M), WALL-001, GAP-001, BRG-001, PROC-001 (#9)."""
import io
import json
import zipfile

import numpy as np
import pytest

from fdmgen.catalog import Verdict
from fdmgen.catalog.checks import ovh, proc

# ---------- geometry helpers ----------

def extrude_xz(poly, depth):
    """Closed, outward-wound prism from a convex CCW polygon in the XZ plane, extruded along +Y."""
    p = np.asarray(poly, float)
    n = len(p)
    v = np.vstack([np.c_[p[:, 0], np.zeros(n), p[:, 1]], np.c_[p[:, 0], np.full(n, depth), p[:, 1]]])
    faces = []
    for i in range(1, n - 1):                      # caps (fan); y = 0 cap faces -Y, y = depth faces +Y
        faces += [(0, i, i + 1), (n, n + i + 1, n + i)]
    for i in range(n):                             # sides
        j = (i + 1) % n
        faces += [(i, j + n, j), (i, i + n, j + n)]
    f = np.array(faces)
    vol = np.einsum("ij,ij->i", v[f[:, 0]], np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])).sum() / 6
    return (v, f) if vol > 0 else (v, f[:, ::-1])


def wedge(alpha_deg, height=20.0, base=10.0, depth=15.0):
    """Part standing on the bed whose overhanging underside slopes at alpha from horizontal."""
    run = height / np.tan(np.radians(alpha_deg))
    return extrude_xz([(0, 0), (base, 0), (base + run, height), (0, height)], depth)


# ---------- OVH-001 ----------

@pytest.mark.parametrize("h,stencil,expected", [
    ((1, 1, 1), "cross5", [45.0, 46.0, 49.1, 54.7]),
    ((1, 1, 1), "box9", [45.0, 39.2, 36.2, 35.3]),
    ((np.tan(np.radians(40)),) * 2 + (1,), "cross5", [50.0, 51.0, 54.0, 59.3]),
    ((np.tan(np.radians(40)),) * 2 + (1,), "box9", [50.0, 44.2, 41.1, 40.1]),
])
def test_stencil_angles_match_research_table(h, stencil, expected):
    got = [round(ovh.stencil_alpha_deg(h, phi, stencil), 1) for phi in (0, 15, 30, 45)]
    assert got == expected


def test_d5_grid_enforces_50_deg_everywhere():
    # dx = 0.503 is 0.6 * tan(40 deg) = 0.5035 rounded down, so the grid is slightly stricter than 50 deg
    worst = ovh.stencil_worst_alpha_deg((0.503, 0.503, 0.6))
    assert worst >= 50.0 and worst == pytest.approx(np.degrees(np.arctan2(0.6, 0.503)), abs=1e-9)


def _staircase(step_cells, layers=6, h=(0.503, 0.503, 0.6)):
    occ = np.zeros((40, 6, layers + 2), bool)
    for k in range(layers):
        occ[2:10 + step_cells * k, 1:5, 1 + k] = True
    return occ, h


def test_voxel_overhang_known_answers():
    occ, h = _staircase(1)                         # one cell per layer = exactly the grid angle: supported
    r = ovh.check_voxel(occ, h)
    assert r.verdict is Verdict.PASS and r.metrics["grid_alpha_deg"] == pytest.approx(50.026, abs=1e-3)
    occ, h = _staircase(2)                         # two cells per layer: one unsupported cell per row per layer
    r = ovh.check_voxel(occ, h)
    assert r.verdict is Verdict.FAIL
    assert r.metrics["unsupported_cells"] == 5 * 4  # layers 1..5, 4 rows each
    assert "nothing under them" in r.message
    occ, _ = _staircase(1)
    r = ovh.check_voxel(occ, (0.6, 0.6, 0.6))      # cubic cells: the grid can only promise 45 deg
    assert r.verdict is Verdict.NOT_CHECKED and "45.0 deg" in r.message


@pytest.mark.parametrize("alpha,verdict", [(45, Verdict.FAIL), (55, Verdict.PASS), (50, Verdict.PASS), (30, Verdict.FAIL)])
def test_mesh_wedges(alpha, verdict):
    v, f = wedge(alpha)
    r = ovh.check_mesh(v, f, 50.0)
    assert r.verdict is verdict, r.message
    if verdict is Verdict.FAIL:
        underside = 15.0 * 20.0 / np.sin(np.radians(alpha))
        assert r.metrics["failing_area_mm2"] == pytest.approx(underside, rel=1e-9)
        assert r.metrics["islands"][0]["min_alpha_deg"] == pytest.approx(alpha, abs=1e-9)
        assert "flatter than 50 deg from horizontal (40 deg from vertical)" in r.message


def test_mesh_bed_faces_winding_and_exclusion():
    v, f = wedge(45)
    r = ovh.check_mesh(v, f[:, ::-1], 50.0)       # inward winding is detected and corrected
    assert r.verdict is Verdict.FAIL and r.metrics["winding_flipped"]
    v, f = wedge(70)
    assert ovh.check_mesh(v, f).metrics["downward_area_mm2"] == pytest.approx(15 * 20 / np.sin(np.radians(70)))
    v, f = wedge(45)
    tri = v[f]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    under = np.flatnonzero((n[:, 2] < 0) & (tri[:, :, 2].max(axis=1) > 1e-6))
    assert ovh.check_mesh(v, f, exclude_faces=under).verdict is Verdict.PASS   # support_allowed region


def _box(x0, x1, z0, z1, depth=10.0):
    return extrude_xz([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], depth)


def test_mesh_horizontal_ceiling_is_handed_to_brg001():
    pv, pf = _box(0, 4, 0, 5)                       # pillar on the bed
    sv, sf = _box(-6, 10, 5, 7)                     # slab on top: 12 mm of flat underside overhangs the pillar
    v, f = np.vstack([pv, sv]), np.vstack([pf, sf + len(pv)])
    r = ovh.check_mesh(v, f, 50.0)
    assert r.verdict is Verdict.PASS, r.message
    assert r.metrics["bridge_candidate_area_mm2"] == pytest.approx(16 * 10)   # slab bottom incl. the part over the pillar
    assert "checked by BRG-001" in r.message
    r = ovh.check_mesh(v, f, 50.0, bridge_alpha_max_deg=-1)                  # hand-off disabled: flat underside fails
    assert r.verdict is Verdict.FAIL


def test_mesh_tolerance_absorbs_tessellation_but_not_real_shortfalls():
    v, f = wedge(49.97)
    assert ovh.check_mesh(v, f, 50.0).verdict is Verdict.PASS                # default tol 0.05 deg
    assert ovh.check_mesh(v, f, 50.0, tol_deg=1e-6).verdict is Verdict.FAIL
    v, f = wedge(49.9)
    assert ovh.check_mesh(v, f, 50.0).verdict is Verdict.FAIL


# ---------- WALL-001 / GAP-001 / BRG-001 ----------

layers = pytest.importorskip("fdmgen.catalog.checks.layers")
pytest.importorskip("scipy")
PX = (0.05, 0.05, 0.2)


def _mm(x):
    return round(x / PX[0])


def _block_with_fin(fin_mm):
    occ = np.zeros((_mm(12), _mm(10), 3), bool)
    occ[_mm(1):_mm(6), _mm(1):_mm(6), :] = True                        # 5 x 5 mm block
    occ[_mm(6):_mm(9), _mm(3):_mm(3) + _mm(fin_mm), :] = True           # 3 mm long fin
    return occ


@pytest.mark.parametrize("fin,verdict", [(0.6, Verdict.FAIL), (0.8, Verdict.FAIL), (0.9, Verdict.PASS), (1.2, Verdict.PASS)])
def test_wall_fin(fin, verdict):
    r = layers.check_wall(_block_with_fin(fin), PX, 0.84)
    assert r.verdict is verdict, r.message
    if verdict is Verdict.FAIL:
        assert r.metrics["layers_affected"] == 3
        lo, hi = r.metrics["bbox_print_mm"]
        assert lo[0] >= 5.9 and hi[0] <= 9.0 + 1e-9                   # flagged pixels are on the fin


def test_wall_square_and_l_shape_corners_are_not_thin():
    occ = np.zeros((_mm(10), _mm(10), 2), bool)
    occ[_mm(1):_mm(6), _mm(1):_mm(6)] = True
    occ[_mm(1):_mm(3), _mm(6):_mm(9)] = True                            # L shape: convex and concave corners
    assert layers.check_wall(occ, PX).verdict is Verdict.PASS
    assert layers.check_gap(occ, PX).verdict is Verdict.PASS


@pytest.mark.parametrize("gap,verdict", [(0.5, Verdict.FAIL), (0.8, Verdict.FAIL), (0.9, Verdict.PASS), (1.2, Verdict.PASS)])
def test_gap_slot(gap, verdict):
    occ = np.zeros((_mm(14), _mm(8), 2), bool)
    occ[_mm(1):_mm(6), _mm(1):_mm(7)] = True
    occ[_mm(6) + _mm(gap):_mm(6) + _mm(gap) + _mm(5), _mm(1):_mm(7)] = True
    r = layers.check_gap(occ, PX, 0.84)
    assert r.verdict is verdict, r.message


def test_grid_edge_is_not_a_gap():
    """Regression (real bracket run): a part one pixel from the grid edge read as a 0.1 mm gap."""
    occ = np.zeros((_mm(10), _mm(10), 2), bool)
    occ[1:-1, 1:-1] = True
    assert layers.check_gap(occ, PX).verdict is Verdict.PASS
    assert layers.check_wall(occ, PX).verdict is Verdict.PASS


def _triangle(apex_deg, height_mm=6.0):
    """Isosceles triangle with the given apex angle, base on y = 1 mm, apex up."""
    n = _mm(12)
    x, y = np.meshgrid((np.arange(n) + 0.5) * PX[0], (np.arange(n) + 0.5) * PX[1], indexing="ij")
    half = np.tan(np.radians(apex_deg / 2))
    inside = (y >= 1.0) & (y <= 1.0 + height_mm) & (np.abs(x - 6.0) <= (1.0 + height_mm - y) * half)
    return np.repeat(inside[:, :, None], 2, axis=2)


def test_corner_tips_below_min_area_are_ignored_but_spikes_are_not():
    assert layers.check_wall(_triangle(70), PX).verdict is Verdict.PASS     # residue at a 70 deg tip < 0.2 mm2
    r = layers.check_wall(_triangle(25), PX)                                # a 25 deg spike: ~1.5 mm of tip < 2w wide
    assert r.verdict is Verdict.FAIL and r.metrics["min_area_mm2"] == 0.2


def _bridge(span_mm, pillar_mm=2.0, width_mm=4.0):
    """Two pillars span_mm apart (5 layers), a deck on top: the deck's air-borne part is the bridge."""
    nx = _mm(2 * pillar_mm + span_mm + 2)
    occ = np.zeros((nx, _mm(width_mm) + 4, 7), bool)
    x0 = _mm(1)
    occ[x0:x0 + _mm(pillar_mm), 2:-2, :5] = True
    occ[x0 + _mm(pillar_mm + span_mm):x0 + _mm(2 * pillar_mm + span_mm), 2:-2, :5] = True
    occ[x0:x0 + _mm(2 * pillar_mm + span_mm), 2:-2, 5] = True
    return occ


@pytest.mark.parametrize("span,verdict", [(12.0, Verdict.FAIL), (8.0, Verdict.PASS)])
def test_bridge_span(span, verdict):
    r = layers.check_bridge(_bridge(span), PX, 10.0)
    assert r.verdict is verdict, r.message
    assert r.metrics["worst"]["span_mm"] == pytest.approx(span, abs=2 * PX[0])
    assert r.metrics["worst"]["layer"] == 5


def test_bridge_without_anchor_fails():
    occ = np.zeros((_mm(10), _mm(10), 4), bool)
    occ[_mm(1):_mm(3), _mm(1):_mm(3), 0:2] = True                     # a post
    occ[_mm(5):_mm(9), _mm(5):_mm(9), 2] = True                       # a slab in mid-air, not touching the post
    r = layers.check_bridge(occ, PX, 10.0)
    assert r.verdict is Verdict.FAIL and "no anchor" in r.message


# ---------- PROC-001 ----------

GCODE = """G1 X1 Y1 E0.1
; CONFIG_BLOCK_START
; layer_height = 0.2
; wall_loops = 4
; filament_shrink = 99.46%
; nozzle_temperature = 260,260
; enable_arc_fitting = 1
; wall_generator = arachne
; CONFIG_BLOCK_END
"""


def test_proc_settings_from_gcode_and_3mf():
    eff = proc.settings_from_gcode(GCODE)
    assert eff["filament_shrink"] == "99.46%" and eff["wall_loops"] == "4"
    ok = proc.check_settings({"layer_height": 0.2, "wall_loops": 4, "nozzle_temperature": 260,
                              "filament_shrink": "99.46%", "enable_arc_fitting": True}, eff)
    assert ok.verdict is Verdict.PASS and not ok.provisional
    bad = proc.check_settings({"wall_loops": 2, "filament_shrink": 99.46, "sparse_infill_density": "0%",
                               "wall_generator": "classic"}, eff)
    assert bad.verdict is Verdict.FAIL
    assert {m["key"] for m in bad.metrics["mismatched"]} == {"wall_loops", "filament_shrink", "wall_generator"}
    assert bad.metrics["missing"] == ["sparse_infill_density"]
    assert "wall_loops declared 2 but the slice used '4'" in bad.message
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Metadata/project_settings.config", json.dumps({"layer_height": "0.2", "wall_loops": "4"}))
    buf.seek(0)
    assert proc.check_settings({"layer_height": 0.2}, proc.settings_from_3mf(buf)).verdict is Verdict.PASS


@pytest.mark.parametrize("thick,verdict", [(1.20, Verdict.FAIL), (1.00, Verdict.PASS), (1.55, Verdict.FAIL), (1.40, Verdict.PASS)])
def test_wall002_strips_near_and_away_from_band_edges(thick, verdict):
    """1.2 mm = 2.86w sits on the 2/3-bead edge (2.85w); 1.55 mm = 3.69w on 3/4 (3.70w)."""
    px = (0.02, 0.02, 0.2)
    n = round(thick / px[0])
    occ = np.zeros((round(12 / px[0]), n + 40, 1), bool)
    occ[round(1 / px[0]):round(11 / px[0]), 20:20 + n, 0] = True
    r = layers.check_bead_bands(occ, px, line_width_mm=0.42)
    assert r.verdict is verdict, r.message


def test_wall002_taper_crosses_edges_briefly():
    px = (0.02, 0.02, 0.2)
    occ = np.zeros((600, 200, 1), bool)
    for i in range(50, 550):                               # 10 mm long, 0.6 -> 2.4 mm thick
        t = 0.6 + 1.8 * (i - 50) / 500
        half = round(t / px[0] / 2)
        occ[i, 100 - half:100 + half, 0] = True
    assert layers.check_bead_bands(occ, px).verdict is Verdict.PASS
    assert layers.bead_band_edges()[:4] == pytest.approx([1.70, 2.85, 3.70, 4.85])
