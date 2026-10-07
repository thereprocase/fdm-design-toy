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


def test_keepout_triangle_box_known_answers():
    from fdmgen.catalog.checks.keepout import triangles_overlap_box
    lo, hi = np.array([0.0, 0, 0]), np.array([1.0, 1, 1])
    tri = np.array([
        [[0.2, 0.2, 0.2], [0.3, 0.2, 0.2], [0.2, 0.3, 0.2]],          # fully inside
        [[-1, 0.5, 0.5], [2, 0.5, 0.5], [0.5, 0.5, 3]],               # crosses the box, no vertex inside
        [[1.5, -0.4, 0.5], [-0.4, 1.5, 0.5], [1.6, 1.6, 0.5]],         # bbox overlaps, triangle clear of the corner? (crosses)
        [[1.2, 0.0, 0.5], [2.0, 0.0, 0.5], [2.0, -0.9, 0.5]],          # outside
        [[0.9, 1.9, 0.5], [1.9, 0.9, 0.5], [1.9, 1.9, 0.5]],           # bbox overlaps the box, triangle does not
    ])
    assert triangles_overlap_box(tri, lo, hi).tolist() == [True, True, True, False, False]


def test_keepout_body_contact_is_not_intrusion():
    from fdmgen.catalog.checks.keepout import check_body, check_boxes
    v = np.array([[x, y, z] for x in (0, 10) for y in (0, 10) for z in (0, 10)], float)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    touching = {"id": "below", "type": "box", "frame": "installed", "min_mm": [None, None, None], "max_mm": [None, None, 0.0]}
    entering = {"id": "corner", "type": "box", "frame": "installed", "min_mm": [8.0, None, None], "max_mm": [None, 2.0, None]}
    unknown = {"id": "sweep", "type": "not_derived", "frame": "installed"}
    r = {x.metrics["keep_out_id"]: x.verdict for x in check_body(v, f, [touching, entering, unknown])}
    assert r == {"below": Verdict.PASS, "corner": Verdict.FAIL, "sweep": Verdict.NOT_CHECKED}
    b = check_boxes({"h1": (np.array([9.0, 0, 0]), np.array([12.0, 3, 5])), "h2": (np.array([0.0, 5, 0]), np.array([2.0, 7, 5]))},
                    [entering], v.min(axis=0), v.max(axis=0))
    assert {x.metrics["helper_id"]: x.verdict for x in b} == {"h1": Verdict.FAIL, "h2": Verdict.PASS}


def test_flange_sweep_matches_the_load_model_and_catches_intrusions():
    from fdmgen.adapters import spool_bracket as sb
    from fdmgen.catalog.checks.keepout import check_body, check_boxes, flange_discs
    ifs = [{"id": k, "center_xy_mm": list(v)} for k, v in sb.ROD_AXES_I.items()]
    ko = {"id": "spool_slide", "type": "flange_sweep", "frame": "installed", "rod_interfaces": list(sb.ROD_AXES_I),
          "spool_diameter_mm": [180.0, 220.0], "rail_radius_mm": [12.4, 12.7], "clearance_mm": 3.5, "rule": "test"}
    cs, rs = flange_discs(ko, ifs)
    span = np.hypot(100, 12)
    rise = np.sqrt((90 + 12.4) ** 2 - span ** 2 / 4)                       # interface_loads: 180 mm spool, 12.4 rail
    assert cs[0] == pytest.approx([140 - 12 * rise / span, 6 + 100 * rise / span])
    assert rs[0] == pytest.approx(93.5) and len(cs) == 42
    c = cs[0]
    inside = np.array([[c[0] - 1, c[1], 0], [c[0] + 1, c[1], 0], [c[0], c[1] + 1, 5]])     # near the spool centre
    far = np.array([[0, -50, 0], [5, -50, 0], [0, -45, 5]])
    v = np.vstack([inside, far])
    r = check_body(v, np.array([[0, 1, 2], [3, 4, 5]]), [ko], interfaces=ifs)
    assert r[0].verdict is Verdict.FAIL and r[0].metrics["triangles_inside"] == 1
    assert check_body(far, np.array([[0, 1, 2]]), [ko], interfaces=ifs)[0].verdict is Verdict.PASS
    b = check_boxes({"in": (np.array([c[0] - 1, c[1] - 1, 0]), np.array([c[0] + 1, c[1] + 1, 5])),
                     "out": (np.array([0, -60, 0]), np.array([5, -50, 5]))}, [ko], v.min(axis=0), v.max(axis=0), interfaces=ifs)
    assert {x.metrics["helper_id"]: x.verdict for x in b} == {"in": Verdict.FAIL, "out": Verdict.PASS}


def _pads_and_bridge(gap, role="Bridge"):
    """Layer 1: two 5 mm pads `gap` apart (solid lines). Layer 2: bridge roads across both pads."""
    import math
    area = math.pi * 1.75 ** 2 / 4

    def road(x0, y0, x1, y1, w=0.42, h=0.2):
        return [f"G1 X{x0:.3f} Y{y0:.3f}", f"G1 X{x1:.3f} Y{y1:.3f} E{w * h * math.hypot(x1 - x0, y1 - y0) / area:.6f}"]
    g = ["; filament_diameter: 1.75", "M83", "G90", "; printing object part", ";WIDTH:0.42", ";HEIGHT:0.2",
         ";Z:0.2", "G1 Z0.2", ";TYPE:Internal solid infill"]
    for x0 in (0.0, 5.0 + gap):
        for y in np.arange(0.21, 5.0, 0.4):
            g += road(x0 + 0.21, y, x0 + 4.79, y)
    g += [";Z:0.4", "G1 Z0.4", f";TYPE:{role}"]
    for y in np.arange(0.21, 5.0, 0.4):
        g += road(1.0, y, 9.0 + gap, y)
    g.append("; stop printing object part")
    from fdmgen.gcode import read_gcode
    return read_gcode("\n".join(g) + "\n", footer_rel_tol=None)


@pytest.mark.parametrize("gap,role,verdict", [(8.0, "Bridge", "PASS"), (12.0, "Bridge", "FAIL"),
                                              (12.0, "Internal Bridge", "PASS"), (20.0, "Internal Bridge", "FAIL")])
def test_brg001_t_measures_the_unsupported_run_over_the_layer_below(gap, role, verdict):
    from fdmgen.catalog.checks.toolpath import bridge_spans, check_bridge_toolpath
    tp = _pads_and_bridge(gap, role)
    rows = bridge_spans(tp)
    assert len(rows) == 12 and all(abs(r["span_mm"] - gap) <= 0.15 for r in rows)    # one cell of raster error
    assert all(r["cantilever_mm"] == 0.0 for r in rows)                               # anchored on both pads
    r = check_bridge_toolpath(tp)
    assert r.verdict.value == verdict and r.level == "T" and r.rule == "BRG-001"


def test_brg001_t_defaults_match_the_catalog():
    import inspect

    from fdmgen.catalog import load_rules
    from fdmgen.catalog.checks.toolpath import check_bridge_toolpath
    rule = load_rules()["BRG-001"]
    sig = inspect.signature(check_bridge_toolpath).parameters
    assert sig["max_span_external_mm"].default == rule.parameters["max_span_external_mm"]["value"]
    assert sig["max_span_internal_mm"].default == rule.parameters["max_span_internal_mm"]["value"]
    assert rule.data["checkers"]["T"] == "fdmgen.catalog.checks.toolpath.check_bridge_toolpath"


def _stepped_part_and_slice():
    """A 10 mm long part whose width steps: 10 mm up to z 2.1, 5 mm to z 4 (two stacked boxes, no triangulation
    engine needed); and a perimeter-only slice of it in that pose. Flipped about X it has the same footprint
    and extent but other sections."""
    import itertools
    import math

    trimesh = pytest.importorskip("trimesh")
    pytest.importorskip("shapely")
    from fdmgen.gcode import read_gcode
    low = trimesh.creation.box(bounds=[[0, 0, 0], [10, 10, 2.1]])
    high = trimesh.creation.box(bounds=[[0, 0, 2.1], [10, 5, 4.0]])
    both = trimesh.util.concatenate([low, high])
    V, F = both.vertices, both.faces
    area = math.pi * 1.75 ** 2 / 4
    g = ["; filament_diameter: 1.75", "M83", "G90", "; printing object part", ";WIDTH:0.42", ";HEIGHT:0.2"]
    for k in range(1, 21):
        z = round(0.2 * k, 3)
        y1 = 10 - 0.21 if z <= 2.1 else 5 - 0.21
        pts = [(0.21, 0.21), (9.79, 0.21), (9.79, y1), (0.21, y1), (0.21, 0.21)]
        g += [f";Z:{z}", f"G1 Z{z}", ";TYPE:Outer wall", f"G1 X{pts[0][0]} Y{pts[0][1]}"]
        for (x0, y0), (x, y) in itertools.pairwise(pts):
            g.append(f"G1 X{x} Y{y} E{0.42 * 0.2 * math.hypot(x - x0, y - y0) / area:.6f}")
    g.append("; stop printing object part")
    return V, F, read_gcode("\n".join(g) + "\n", footer_rel_tol=None)


def test_verify_pose_tells_a_flip_from_the_right_pose():
    from fdmgen.catalog.checks.toolpath import verify_pose
    V, F, tp = _stepped_part_and_slice()
    ok = verify_pose(tp, V, F)
    assert len(ok["bands"]) == 5 and all(b["inside_fraction"] == 1.0 for b in ok["bands"])
    flipped = V @ np.diag([1.0, -1.0, -1.0]).T + np.array([0.0, 10.0, 4.0])          # same footprint, same extent
    assert np.allclose(flipped.min(axis=0), V.min(axis=0)) and np.allclose(flipped.max(axis=0), V.max(axis=0))
    with pytest.raises(ValueError, match="not that pose"):
        verify_pose(tp, flipped, F[:, ::-1])                                           # the mirror flips winding


def _channel(role="Bridge"):
    """Layer 1: a U of support, two 5 mm strips 3 mm apart (x 0..5 and 8..13, y 0..30) joined by end caps.
    Layer 2: bridge strands laid ALONG the 3 mm channel (x 5.5, 6.5, 7.5), anchored only at the caps."""
    import math

    from fdmgen.gcode import read_gcode
    area = math.pi * 1.75 ** 2 / 4

    def road(x0, y0, x1, y1):
        return [f"G1 X{x0:.3f} Y{y0:.3f}", f"G1 X{x1:.3f} Y{y1:.3f} E{0.42 * 0.2 * math.hypot(x1 - x0, y1 - y0) / area:.6f}"]
    g = ["; filament_diameter: 1.75", "M83", "G90", "; printing object part", ";WIDTH:0.42", ";HEIGHT:0.2",
         ";Z:0.2", "G1 Z0.2", ";TYPE:Internal solid infill"]
    for x in np.arange(0.21, 5.0, 0.4):
        g += road(x, 0.21, x, 29.79) + road(x + 8.0, 0.21, x + 8.0, 29.79)
    for y in (0.21, 0.61, 1.01, 1.41, 1.79, 28.21, 28.61, 29.01, 29.41, 29.79):
        g += road(5.0, y, 8.0, y)
    g += [";Z:0.4", "G1 Z0.4", f";TYPE:{role}"]
    for x in (5.5, 6.5, 7.5):
        g += road(x, 0.6, x, 29.4)
    g.append("; stop printing object part")
    return read_gcode("\n".join(g) + "\n", footer_rel_tol=None)


def test_brg001_t_reports_strand_and_ceiling_spans_for_strands_along_a_channel():
    """The strand hangs 26 mm between the end caps; as a ceiling the channel is only 3 mm wide."""
    from fdmgen.catalog.checks.toolpath import bridge_spans, check_bridge_toolpath
    tp = _channel()
    rows = bridge_spans(tp)
    assert len(rows) == 3 and all(abs(r["span_mm"] - 26.0) <= 0.2 for r in rows)
    mid = next(r for r in rows if abs(tp.start[r["road_index"], 0] - 6.5) < 1e-6)
    assert mid["ceiling_span_mm"] == pytest.approx(3.0, abs=0.25)          # 1.5 mm to either strip
    r = check_bridge_toolpath(tp)
    assert r.verdict.value == "FAIL"                                        # the verdict uses the strand model
    assert r.metrics["max_ceiling_span_external_mm"] < 3.3
