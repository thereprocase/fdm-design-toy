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
    assert r.metrics["per_region"]["_unassigned"]["support_segments"] == 0
    r = check_support(tp, {"a": ([22, 10], [30, 30]), "b": ([20, 10], [30, 20])}, design)   # overlapping regions
    assert r.metrics["per_region"]["_unassigned"]["support_segments"] == 0                 # never negative
    with pytest.raises(ValueError, match="does not match the design"):
        locate(tp, [10, 10], [40, 30])
    assert area > 0


FIX = __import__("pathlib").Path(__file__).parent / "fixtures" / "coupons"


def test_plate_fixture_matches_the_generator_and_evidence_contract():
    import json
    plate_json = json.loads((FIX / "ladder-plate.json").read_text())
    _, meta = plate()
    assert plate_json["schema"] == "fdmgen/coupon-plate@0.1" and plate_json["frame"] == "print"
    assert [r["id"] for r in plate_json["rungs"]] == [m["id"] for m in meta]
    for name in ("slice-evidence-support45.json", "slice-evidence-nosupport.json"):
        ev = json.loads((FIX / name).read_text())
        assert ev["schema"] == "fdmgen/slice-evidence@0.1" and ev["tier"] == "S"
        assert {"plate", "gcode", "placement", "rungs", "establishes", "does_not_establish"} <= set(ev)
        assert ev["gcode"]["version"] == "2.4.2" and "support_threshold_angle" in ev["gcode"]["settings"]
        assert [r["id"] for r in ev["rungs"]] == [m["id"] for m in meta]
        assert max(abs(x) for x in ev["placement"]["shift_xy_mm"]) < 0.1
    s45 = {r["id"]: r for r in json.loads((FIX / "slice-evidence-support45.json").read_text())["rungs"]}
    assert [s45[f"ovh-{a}"]["support_segments"] > 0 for a in (35, 40, 45, 50, 55, 60)] == [True] * 3 + [False] * 3
    nos = json.loads((FIX / "slice-evidence-nosupport.json").read_text())["rungs"]
    for r in nos:
        if r["kind"] == "bridge":          # every span bridged with ~2.45 mm anchors at each end
            assert r["longest_bridge_road_mm"] == pytest.approx(r["span_mm"] + 4.9, abs=0.2)


def test_channel_ladder_bars_are_closed_and_their_voids_are_nominal():
    from fdmgen.coupons import channel_plate
    (v, f), meta = channel_plate()
    assert [m["id"] for m in meta] == ["chn-04", "chn-08", "chn-12", "chn-16"]
    tri = v[f]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
    expect = sum((m["void_mm"] + 2 * m["shell_mm"]) * m["length_mm"] * m["height_mm"] for m in meta)
    assert vol == pytest.approx(expect, rel=1e-9)                              # outward-wound closed bars
    for m in meta:
        (cx0, cy0, _), (cx1, cy1, _) = m["channel_bbox_mm"]
        assert cx1 - cx0 == pytest.approx(m["void_mm"]) and cy1 - cy0 == pytest.approx(m["length_mm"] - 2 * m["shell_mm"])
    assert v[:, 0].min() + v[:, 0].max() == pytest.approx(256.0) and v[:, 2].min() == 0.0      # bed-centred, on the bed


def test_channel_row_counts_strand_direction_by_length_not_by_road():
    """Across-strands joined by short lengthwise connectors: by road count half run along, by length almost none."""
    from types import SimpleNamespace

    from fdmgen.coupons.evidence import _channel_row
    start, end, spans = [], [], []
    for k in range(10):
        y = 10.0 + 0.45 * k
        start += [(1.0, y, 0.4), (9.0, y, 0.4)]
        end += [(9.0, y, 0.4), (9.0, y + 0.45, 0.4)]                      # strand across, then a 0.45 mm connector
        spans += [{"road_index": 2 * k, "span_mm": 7.5, "ceiling_span_mm": 7.6, "z_mm": 0.4},
                  {"road_index": 2 * k + 1, "span_mm": 0.0, "ceiling_span_mm": 0.5, "z_mm": 0.4}]
    tp = SimpleNamespace(start=np.array(start), end=np.array(end))
    rung = {"channel_bbox_mm": [[0.0, 0.0, 0.0], [10.0, 30.0, 8.0]]}
    row = _channel_row(rung, spans, tp, (0.0, 0.0, 0.0), np.zeros(2))
    assert row["bridge_roads"] == 20 and row["length_fraction_along"] == pytest.approx(4.5 / 84.5, abs=1e-4)
    assert row["strand_span_max_mm"] == 7.5 and row["ceiling_span_max_mm"] == 7.6
