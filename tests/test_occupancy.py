"""G-code -> design-frame density grid: volume conservation, solid fill, pose round trip."""
import math

import numpy as np
import pytest

from fdmgen.gcode import read_gcode
from fdmgen.gcode.occupancy import deposit, occupancy, plate_to_grid

AREA = math.pi * 1.75 ** 2 / 4


def _layer_square(z, n=25, pitch=0.4, w=0.42, x0=0.2, y0=0.2, length=10.0):
    """n parallel roads along X, `pitch` apart: a solid 10 x 10 mm square of one layer."""
    e = 0.2 * w * length / AREA          # E for a w x 0.2 bead of this length
    out = [f";Z:{z}", ";HEIGHT:0.2", f";WIDTH:{w}"]
    for k in range(n):
        y = y0 + k * pitch
        out += [f"G1 X{x0} Y{y:.3f} Z{z}", f"G1 X{x0 + length} Y{y:.3f} E{e:.6f}"]
    return out


def gcode(layers=5, extra=()):
    g = ["; filament_diameter: 1.75", "M83", "G90", "; printing object part", ";TYPE:Internal solid infill"]
    for i in range(layers):
        g += _layer_square(round(0.2 * (i + 1), 3))
    g += list(extra) + ["; stop printing object part"]
    return "\n".join(g) + "\n"


def test_volume_is_conserved_and_bridges_are_excluded():
    extra = [";TYPE:Bridge", ";HEIGHT:0.4", "G1 X0 Y12 Z1.0", "G1 X10 Y12 E5"]
    tp = read_gcode(gcode(extra=extra + [";Z:1.0"]), footer_rel_tol=None)
    vgrid, outside = deposit(tp, (0, 0, 0), np.eye(3), np.zeros(3), np.array([-1.0, -1, -1]), 0.5, (30, 30, 10))
    credited = tp.volume[tp.role == "Internal solid infill"].sum()
    assert vgrid.sum() == pytest.approx(credited, rel=1e-12) and outside == 0.0   # every credited mm3 in the grid
    small, out2 = deposit(tp, (0, 0, 0), np.eye(3), np.zeros(3), np.array([-1.0, -1, -1]), 0.5, (12, 30, 10))
    assert small.sum() + out2 == pytest.approx(credited, rel=1e-12) and out2 > 0  # clipped volume is accounted


def test_solid_square_reads_as_solid_cells():
    tp = read_gcode(gcode(), footer_rel_tol=None)
    d = occupancy(tp, (0, 0, 0), np.eye(3), np.zeros(3), np.array([-0.4, -0.4, -0.4]), 0.4, (28, 28, 5))
    dens = d["density"]
    acct = d["accounting"]
    assert acct["saturation_excess_mm3"] > 0 and acct["clipped_outside_grid_mm3"] == 0.0
    assert d["density"].max() > 1 and d["density_capped"].max() == 1.0
    core = dens[5:24, 5:24, 1:3]                                               # z cells 0..0.8 mm: fully inside the 1 mm square
    assert core.mean() == pytest.approx(0.42 / 0.4, rel=0.05)                 # w x h beads at 0.4 mm pitch: 1.05 (overlap)
    assert d["solid_mask"][5:24, 5:24, 1:3].all() and not d["solid_mask"][:, 28:, :].any()


def test_plate_to_grid_composes_pose_inverse_and_solver_map():
    """A plate point of a posed part lands in the solver-grid cell of its design-frame point."""
    R = np.array([[0.0, -1, 0], [1, 0, 0], [0, 0, 1]])                       # pose: design -> plate
    t = np.array([50.0, 20.0, 0])
    Rg, tg = np.diag([-1.0, -1, 1]), np.array([250.0, 182.0, 0])            # solver: design -> grid
    M, c = plate_to_grid(R, t, Rg, tg)
    d = np.array([[12.0, -3.0, 4.0], [100.0, 40.0, 7.0]])
    plate = d @ R.T + t
    assert np.allclose(plate @ M.T + c, d @ Rg.T + tg, atol=1e-12)
    tp = read_gcode(gcode(layers=2), footer_rel_tol=None)
    g = occupancy(tp, (0, 0, 0), M, c, np.array([180.0, 150.0, -1.0]), 1.6, (60, 40, 4))
    a = g["accounting"]
    assert a["deposited_inside_grid_mm3"] + a["clipped_outside_grid_mm3"] == pytest.approx(a["credited_input_mm3"], rel=1e-12)


def test_caps_fill_the_convex_corner_and_conserve_volume():
    """Two walls meeting at their centrelines (how the slicer turns a corner): caps fill the corner square."""
    e = 0.2 * 0.42 * 5.0 / AREA
    g = ["; filament_diameter: 1.75", "M83", "G90", "; printing object part", ";TYPE:Outer wall", ";Z:0.2",
         ";HEIGHT:0.2", ";WIDTH:0.42", "G1 X0.21 Y5.21 Z0.2", f"G1 X0.21 Y0.21 E{e:.6f}", f"G1 X5.21 Y0.21 E{e:.6f}",
         "; stop printing object part"]
    tp = read_gcode("\n".join(g) + "\n", footer_rel_tol=None)
    args = (tp, (0, 0, 0), np.eye(3), np.zeros(3), np.array([-1.0, -1.0, 0.0]) + 1e-4 * np.pi, 0.1, (80, 80, 2))
    plain, _ = deposit(*args, mask=np.ones(len(tp), bool))
    capped, out = deposit(*args, mask=np.ones(len(tp), bool), caps=True)
    corner = (slice(10, 12), slice(10, 12), 0)                     # cells covering x, y in 0.0..0.2 mm
    assert plain[corner].sum() == 0.0 and capped[corner].min() > 0
    assert capped.sum() + out == pytest.approx(tp.volume.sum(), rel=1e-12) == plain.sum()
