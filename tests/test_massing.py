"""Massing export (#14 handoff): MOD-001 on helper boxes, 3MF contents, refused settings."""
import io
import zipfile
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("yaml")
trimesh = pytest.importorskip("trimesh")

from fdmgen.catalog import Verdict
from fdmgen.massing import check_helpers, export_plan, load_capabilities
from fdmgen.planning import Helper, PlanningDraft
from fdmgen.slicer.threemf import Part, write_project

REPO = Path(__file__).resolve().parents[1]
CAP = load_capabilities(REPO / "catalog" / "slicer" / "orca-2.4.2-p1s-asa-modifier-capabilities.yaml")
TEMPLATE_ZIP = REPO.parent / "spool-wall-rack" / "designs/rev-g2/print-controls/ef-core-asa-4w-1p6/slice-evidence.zip"


def helper(hid, center, size):
    return Helper(hid, hid, "test", "test", np.array(center, float), np.array(size, float), (), None, "")


def body():
    b = trimesh.creation.box(extents=(60, 40, 10))
    b.apply_translation((0, 0, 5))
    return b


def plan(helpers, shell_only=False):
    return PlanningDraft("d" * 64, "t" * 64, "m" * 64, "box-test", "facet-00", "test", np.eye(3),
                         np.array([128.0, 128.0, 0.0]), 4, 1.6, shell_only, tuple(helpers))


def test_mod001_known_answers():
    b = body()
    ok = check_helpers([helper("a", (0, 0, 5), (10, 10, 8)), helper("b", (12, 0, 5), (10, 10, 8))], b.vertices, b.faces,
                       shell_band_mm=1.6)
    assert all(c.verdict is Verdict.PASS for c in ok)                          # 2 mm gap; both reach the 1.6 mm skins
    thin_band = check_helpers([helper("a", (0, 0, 5), (10, 10, 8))], b.vertices, b.faces, shell_band_mm=0.8)
    assert thin_band[-1].verdict is Verdict.NOT_CHECKED                         # 1 mm off the skins, band 0.8 mm
    floating = check_helpers([helper("mid", (0, 0, 5), (4, 4, 2))], b.vertices, b.faces, shell_band_mm=1.6)
    assert floating[-1].verdict is Verdict.NOT_CHECKED and "cannot rule out" in floating[-1].message
    r = check_helpers([helper("tiny", (0, 0, 5), (0.5, 10, 8))])
    assert r[0].verdict is Verdict.FAIL and "tiny" in r[0].message
    r = check_helpers([helper("a", (0, 0, 5), (10, 10, 8)), helper("b", (10.5, 0, 5), (10, 10, 8))])
    assert r[0].verdict is Verdict.FAIL and "0.50 mm apart" in r[0].message
    r = check_helpers([helper("a", (0, 0, 5), (10, 10, 8)), helper("b", (9.5, 0, 5), (10, 10, 8))])
    assert r[0].verdict is Verdict.FAIL and "overlap only 0.50 mm" in r[0].message
    r = check_helpers([helper("tiny", (0, 0, 5), (0.5, 10, 8))], b.vertices, b.faces, shell_band_mm=1.6)
    assert [c.verdict for c in r] == [Verdict.FAIL, Verdict.PASS]              # size fails; bonding reports only bonding
    assert "sampled" in r[1].message and "slice" in r[1].does_not_establish
    r = check_helpers([helper("away", (100, 0, 5), (10, 10, 8))], b.vertices, b.faces)
    assert any(c.verdict is Verdict.FAIL and "entirely outside" in c.message for c in r)


def test_write_project_requires_a_body_first():
    with pytest.raises(ValueError, match="first part must be the body"):
        write_project(b"", [Part("m", np.zeros((3, 3)), np.array([[0, 1, 2]]), "modifier_part")], object_name="x")


@pytest.mark.skipif(not TEMPLATE_ZIP.is_file(), reason="spool-wall-rack checkout not next to this repository")
def test_export_plan_writes_body_and_helper_modifiers():
    template = zipfile.ZipFile(TEMPLATE_ZIP).read("audit.3mf")
    b = body()
    p = plan([helper("rib", (20, 0, 5), (10, 30, 8)), helper("boss", (-20, 0, 5), (8, 8, 8))])
    data, report = export_plan(p, b.vertices, b.faces, template, CAP)
    assert report["capability_context_matches_template"] is True
    assert report["object_settings"]["top_shell_layers"] == 8 and report["object_settings"]["sparse_infill_density"] == "0%"
    z = zipfile.ZipFile(io.BytesIO(data))
    cfg = z.read("Metadata/model_settings.config").decode()
    assert cfg.count('subtype="modifier_part"') == 2 and cfg.count('subtype="normal_part"') == 1
    assert cfg.count('key="sparse_infill_density" value="100%"') == 2
    assert report["settings_evidence"]["sparse_infill_density"]["evidence"] == "measured"
    assert 'key="gcode_file"' not in cfg and "Metadata/plate_1.gcode" not in z.namelist()
    assert report["helpers"][0]["print_bbox_mm"][0] == pytest.approx([143.0, 113.0, 1.0])     # design + (128, 128, 0)
    assert all(c["verdict"] == "PASS" for c in report["checks"])
    with pytest.raises(ValueError, match=r"wall_generator \(ignored by the slicer\)"):
        export_plan(p, b.vertices, b.faces, template, CAP, helper_settings={"wall_generator": "classic"})
    with pytest.raises(ValueError, match=r"ironing_type \(not measured\)"):
        export_plan(p, b.vertices, b.faces, template, CAP, helper_settings={"ironing_type": "top"})
    with pytest.raises(ValueError, match=r"sparse_infill_pattern \(value 'rectilinear' not measured\)"):
        export_plan(p, b.vertices, b.faces, template, CAP,
                    helper_settings={"sparse_infill_density": "100%", "sparse_infill_pattern": "rectilinear"})
    _, rep = export_plan(p, b.vertices, b.faces, template, CAP, allow_unmeasured_values=True,
                         helper_settings={"sparse_infill_density": "100%", "sparse_infill_pattern": "rectilinear"})
    assert rep["settings_evidence"]["sparse_infill_pattern"]["evidence"].startswith("unverified")
    import copy
    other = copy.deepcopy(CAP)
    other["context"]["template_3mf_sha256"] = "0" * 64                         # measured with another profile
    _, rep = export_plan(p, b.vertices, b.faces, template, other)
    assert rep["settings_evidence"]["sparse_infill_density"]["evidence"].startswith("unverified")
    shell = plan([], shell_only=True)
    data, report = export_plan(shell, b.vertices, b.faces, template, CAP)
    assert report["helpers"] == [] and report["checks"] == []


DRAFT = REPO / "tests" / "fixtures" / "massing" / "sample-draft.json"
TABLE = REPO / "tests" / "fixtures" / "orient" / "spool-rack-g2-ef.orientation-table.json"


@pytest.mark.skipif(not TEMPLATE_ZIP.is_file(), reason="spool-wall-rack checkout not next to this repository")
def test_real_ui_draft_exports_and_flags_the_tiny_helper():
    """A draft exported by the browser workspace: one backing box near rear_seat, one 0.5 mm box.
    On the second workstation's Orca the backing box printed 2,746 mm3 of solid infill and the tiny box nothing."""
    import json

    from fdmgen.planning import load_draft
    table = TABLE.read_bytes()
    mesh_path = REPO.parent / "spool-wall-rack" / json.loads(table)["mesh"]["path"]
    p = load_draft(DRAFT.read_bytes(), table, mesh_path.read_bytes())
    b = trimesh.load(mesh_path)
    _data, rep = export_plan(p, b.vertices, b.faces, zipfile.ZipFile(TEMPLATE_ZIP).read("audit.3mf"), CAP)
    tiny = next(h for h in p.helpers if min(h.size_mm) < 0.84)
    fails = [c for c in rep["checks"] if c["verdict"] == "FAIL"]
    assert len(fails) == 1 and tiny.id in fails[0]["message"] and "0.50 mm" in fails[0]["message"]
    assert rep["plan"]["candidate_id"] == "facet-00" and len(rep["helpers"]) == 2


@pytest.mark.skipif(not TEMPLATE_ZIP.is_file(), reason="spool-wall-rack checkout not next to this repository")
def test_cli_massing_exit_code_and_outputs(tmp_path, capsys):
    from fdmgen.cli import main
    rc = main(["massing", str(DRAFT), "--table", str(TABLE), "--template", str(TEMPLATE_ZIP), "--out", str(tmp_path)])
    assert (tmp_path / "spool-rack-g2-ef-facet-00-massing-shell-only.3mf").is_file()
    out = capsys.readouterr().out
    assert rc == 2 and "MOD-001 FAIL" in out and "NOT_CHECKED" in out          # the tiny helper fails, exit code says so
    assert (tmp_path / "spool-rack-g2-ef-facet-00-massing.3mf").is_file()
    assert (tmp_path / "spool-rack-g2-ef-facet-00-massing.json").is_file()


def test_massing_slice_evidence_is_differential():
    from fdmgen.massing import slice_evidence
    report = {"body_print_bbox_mm": [[100, 100, 0], [140, 120, 10]], "project_3mf_sha256": "p" * 64,
              "plan": {"candidate_id": "facet-00"},
              "helpers": [{"id": "kept", "print_bbox_mm": [[105, 105, 2], [115, 115, 8]]},
                          {"id": "dropped", "print_bbox_mm": [[125, 105, 2], [125.5, 105.5, 2.5]]}]}
    lo, hi = (100.21, 100.21), (139.79, 119.79)                 # outer-wall centreline 0.21 inside the body
    shell = ["; filament_diameter: 1.75", "M83", "G90", "; printing object part", ";TYPE:Outer wall", ";Z:2.4",
             ";HEIGHT:0.2", f"G1 X{lo[0]} Y{lo[1]} Z2.4", f"G1 X{hi[0]} Y{lo[1]} E1", f"G1 X{hi[0]} Y{hi[1]} E1",
             f"G1 X{lo[0]} Y{hi[1]} E1", f"G1 X{lo[0]} Y{lo[1]} E1", ";TYPE:Internal solid infill",
             "G1 X124 Y105.2", "G1 X126 Y105.2 E0.05"]           # the body's own solid road clipping the tiny box
    helper = ["G1 X106 Y110", "G1 X114 Y110 E15.0", "G1 X106 Y111", "G1 X114 Y111 E15.0"]   # ~72 mm3 in a 600 mm3 box
    end = ["; stop printing object part"]
    with_helpers = "\n".join(shell + helper + end) + "\n; filament used [cm3] = 0.08\n"      # 34.05 mm of filament
    baseline = "\n".join(shell + end) + "\n; filament used [cm3] = 0.01\n"                   # 4.05 mm
    ev = slice_evidence(report, with_helpers, baseline)
    v = {h["id"]: h for h in ev["helpers"]}
    assert v["kept"]["verdict"] == "PASS" and v["kept"]["added_solid_mm3"] > 0
    assert v["dropped"]["solid_infill_in_box_mm3"] > 0 and v["dropped"]["added_solid_mm3"] == pytest.approx(0)
    assert v["dropped"]["verdict"] == "FAIL" and "dropped it" in v["dropped"]["message"]
    assert ev["placement_shift_xy_mm"] == pytest.approx([0, 0], abs=1e-6) and ev["baseline"] == "shell-only slice"
    single = {h["id"]: h for h in slice_evidence(report, with_helpers)["helpers"]}
    assert single["dropped"]["verdict"] == "NOT_CHECKED" and single["kept"]["verdict"] == "PASS"


def test_sample_slice_evidence_contract():
    """Real receipts: the UI sample draft exported, sliced (with its shell-only baseline) and read back."""
    import json
    rep = json.loads((REPO / "tests/fixtures/massing/sample-export-report.json").read_text())
    ev = json.loads((REPO / "tests/fixtures/massing/sample-slice-evidence.json").read_text())
    assert ev["schema"] == "fdmgen/massing-slice-evidence@0.1" and ev["tier"] == "S" and ev["level"] == "T"
    assert ev["project_3mf_sha256"] == rep["project_3mf_sha256"] and ev["plan"] == rep["plan"]
    assert ev["baseline"] == "shell-only slice" and max(abs(x) for x in ev["placement_shift_xy_mm"]) < 0.01
    assert [h["id"] for h in ev["helpers"]] == [h["id"] for h in rep["helpers"]]
    for h in ev["helpers"]:
        assert {"id", "verdict", "message", "added_solid_mm3", "added_fill_fraction", "box_volume_mm3",
                "baseline_solid_infill_mm3", "solid_infill_in_box_mm3"} <= set(h)
    assert sorted(h["verdict"] for h in ev["helpers"]) == ["FAIL", "PASS"]
