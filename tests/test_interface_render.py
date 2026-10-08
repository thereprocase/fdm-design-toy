"""Render-only interface cylinders (fdmgen/interface-render@0.1): the model check_keep_clear tests, never a verdict."""
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

from fdmgen.massing.export import interface_render_items

SEAT = {"id": "rear_seat", "type": "rod_seat", "axis": "Z", "role": "interface", "support": "forbidden",
        "center_xy_mm": [90.0, 0.0], "seat_radius_mm": [12.4, 13.6]}
BORE = {"id": "mount_upper", "type": "screw_clearance", "axis": "X", "role": "interface", "support": "forbidden",
        "center_yz_mm": [164.0, 12.0], "d_mm": 5.2}
LO, HI = [-10.0, -60.0, -10.0], [220.0, 190.0, 34.0]


def test_items_carry_the_check_model_and_clip_only_the_drawn_axis():
    seat, bore = interface_render_items([SEAT, BORE], LO, HI)
    assert seat["base_radius_mm"] == 13.6 and "largest seat radius" in seat["model"]
    assert seat["axis_start_mm"] == [90.0, 0.0, -10.0] and seat["axis_end_mm"] == [90.0, 0.0, 34.0]
    assert seat["unbounded"] == ["min_z", "max_z"] and seat["source_fields"] == {"seat_radius_mm": [12.4, 13.6]}
    assert bore["base_radius_mm"] == pytest.approx(2.6) and "washer and driver access are not modelled" in bore["model"]
    assert bore["axis_start_mm"] == [-10.0, 164.0, 12.0] and bore["axis_end_mm"] == [220.0, 164.0, 12.0]
    assert bore["centre_plane"] == {"key": "center_yz_mm", "value": [164.0, 12.0]}


def test_y_axis_and_undrawable_interfaces():
    y = {"id": "pin", "type": "screw_clearance", "axis": "Y", "center_xz_mm": [5.0, 6.0], "d_mm": 3.0}
    unknown = {"id": "snap", "type": "snap_fit", "axis": "Z", "center_xy_mm": [0.0, 0.0]}
    nocentre = {"id": "lost", "type": "rod_seat", "axis": "Z", "seat_radius_mm": [5.0]}
    a, b, c = interface_render_items([y, unknown, nocentre], LO, HI)
    assert a["axis_start_mm"] == [5.0, -60.0, 6.0] and a["axis_end_mm"] == [5.0, 190.0, 6.0]
    assert b["rendered"] is False and "snap_fit" in b["reason"]
    assert c["rendered"] is False and "centre missing" in c["reason"]


@pytest.mark.parametrize("bad,match", [
    ([SEAT, dict(SEAT)], "not unique"),
    ([dict(SEAT, seat_radius_mm=[12.4, math.inf])], "finite and positive"),
    ([dict(BORE, d_mm=0)], "finite and positive"),
    ([dict(BORE, d_mm=-5.2)], "finite and positive"),
    ([dict(SEAT, center_xy_mm=[90.0, math.nan])], "two finite numbers"),
    ([dict(SEAT, center_xy_mm=[90.0])], "two finite numbers"),
])
def test_refuses_geometry_the_check_would_not_test(bad, match):
    with pytest.raises(ValueError, match=match):
        interface_render_items(bad, LO, HI)
    with pytest.raises(ValueError, match="not finite"):
        interface_render_items([SEAT], [0, 0, math.nan], HI)


def _cli_case(tmp_path, interfaces):
    trimesh = pytest.importorskip("trimesh")
    yaml = pytest.importorskip("yaml")
    trimesh.creation.box(bounds=[[0, -50, 0], [210, 180, 24]]).export(tmp_path / "body.stl")
    sha = hashlib.sha256((tmp_path / "body.stl").read_bytes()).hexdigest()
    table = {"mesh": {"path": "body.stl", "frame": "design", "sha256": sha}, "interfaces": interfaces,
             "keep_outs": [], "candidates": []}
    (tmp_path / "t.json").write_text(json.dumps(table), encoding="utf-8")
    (tmp_path / "p.yaml").write_text(yaml.safe_dump({"frames": {"design": "installed"}, "keep_outs": []}),
                                     encoding="utf-8")


def _cli(tmp_path, monkeypatch, *extra):
    from fdmgen.cli import main
    monkeypatch.setenv("SPOOL_RACK_ROOT", str(tmp_path))
    return main(["interface-render", str(tmp_path / "t.json"), "--problem", str(tmp_path / "p.yaml"),
                 "--out", str(tmp_path / "r.json"), *extra])


def test_cli_pins_and_states_scope(tmp_path, monkeypatch):
    _cli_case(tmp_path, [SEAT, BORE])
    assert _cli(tmp_path, monkeypatch) == 0
    r = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert r["schema"] == "fdmgen/interface-render@0.1" and r["frame"] == "design" and r["units"] == "mm"
    assert r["clip"]["bbox_mm"] == [[-10.0, -60.0, -10.0], [220.0, 190.0, 34.0]] and r["clip"]["margin_mm"] == 10.0
    assert "per-helper clearance is not included" in r["scope"]
    assert r["installed_to_design"]["R"] == np.eye(3).tolist()
    assert str(tmp_path) not in (tmp_path / "r.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("case", ["dup", "margin"])
def test_cli_refusals_leave_no_file(tmp_path, monkeypatch, case):
    _cli_case(tmp_path, [SEAT, SEAT] if case == "dup" else [SEAT])
    (tmp_path / "r.json").write_text("{}", encoding="utf-8")
    extra = ("--margin", "nan") if case == "margin" else ()
    assert _cli(tmp_path, monkeypatch, *extra) == 1 and not (tmp_path / "r.json").exists()


REAL = Path(__file__).parent / "fixtures" / "orient" / "spool-rack-g2-ef.with-keep-outs.interface-render.json"
SRC = Path(os.environ.get("SPOOL_RACK_ROOT") or Path(__file__).resolve().parents[2] / "spool-wall-rack")


@pytest.mark.skipif(not (SRC / "designs/rev-g2/print-controls/ef-core-asa-4w-1p6/body-mounted.stl").is_file(),
                    reason="spool-wall-rack checkout not present")
def test_real_fixture_reproduces(tmp_path, monkeypatch):
    from fdmgen.cli import main
    monkeypatch.setenv("SPOOL_RACK_ROOT", str(SRC))
    repo = Path(__file__).resolve().parents[1]
    out = tmp_path / "r.json"
    assert main(["interface-render", str(repo / "tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json"),
                 "--problem", str(repo / "problems/spool-rack-g2-ef/problem.yaml"), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == json.loads(REAL.read_text(encoding="utf-8"))
