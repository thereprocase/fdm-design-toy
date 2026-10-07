"""Design report (PLAN D16): a box body in its first pose, every check present with its limits."""
import numpy as np
import pytest

pytest.importorskip("scipy")
trimesh = pytest.importorskip("trimesh")

from fdmgen.orient import build_table
from fdmgen.report import layer_checks, render_markdown, run_report


def test_report_on_a_box():
    b = trimesh.creation.box(extents=(30, 20, 10))
    b.apply_translation((0, 0, 5))
    t = build_table(b.vertices, b.faces)
    ko = [{"id": "far", "type": "box", "frame": "installed", "min_mm": [100, None, None], "max_mm": [None, None, None]}]
    rep = run_report({"id": "box", "keep_outs": ko}, b.vertices, b.faces, t["candidates"][0], raster_px=0.2)
    rules = {r.rule for r in rep["results"]}
    assert {"OVH-001", "WALL-001", "GAP-001", "WALL-002", "BRG-001", "KEEP-OUT"} <= rules
    assert all(r.verdict.value == "PASS" for r in rep["results"]), [r.message for r in rep["results"] if r.verdict.value != "PASS"]
    md = render_markdown(rep, {"source": "test"})
    assert "Evidence reached: GEOMETRY" in md and "Nothing here is physically qualified" in md
    assert md.count("Does not establish:") >= 5


def test_report_accepts_an_unmerged_mesh():
    """Raw STL loading (no vertex merging, as the CLI does) must still voxelise."""
    b = trimesh.creation.box(extents=(30, 20, 10))
    b.apply_translation((0, 0, 5))
    tri = b.vertices[b.faces].reshape(-1, 3)                  # every triangle with its own three vertices
    faces = np.arange(len(tri)).reshape(-1, 3)
    t = build_table(b.vertices, b.faces)
    rep = run_report({"id": "box"}, tri, faces, t["candidates"][0], raster_px=0.2)
    assert all(r.verdict.value == "PASS" for r in rep["results"])


def test_layer_checks_parallel_matches_serial():
    occ = np.zeros((200, 120, 12), bool)
    occ[10:190, 10:110, :] = True
    occ[60:140, 40:44, 4:] = False                    # a 0.8 mm slot from layer 4 up: GAP-001 fails
    serial = {r.rule: r.verdict for r in layer_checks(occ, (0.2, 0.2, 0.2), (0, 0, 0), workers=1)}
    par = {r.rule: r.verdict for r in layer_checks(occ, (0.2, 0.2, 0.2), (0, 0, 0), workers=3)}
    assert serial == par and serial["GAP-001"].value == "FAIL"
