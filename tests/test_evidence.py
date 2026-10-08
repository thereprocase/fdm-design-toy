"""Evidence bundle manifest: receipts pinned by hash, verdicts, paired deltas, refusal on command errors."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from fdmgen import evidence

FIX = Path(__file__).parent / "fixtures"


def _canned(monkeypatch, *, broken=None, change_method=False, tweak=None):
    """Replace the heavy commands with real receipt fixtures copied to --out. The shell fixture is 0.2, so it
    borrows the bridge fixture's real placement block (same slice, same pose) to stand in for a 0.3 receipt."""
    shell = json.loads((FIX / "shell" / "facet-00-shell-only.shell-check.json").read_text(encoding="utf-8"))
    bridge = json.loads((FIX / "bridge" / "facet-00-shell-only.bridge-check.json").read_text(encoding="utf-8"))
    shell["schema"], shell["placement"] = "fdmgen/shell-check@0.3", bridge["placement"]
    helpers = json.loads((FIX / "massing" / "sample-slice-evidence.json").read_text(encoding="utf-8"))
    calls = []

    def run(argv):
        calls.append(argv[0])
        if argv[0] == broken:
            return 1
        out = Path(argv[argv.index("--out") + 1])
        kind = "project" if "project" in out.name else "shell-only"
        rec = {"massing-evidence": helpers, "shell-check": shell, "bridge-check": bridge}[argv[0]]
        rec = copy.deepcopy(rec)
        if kind == "project" and argv[0] == "shell-check":
            rec["result"]["metrics"]["thin_fraction"] = 0.0030              # a project that thins the shell
        if kind == "project" and argv[0] == "bridge-check":
            rec["result"]["metrics"]["max_span_internal_mm"] = 30.0          # helpers that shorten a bridge
            if change_method:
                rec["method"]["cell_mm"] = 0.2
        if tweak and kind == "project":
            tweak(argv[0], rec)
        out.write_text(json.dumps(rec), encoding="utf-8")
        return 2 if rec.get("result", {}).get("verdict") == "FAIL" else 0
    monkeypatch.setattr(evidence, "_run", run)
    return calls


def _inputs(tmp_path):
    paths = {}
    for n in ("report.json", "p.gcode", "b.gcode", "t.json"):
        (tmp_path / n).write_text(n, encoding="utf-8")
        paths[n] = tmp_path / n
    return paths


def test_bundle_pins_every_receipt_and_pairs_the_two_slices(tmp_path, monkeypatch):
    calls = _canned(monkeypatch)
    i = _inputs(tmp_path)
    m = evidence.build_bundle(i["report.json"], i["p.gcode"], i["b.gcode"], i["t.json"], "facet-00", tmp_path / "out")
    assert calls == ["massing-evidence", "shell-check", "bridge-check", "shell-check", "bridge-check"]
    assert m["schema"] == "fdmgen/evidence-bundle@0.1" and len(m["receipts"]) == 5
    for r in m["receipts"]:
        assert r["sha256"] == hashlib.sha256((tmp_path / "out" / r["path"]).read_bytes()).hexdigest()
    v = {(r["check"], r["slice_kind"]): r["verdict"] for r in m["receipts"]}
    assert v[("massing-evidence", "project")] == "FAIL"                  # the fixture has one dropped helper
    assert v[("shell-check", "shell-only")] == "PASS" and v[("bridge-check", "shell-only")] == "FAIL"
    assert m["paired"]["shell-check"]["thin_fraction"]["delta"] == pytest.approx(0.0008)
    assert m["paired"]["bridge-check"]["max_span_internal_mm"]["delta"] == pytest.approx(30.0 - 122.1)
    assert m["inputs"]["gcode_sha256"]["project"] == hashlib.sha256(b"p.gcode").hexdigest()
    on_disk = json.loads((tmp_path / "out" / "evidence-bundle.json").read_text(encoding="utf-8"))
    assert on_disk == m and str(tmp_path) not in json.dumps(m)       # paths relative to the bundle only


def test_bundle_withholds_a_delta_across_different_methods(tmp_path, monkeypatch):
    _canned(monkeypatch, change_method=True)
    i = _inputs(tmp_path)
    m = evidence.build_bundle(i["report.json"], i["p.gcode"], i["b.gcode"], i["t.json"], "facet-00", tmp_path / "out")
    assert "withheld" in m["paired"]["bridge-check"] and "thin_fraction" in m["paired"]["shell-check"]


def test_bundle_refuses_when_a_command_errors(tmp_path, monkeypatch):
    _canned(monkeypatch, broken="bridge-check")
    i = _inputs(tmp_path)
    with pytest.raises(RuntimeError, match="bridge-check on the project slice failed"):
        evidence.build_bundle(i["report.json"], i["p.gcode"], i["b.gcode"], i["t.json"], "facet-00", tmp_path / "out")
    assert not (tmp_path / "out" / "evidence-bundle.json").exists()


@pytest.mark.parametrize("what,reason", [
    ("slicer", "slicer print_settings_id differs"),
    ("clipped", "project raster clipped 1.5 mm3"),
    ("unmeasured", "project has 3 unmeasured samples"),
    ("bands", "project slice checked against the pose at 2 heights"),
])
def test_bundle_withholds_shell_deltas_that_would_mislead(tmp_path, monkeypatch, what, reason):
    def tweak(check, rec):
        if check != "shell-check":
            return
        if what == "slicer":
            rec["gcode"]["print_settings_id"] = "another profile"
        if what == "clipped":
            rec["grid"]["clipped_outside_grid_mm3"] = 1.5
        if what == "unmeasured":
            rec["result"]["metrics"]["unmeasured"] = 3
        if what == "bands":
            rec["placement"] = dict(rec["placement"], bands=rec["placement"]["bands"][:2])
    _canned(monkeypatch, tweak=tweak)
    i = _inputs(tmp_path)
    m = evidence.build_bundle(i["report.json"], i["p.gcode"], i["b.gcode"], i["t.json"], "facet-00", tmp_path / "out")
    assert any(r.startswith(reason) for r in m["paired"]["shell-check"]["withheld"]), m["paired"]["shell-check"]
    assert "max_span_internal_mm" in m["paired"]["bridge-check"]            # the bridge pair is unaffected


def test_a_failed_run_removes_the_previous_bundle(tmp_path, monkeypatch):
    _canned(monkeypatch)
    i = _inputs(tmp_path)
    evidence.build_bundle(i["report.json"], i["p.gcode"], i["b.gcode"], i["t.json"], "facet-00", tmp_path / "out")
    assert (tmp_path / "out" / "evidence-bundle.json").exists()
    _canned(monkeypatch, broken="shell-check")
    with pytest.raises(RuntimeError):
        evidence.build_bundle(i["report.json"], i["p.gcode"], i["b.gcode"], i["t.json"], "facet-00", tmp_path / "out")
    assert not (tmp_path / "out" / "evidence-bundle.json").exists()


def _canned_orient(monkeypatch, *, broken=None, swap_pose=False):
    """shell-check / bridge-check replaced by the real per-pose receipt fixtures."""
    def run(argv):
        if argv[0] == broken:
            return 1
        pose = argv[argv.index("--pose") + 1]
        src = pose if not swap_pose else {"facet-00": "facet-01", "facet-01": "facet-00"}[pose]
        sub = "shell" if argv[0] == "shell-check" else "bridge"
        rec = (FIX / sub / f"{src}-shell-only.{argv[0]}.json").read_bytes()
        Path(argv[argv.index("--out") + 1]).write_bytes(rec)
        return 2 if json.loads(rec)["result"]["verdict"] == "FAIL" else 0
    monkeypatch.setattr(evidence, "_run", run)


TABLE = FIX / "orient" / "spool-rack-g2-ef.with-keep-outs.orientation-table.json"


def test_orient_bundle_enriches_one_table_from_every_pose_slice(tmp_path, monkeypatch):
    _canned_orient(monkeypatch)
    (tmp_path / "a.gcode").write_text("a", encoding="utf-8")
    (tmp_path / "b.gcode").write_text("b", encoding="utf-8")
    m = evidence.build_orient_bundle(TABLE, [("facet-00", "shell-only", tmp_path / "a.gcode"),
                                             ("facet-01", "shell-only", tmp_path / "b.gcode")], tmp_path / "out")
    assert m["schema"] == "fdmgen/orient-evidence@0.1" and len(m["receipts"]) == 4
    assert m["table"]["sha256"] == hashlib.sha256(TABLE.read_bytes()).hexdigest()
    t = json.loads((tmp_path / "out" / m["enriched_table"]["path"]).read_text(encoding="utf-8"))
    assert t["enriched"]["from_table_sha256"] == m["table"]["sha256"]
    cols = {c["id"]: c["columns"] for c in t["candidates"]}
    assert cols["facet-00"]["t_shell_thin_fraction"]["value"] == 0.0022
    assert cols["facet-01"]["t_bridge_span_external_mm"]["value"] == 52.2
    assert m["enriched_table"]["sha256"] == hashlib.sha256(
        (tmp_path / "out" / m["enriched_table"]["path"]).read_bytes()).hexdigest()


@pytest.mark.parametrize("case", ["duplicate", "wrong_pose_receipt", "command_error"])
def test_orient_bundle_refuses_and_leaves_no_manifest(tmp_path, monkeypatch, case):
    _canned_orient(monkeypatch, broken="bridge-check" if case == "command_error" else None,
                   swap_pose=case == "wrong_pose_receipt")
    (tmp_path / "a.gcode").write_text("a", encoding="utf-8")
    slices = [("facet-00", "shell-only", tmp_path / "a.gcode")]
    if case == "duplicate":
        slices.append(("facet-00", "shell-only", tmp_path / "a.gcode"))
    with pytest.raises(RuntimeError):
        evidence.build_orient_bundle(TABLE, slices, tmp_path / "out")
    assert not (tmp_path / "out" / "orient-evidence.json").exists()
