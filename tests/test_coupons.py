"""Printability ladders (#12): each rung's defining number is recovered by the catalog checkers."""
import numpy as np
import pytest

from fdmgen.catalog import Verdict
from fdmgen.catalog.checks import ovh
from fdmgen.coupons import bridge_ladder, overhang_ladder, plate, write_stl


def test_overhang_rungs_fail_below_50_and_report_their_angle():
    (v, f), meta = overhang_ladder()
    r = ovh.check_mesh(v, f, 50.0)
    assert r.verdict is Verdict.FAIL
    failing = [i for i in r.metrics["islands"] if i["area_mm2"] >= 0.3]
    by_rung = {}
    for isl in failing:
        cx = (isl["bbox_print_mm"][0][0] + isl["bbox_print_mm"][1][0]) / 2
        rung = next(m for m in meta if m["bbox_mm"][0][0] <= cx <= m["bbox_mm"][1][0])
        by_rung[rung["id"]] = isl
    assert sorted(by_rung) == ["ovh-35", "ovh-40", "ovh-45"]
    for m in meta:
        if m["id"] in by_rung:
            assert by_rung[m["id"]]["min_alpha_deg"] == pytest.approx(m["alpha_deg"], abs=1e-9)
            assert by_rung[m["id"]]["area_mm2"] == pytest.approx(m["underside_area_mm2"], rel=1e-9)


def _raster(boxes, px=0.1, dz=0.2, size=(140, 110, 12)):
    nx, ny, nz = (round(s / d) for s, d in zip(size, (px, px, dz)))
    occ = np.zeros((nx, ny, nz), bool)
    for (x0, y0, z0), (x1, y1, z1) in boxes:
        occ[round(x0 / px):round(x1 / px), round(y0 / px):round(y1 / px),
            round(z0 / dz):round(z1 / dz)] = True
    return occ, (px, px, dz)


def test_bridge_rungs_span_their_design_length():
    pytest.importorskip("scipy")
    from fdmgen.catalog.checks import layers
    (_v, _f), meta = bridge_ladder()
    for m in meta:
        (x0, y0, _), (x1, y1, z1) = m["bbox_mm"]
        (bx0, _, z0), (bx1, _, _) = m["bridge_bbox_mm"]
        occ, h = _raster([((x0, y0, 0), (bx0, y1, z0)), ((bx1, y0, 0), (x1, y1, z0)), ((x0, y0, z0), (x1, y1, z1))])
        r = layers.check_bridge(occ, h, 10.0)
        assert r.metrics["worst"]["span_mm"] == pytest.approx(m["span_mm"], abs=2 * h[0]), m["id"]
        assert (r.verdict is Verdict.FAIL) == (m["span_mm"] > 10.0 + 2 * h[0])


def test_plate_fits_the_p1s_and_stl_roundtrip(tmp_path):
    (v, f), meta = plate()
    assert v.min(axis=0)[2] == 0.0 and max(np.ptp(v[:, :2], axis=0)) <= 236.0
    assert np.allclose((v[:, :2].min(axis=0) + v[:, :2].max(axis=0)) / 2, [128, 128])
    assert v[:, 0].min() > 18 or v[:, 1].min() > 28                       # clear of the exclusion zone
    for m in meta:                                                           # metadata moved with the geometry
        lo, hi = np.array(m["bbox_mm"])
        inside = np.all((v >= lo - 1e-9) & (v <= hi + 1e-9), axis=1)
        assert inside.any()
    assert len(meta) == 13 and len({m["id"] for m in meta}) == 13
    p = tmp_path / "plate.stl"
    write_stl(p, v, f, "fdmgen ladder plate")
    assert p.stat().st_size == 84 + 50 * len(f)
    trimesh = pytest.importorskip("trimesh")
    m = trimesh.load(p)
    assert m.volume == pytest.approx(sum(s.volume for s in m.split(only_watertight=True)), rel=1e-6)
    assert all(s.is_watertight and s.volume > 0 for s in m.split(only_watertight=False))


def test_toolpath_support_check_and_placement_guard():
    from fdmgen.catalog.checks.toolpath import check_support, locate
    from fdmgen.gcode import read_gcode
    area = 3.141592653589793 * 1.75 ** 2 / 4
    g = ("; filament_diameter: 1.75\nM83\nG90\n; printing object part\n;TYPE:Outer wall\n;Z:0.2\n;HEIGHT:0.2\n"
         "G1 X10.21 Y10.21 Z0.2\nG1 X29.79 Y10.21 E1\nG1 X29.79 Y29.79 E1\nG1 X10.21 Y29.79 E1\nG1 X10.21 Y10.21 E1\n"
         ";TYPE:Support\nG1 X25 Y12\nG1 X25 Y15 E0.5\nG1 X25 Y18 E0.5\n; stop printing object part\n")
    tp = read_gcode(g, footer_rel_tol=None)
    design = ([10, 10, 0], [30, 30, 5])                   # a 20 x 20 mm part; outer wall centreline 0.21 inside
    assert locate(tp, design[0][:2], design[1][:2]) == pytest.approx([0, 0], abs=1e-9)
    r = check_support(tp, {"left": ([10, 10], [18, 30]), "right": ([22, 10], [30, 30])}, design)
    assert r.verdict is Verdict.FAIL and "right" in r.message and "left" not in r.message
    assert r.metrics["per_region"]["right"]["support_segments"] == 2
    with pytest.raises(ValueError, match="does not match the design"):
        locate(tp, [10, 10], [40, 30])
    assert area > 0
