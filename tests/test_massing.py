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
    ok = check_helpers([helper("a", (0, 0, 5), (10, 10, 8)), helper("b", (12, 0, 5), (10, 10, 8))], b.vertices, b.faces)
    assert all(c.verdict is Verdict.PASS for c in ok)                          # 2 mm gap; both reach the skins
    floating = check_helpers([helper("mid", (0, 0, 5), (4, 4, 2))], b.vertices, b.faces, shell_band_mm=1.6)
    assert floating[-1].verdict is Verdict.NOT_CHECKED and "cannot rule out" in floating[-1].message
    r = check_helpers([helper("tiny", (0, 0, 5), (0.5, 10, 8))])
    assert r[0].verdict is Verdict.FAIL and "tiny" in r[0].message
    r = check_helpers([helper("a", (0, 0, 5), (10, 10, 8)), helper("b", (10.5, 0, 5), (10, 10, 8))])
    assert r[0].verdict is Verdict.FAIL and "0.50 mm apart" in r[0].message
    r = check_helpers([helper("a", (0, 0, 5), (10, 10, 8)), helper("b", (9.5, 0, 5), (10, 10, 8))])
    assert r[0].verdict is Verdict.FAIL and "overlap only 0.50 mm" in r[0].message
    r = check_helpers([helper("tiny", (0, 0, 5), (0.5, 10, 8))], b.vertices, b.faces)
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
