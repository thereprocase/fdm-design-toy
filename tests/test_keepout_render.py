"""Render-only keep-out geometry (fdmgen/keepout-render@0.1): bounded, pinned, never a clearance verdict."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from fdmgen.catalog.checks.keepout import render_items

yaml = pytest.importorskip("yaml")
trimesh = pytest.importorskip("trimesh")

IFACES = [{"id": "rear_seat", "type": "rod_seat", "axis": "Z", "center_xy_mm": [90.0, 0.0]},
          {"id": "front_seat", "type": "rod_seat", "axis": "Z", "center_xy_mm": [190.0, 12.0]}]
BOX = {"id": "moulding", "type": "box", "frame": "installed", "min_mm": [0.0, None, None], "max_mm": [25.4, -32.0, None],
       "rule": "no material below Y -32 for X 0..25.4"}
SWEEP = {"id": "spool_slide", "type": "flange_sweep", "frame": "installed", "axis": "Z",
         "rod_interfaces": ["rear_seat", "front_seat"], "spool_diameter_mm": [180.0, 220.0],
         "rail_radius_mm": [12.4, 12.7], "clearance_mm": 3.5, "rule": "keep flanges sliding"}
OTHER = {"id": "later", "type": "not_derived", "frame": "installed", "note": "contract not machine-readable"}


def test_render_items_clips_open_bounds_and_samples_the_flange_like_the_check():
    g = render_items([BOX, SWEEP, OTHER], IFACES, [0.0, -50.0, -5.0], [210.0, 40.0, 30.0], margin_mm=10.0)
    assert g["clip"]["bbox_mm"] == [[-10.0, -60.0, -15.0], [220.0, 50.0, 40.0]]
    box, sweep, other = g["items"]
    assert box["min_mm"] == [0.0, -60.0, -15.0] and box["max_mm"] == [25.4, -32.0, 40.0]
    assert box["unbounded"] == ["min_y", "min_z", "max_z"] and box["original"]["min_mm"] == [0.0, None, None]
    assert len(sweep["discs"]) == 42 and sweep["coverage"]["sampled_spool_radii"] == 21          # radii 90..110 x 2 rails
    assert sweep["z_min_mm"] == -15.0 and sweep["z_max_mm"] == 40.0 and sweep["unbounded"] == ["min_z", "max_z"]
    assert sweep["discs"][0]["radius_mm"] == pytest.approx(90 + 3.5)
    assert other["rendered"] is False and "not_derived" in other["reason"]


def _case(tmp_path, *, frames=None, problem_keep_outs=None, mesh_sha=None):
    box = trimesh.creation.box(bounds=[[0, -50, -5], [210, 40, 30]])
    box.export(tmp_path / "body.stl")
    sha = hashlib.sha256((tmp_path / "body.stl").read_bytes()).hexdigest()
    table = {"mesh": {"path": "body.stl", "frame": "design", "sha256": mesh_sha or sha}, "interfaces": IFACES,
             "keep_outs": [BOX, SWEEP], "candidates": []}
    (tmp_path / "t.json").write_text(json.dumps(table), encoding="utf-8")
    prob = {"frames": frames or {"design": "installed", "installed": "X out from the wall"},
            "keep_outs": problem_keep_outs if problem_keep_outs is not None else [BOX, SWEEP]}
    (tmp_path / "p.yaml").write_text(yaml.safe_dump(prob), encoding="utf-8")


def _run(tmp_path, monkeypatch):
    from fdmgen.cli import main
    monkeypatch.setenv("SPOOL_RACK_ROOT", str(tmp_path))
    return main(["keepout-render", str(tmp_path / "t.json"), "--problem", str(tmp_path / "p.yaml"),
                 "--out", str(tmp_path / "r.json")])


def test_cli_pins_table_mesh_problem_and_states_the_identity_transform(tmp_path, monkeypatch):
    _case(tmp_path)
    assert _run(tmp_path, monkeypatch) == 0
    r = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert r["schema"] == "fdmgen/keepout-render@0.1" and r["frame"] == "design" and r["units"] == "mm"
    assert r["table"]["sha256"] == hashlib.sha256((tmp_path / "t.json").read_bytes()).hexdigest()
    assert r["problem"]["sha256"] == hashlib.sha256((tmp_path / "p.yaml").read_bytes()).hexdigest()
    assert r["installed_to_design"]["R"] == np.eye(3).tolist() and r["installed_to_design"]["t_mm"] == [0.0, 0.0, 0.0]
    assert "render only" in r["scope"] and str(tmp_path) not in (tmp_path / "r.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("bad", ["frames", "keep_outs", "mesh"])
def test_cli_refuses_what_it_cannot_vouch_for(tmp_path, monkeypatch, bad):
    _case(tmp_path, frames={"design": "print"} if bad == "frames" else None,
          problem_keep_outs=[BOX] if bad == "keep_outs" else None, mesh_sha="0" * 64 if bad == "mesh" else None)
    assert _run(tmp_path, monkeypatch) == 1 and not (tmp_path / "r.json").exists()


REAL = Path(__file__).parent / "fixtures" / "orient" / "spool-rack-g2-ef.with-keep-outs.keepout-render.json"
SRC = Path(os.environ.get("SPOOL_RACK_ROOT") or Path(__file__).resolve().parents[2] / "spool-wall-rack")


@pytest.mark.skipif(not (SRC / "designs/rev-g2/print-controls/ef-core-asa-4w-1p6/body-mounted.stl").is_file(),
                    reason="spool-wall-rack checkout not present")
def test_real_fixture_reproduces(tmp_path, monkeypatch):
    from fdmgen.cli import main
    monkeypatch.setenv("SPOOL_RACK_ROOT", str(SRC))
    repo = Path(__file__).resolve().parents[1]
    out = tmp_path / "r.json"
    assert main(["keepout-render", str(repo / "tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json"),
                 "--problem", str(repo / "problems/spool-rack-g2-ef/problem.yaml"), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == json.loads(REAL.read_text(encoding="utf-8"))


def test_a_refused_run_removes_an_older_output_file(tmp_path, monkeypatch):
    """bridge-check, shell-check and keepout-render clear --out first, so exit 1 never leaves a stale receipt."""
    _case(tmp_path, frames={"design": "print"})
    (tmp_path / "r.json").write_text('{"stale": true}', encoding="utf-8")
    assert _run(tmp_path, monkeypatch) == 1 and not (tmp_path / "r.json").exists()
    from fdmgen.cli import main
    for cmd in (["bridge-check"], ["shell-check"]):
        stale = tmp_path / f"{cmd[0]}.json"
        stale.write_text('{"stale": true}', encoding="utf-8")
        e = 0.42 * 0.2 * 10.0 / (3.141592653589793 * 1.75 ** 2 / 4)       # one valid road, footer to match
        (tmp_path / "s.gcode").write_text("; filament_diameter: 1.75\nM83\nG90\n; printing object part\n;WIDTH:0.42\n"
                                          ";HEIGHT:0.2\n;Z:0.2\nG1 Z0.2\n;TYPE:Outer wall\nG1 X0 Y0\n"
                                          f"G1 X10 Y0 E{e:.6f}\n; stop printing object part\n"
                                          f"; filament used [cm3] = {0.42 * 0.2 * 10.0 / 1000:.8f}\n", encoding="utf-8")
        argv = cmd + [str(tmp_path / "s.gcode"), "--table", str(tmp_path / "t.json"), "--pose", "missing-pose",
                      "--out", str(stale)]
        assert main(argv) == 1 and not stale.exists(), cmd
