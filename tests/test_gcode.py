"""Canonical G-code reader (#2): P0-A parity on the archived slice, arcs, footer guard, frames."""
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pytest

from fdmgen.gcode import (
    FooterMismatch,
    build_transform_from_3mf,
    credit,
    gcode_to_model,
    read_gcode,
    undo_xy_shrink,
)
from fdmgen.gcode.frames import extruder_offset

REPO = Path(__file__).resolve().parents[1]
SRC = REPO.parent / "spool-wall-rack"
SLICE = SRC / "designs/rev-g2/g-recheck/2w-5layers/slice-evidence.zip"
REFERENCE = SRC / "analysis/rev-g2/g-recheck/2w-5layers/validated-shape/shape-verification.json"
PINNED_CREDITED = 70979.8020219935           # PLAN P0-A; must equal the reference file's key
PINNED_GCODE_SHA = "ab6cdc9bc145ce140e39432573fdb89347ae66724c9fd072689a6792ba5ec02f"
AREA = math.pi * 1.75 ** 2 / 4


@pytest.mark.skipif(not SLICE.is_file(), reason="spool-wall-rack@14338e9 checkout not next to this repository")
def test_p0a_credited_volume_parity():
    ref = json.loads(REFERENCE.read_text())
    assert ref["structurally_credited_extrusion_volume_mm3"] == PINNED_CREDITED
    assert ref["Gcode_sha256"] == PINNED_GCODE_SHA
    with zipfile.ZipFile(SLICE) as z:
        tp = read_gcode(z.read("plate_1.gcode"))
        xf = build_transform_from_3mf(io.BytesIO(z.read("audit.3mf")))
    assert tp.meta["gcode_sha256"] == PINNED_GCODE_SHA
    c = credit(tp)
    assert abs(c["structurally_credited_extrusion_volume_mm3"] / PINNED_CREDITED - 1) <= 1e-9
    assert c["sacrificial_thick_bridge_extrusion_volume_mm3"] == pytest.approx(
        ref["sacrificial_thick_bridge_extrusion_volume_mm3"], rel=1e-9)
    assert c["thick_bridge_segments"] == ref["thick_bridge_segments"] == 4713
    assert c["thick_bridge_heights_mm"] == ref["thick_bridge_heights_mm"] == [0.4]
    assert c["sparse_infill_volume_mm3"] == 0.0
    assert tp.meta["footer_relative_difference"] == pytest.approx(ref["relative_extrusion_footer_difference"], rel=1e-9)
    assert np.allclose(xf[:3] @ xf[:3].T, np.eye(3))


def _g(body, footer_cm3=None, header="; filament_diameter: 1.75\nM83\nG90\n"):
    tail = "" if footer_cm3 is None else f"; filament used [cm3] = {footer_cm3:.6f}\n"
    return header + body + tail


OBJ = "; printing object part\n;TYPE:Outer wall\n;WIDTH:0.42\n;HEIGHT:0.2\n;Z:0.2\nG1 X0 Y0 Z0.2 F600\n"


def test_relative_absolute_e_priming_and_footer():
    body = ("G1 X5 Y0 E1\n"                      # priming line: spent, not object
            + OBJ + "G1 X10 Y0 E2\nG1 E-0.8\nG1 E0.8\nG1 X10 Y10 E1.5\n; stop printing object part\n"
            + "M82\nG92 E0\n; printing object part\nG1 X0 Y10 E3\nG1 X0 Y0 E3.5\n; stop printing object part\n")
    total = (1 + 2 + 1.5 + 3 + 0.5) * AREA
    tp = read_gcode(_g(body, total / 1000))
    assert tp.meta["moving_extrusion_volume_mm3"] == pytest.approx(total)
    c = credit(tp)
    assert c["structurally_credited_extrusion_volume_mm3"] == pytest.approx(7 * AREA)
    assert c["nonobject_spent_volume_mm3"] == pytest.approx(1 * AREA)
    with pytest.raises(FooterMismatch, match="footer says"):
        read_gcode(_g(body, total / 1000 * 1.01))
    with pytest.raises(FooterMismatch, match="no '; filament used"):
        read_gcode(_g(body))
    assert read_gcode(_g(body), footer_rel_tol=None).meta["footer_check"] == "skipped by caller"


def test_thick_bridges_are_sacrificial_and_height_rounding_is_normalised():
    body = (OBJ + "G1 X10 Y0 E1\n;TYPE:Bridge\n;HEIGHT:0.4\nG1 X20 Y0 E2\n;TYPE:Internal Bridge\n;HEIGHT:0.200001\n"
            "G1 X30 Y0 E1\n; stop printing object part\n")
    tp = read_gcode(_g(body, 4 * AREA / 1000))
    c = credit(tp)
    assert c["sacrificial_thick_bridge_extrusion_volume_mm3"] == pytest.approx(2 * AREA)
    assert c["structurally_credited_extrusion_volume_mm3"] == pytest.approx(2 * AREA)
    assert tp.height[-1] == 0.2 and tp.declared_height[-1] == 0.200001


def test_arcs_are_read_and_match_their_polyline():
    r, e = 10.0, 3.0
    arc = OBJ.replace("G1 X0 Y0", f"G1 X{r} Y0") + f"G3 X{-r} Y0 I{-r} J0 E{e}\n; stop printing object part\n"
    tp = read_gcode(_g(arc, e * AREA / 1000))      # the source parser skipped G2/G3: this footer would fail
    assert tp.from_arc.all() and len(tp) == 36       # 180 deg in 5 deg chords
    assert tp.volume.sum() == pytest.approx(e * AREA, rel=1e-12)
    rad = np.hypot(tp.end[:, 0], tp.end[:, 1])
    assert np.allclose(rad, r) and np.all(tp.end[:, 1] >= -1e-9)   # counter-clockwise: upper half
    n = 720                                          # the same semicircle written as a G1 polyline
    ang = np.linspace(0, math.pi, n + 1)[1:]
    poly = OBJ.replace("G1 X0 Y0", f"G1 X{r} Y0") + "".join(
        f"G1 X{r * math.cos(a):.6f} Y{r * math.sin(a):.6f} E{e / n:.9f}\n" for a in ang) + "; stop printing object part\n"
    tq = read_gcode(_g(poly, e * AREA / 1000))
    assert tq.volume.sum() == pytest.approx(tp.volume.sum(), rel=1e-3)      # P0-B style: within 0.1 %
    length = lambda t: np.linalg.norm(t.end - t.start, axis=1).sum()
    assert length(tp) == pytest.approx(length(tq), rel=1e-3)
    cw = OBJ.replace("G1 X0 Y0", f"G1 X{r} Y0") + f"G2 X{-r} Y0 I{-r} J0 E{e}\n; stop printing object part\n"
    assert np.all(read_gcode(_g(cw, e * AREA / 1000)).end[:, 1] <= 1e-9)   # clockwise: lower half
    with pytest.raises(ValueError, match="R-form"):
        read_gcode(_g(OBJ + "G2 X5 Y5 R5 E1\n", AREA / 1000))


def test_nonplanar_and_wrong_layer_extrusion_raise():
    with pytest.raises(ValueError, match="non-planar"):
        read_gcode(_g(OBJ + ";Z:0.4\nG1 X5 Y0 Z0.4 E1\n", AREA / 1000))
    with pytest.raises(ValueError, match="layer comment"):
        read_gcode(_g(OBJ.replace(";Z:0.2", ";Z:0.4") + "G1 X5 Y0 E1\n", AREA / 1000))


def test_frame_chain_known_answers(tmp_path):
    assert extruder_offset("; extruder_offset = 0x2\n").tolist() == [0, 2, 0]
    xf = np.array([[-1, 0, 0], [0, -1, 0], [0, 0, 1], [128.0, 130.0, 0]])   # 180 deg about Z, centred
    model = gcode_to_model([[128.0, 128.0, 0.2]], xf, [0, 2, 0])            # offset restored before placement
    assert np.allclose(model, [[0.0, 0.0, 0.2]])
    p = np.array([[10.0, 20.0, 1.0], [-5.0, 3.0, 2.0]])
    c = [1.0, 2.0]
    scaled = (p[:, :2] - c) * (100 / 99.46) + c                             # what the slicer does
    assert np.allclose(undo_xy_shrink(np.c_[scaled, p[:, 2]], 99.46, c), p)
    f = tmp_path / "plate.3mf"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("3D/3dmodel.model", '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
                   '<build><item objectid="1" transform="-1 0 0 0 -1 0 0 0 1 128 130 0"/></build></model>')
    assert np.allclose(build_transform_from_3mf(f), xf)


ASA_SLICE = SRC / "designs/rev-g2/print-controls/ef-core-asa-4w-1p6/slice-evidence.zip"


@pytest.mark.skipif(not (SLICE.is_file() and ASA_SLICE.is_file()), reason="spool-wall-rack@14338e9 checkout not present")
@pytest.mark.parametrize("archive,offset", [(SLICE, [0, 0, 0]), (ASA_SLICE, [0, 2, 0])])
def test_offset_restore_lands_on_the_placed_body(archive, offset):
    """G-code + extruder offset sits half a line width inside the 3MF-placed body on all four sides,
    and the footprint is unscaled (both archives were sliced at filament_shrink 100 %)."""
    from fdmgen.gcode import placed_component_bbox, xy_scale_vs_model
    with zipfile.ZipFile(archive) as z:
        text = z.read("plate_1.gcode").decode()
        lo, hi = placed_component_bbox(io.BytesIO(z.read("audit.3mf")))
    assert "; filament_shrink = 100%" in text
    off = extruder_offset(text)
    assert off.tolist() == offset
    r = xy_scale_vs_model(read_gcode(text), off, lo, hi, half_width=0.21)
    assert np.allclose(r["inset_lo_xy"] + r["inset_hi_xy"], 0.21, atol=0.015)   # outer wall 0.42 mm; measured 0.2095..0.2204
    assert np.allclose(r["scale_xy"], 1.0, atol=1e-4)
    wrong = xy_scale_vs_model(read_gcode(text), off + [0, 2, 0], lo, hi, half_width=0.21)
    assert not np.allclose(wrong["inset_lo_xy"] + wrong["inset_hi_xy"], 0.21, atol=0.015)  # a 2 mm error shows
