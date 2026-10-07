"""SHELL-001 at T level: a synthetic printed box with 2 walls passes, with 1 wall the walls fail."""
import math

import numpy as np
import pytest

pytest.importorskip("scipy")
trimesh = pytest.importorskip("trimesh")

from fdmgen.catalog import Verdict
from fdmgen.catalog.checks.shell import TIE_BREAK_MM, check_shell
from fdmgen.gcode import read_gcode
from fdmgen.gcode.occupancy import deposit

AREA = math.pi * 1.75 ** 2 / 4
W, H, SIDE, TOP = 0.42, 0.2, 10.0, 6.0


def road(x0, y0, x1, y1):
    e = W * H * math.hypot(x1 - x0, y1 - y0) / AREA
    return [f"G1 X{x0:.3f} Y{y0:.3f}", f"G1 X{x1:.3f} Y{y1:.3f} E{e:.6f}"]


def printed_box(walls, caps=True):
    g = ["; filament_diameter: 1.75", "M83", "G90", "; printing object part", f";WIDTH:{W}", f";HEIGHT:{H}"]
    layers = round(TOP / H)
    for k in range(1, layers + 1):
        z = round(k * H, 3)
        g += [f";Z:{z}", f"G1 Z{z}", ";TYPE:Outer wall"]
        for i in range(walls):                              # closed loops: each side runs W/2 past its corner
            a, b, e = W / 2 + 0.4 * i, SIDE - W / 2 - 0.4 * i, (W / 2 if caps else 0.0)
            g += road(a - e, a, b + e, a) + road(b, a - e, b, b + e) + road(b + e, b, a - e, b) + road(a, b + e, a, a - e)
        if k <= 3 or k > layers - 3:                       # 3-layer bottom and top skins
            g.append(";TYPE:Internal solid infill")
            a = W / 2 + 0.4 * walls                       # skin runs into the inner wall's centreline (overlap)
            for y in np.linspace(a, SIDE - a, round((SIDE - 2 * a) / 0.4) + 1):   # rows spaced evenly wall to wall
                g += road(a - 0.4, y, SIDE - a + 0.4, y)
    g.append("; stop printing object part")
    return read_gcode("\n".join(g) + "\n", footer_rel_tol=None)


def shell_result(walls, shift=0.0, caps=True, raster_caps=False):
    tp = printed_box(walls, caps)
    origin, h, shape = np.array([-0.5, -0.5, -0.5]) + shift, 0.1, (120, 120, 75)
    vgrid, _ = deposit(tp, (0, 0, 0), np.eye(3), np.zeros(3), origin, h, shape, mask=np.ones(len(tp), bool),
                       caps=raster_caps)
    box = trimesh.creation.box(extents=(SIDE, SIDE, TOP))
    box.apply_translation((SIDE / 2, SIDE / 2, TOP / 2))
    return check_shell(vgrid / h ** 3, origin, h, box.vertices, box.faces, n_samples=3000)


def test_two_walls_pass_one_wall_fails_on_the_walls():
    two = shell_result(2)
    assert two.verdict is Verdict.PASS, two.message
    one = shell_result(1)
    assert one.verdict is Verdict.FAIL
    bands = {tuple(b["slope_deg"]): b for b in one.metrics["bands"]}
    # wall points at skin heights (20 % of the wall) correctly read thick through the skin; the rest read one bead
    assert bands[(80, 90)]["thin_fraction"] > 0.6 and bands[(0, 10)]["thin_fraction"] < 0.05
    assert bands[(80, 90)]["p05_mm"] == pytest.approx(0.42, abs=0.06)
    assert {tuple(b["slope_deg"]): b for b in two.metrics["bands"]}[(80, 90)]["thin_fraction"] == 0.0


def test_grid_offset_from_the_surfaces_does_not_read_as_thin():
    """Regression (real bracket at 0.2 mm): a surface cell only partly inside the body read as 0 mm."""
    for shift in (0.0137, 0.03, 0.07, 0.0861):
        r = shell_result(2, shift)
        assert r.verdict is Verdict.PASS, (shift, r.message)


def test_tie_break_offset_removes_the_exact_half_cell_artefact():
    """At exactly half a cell the deposit's sample points sit on cell edges; the tie-break nudge removes it."""
    assert shell_result(2, 0.05).verdict is Verdict.FAIL          # documents the raw artefact the nudge exists for
    r = shell_result(2, 0.05 + TIE_BREAK_MM)
    assert r.verdict is Verdict.PASS, r.message


def test_convex_corners_without_road_end_caps_do_not_read_as_zero():
    """Regression (real bracket): the slicer turns the outer wall at its centreline, the raster has no end caps,
    so a half-bead square at each convex corner is empty and rays starting there used to read 0 mm."""
    assert shell_result(2, 0.0137, caps=False).verdict is Verdict.FAIL     # the raster artefact without caps
    r = shell_result(2, 0.0137, caps=False, raster_caps=True)
    assert r.verdict is Verdict.PASS, r.message
    assert shell_result(1, 0.0137, caps=False, raster_caps=True).verdict is Verdict.FAIL
