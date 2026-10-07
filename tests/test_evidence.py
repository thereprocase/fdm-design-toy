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
