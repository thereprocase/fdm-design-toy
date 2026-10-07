"""Orca modifier capability spike (#6): variant builder, region accounting, the committed capability file."""
import io
import zipfile
from pathlib import Path

import numpy as np
import pytest

yaml = pytest.importorskip("yaml")

from fdmgen.gcode import Toolpath
from fdmgen.slicer.modifier_spike import _fraction_in_box, build_variant, region_volumes

REPO = Path(__file__).resolve().parents[1]
CAP = REPO / "catalog" / "slicer" / "orca-2.4.2-p1s-asa-modifier-capabilities.yaml"
TEMPLATE_ZIP = REPO.parent / "spool-wall-rack" / "designs/rev-g2/print-controls/ef-core-asa-4w-1p6/slice-evidence.zip"


def test_fraction_in_box_known_answers():
    a = np.array([[0.0, 0.0], [0.0, 5.0], [2.0, 2.0], [-5.0, 20.0]])
    b = np.array([[10.0, 0.0], [10.0, 5.0], [3.0, 3.0], [5.0, 20.0]])
    f = _fraction_in_box(a, b, np.array([2.5, -1.0]), np.array([7.5, 4.0]))
    assert np.allclose(f, [0.5, 0.0, 0.5, 0.0])


def test_region_volumes_split_long_segments_by_length():
    geo = {"body_plate_bbox": [[0, 0, 0], [10, 40, 10]], "modifier_plate_bbox": [[-5, -5, 0], [15, 10, 10]]}
    tp = Toolpath(np.array([[1.0, 0.5, 5.0]]), np.array([[1.0, 39.5, 5.0]]), np.array(["Outer wall"]), np.array([0.42]),
                  np.array([0.2]), np.array([0.2]), np.array([39.0]), np.array([True]), np.array([False]))
    r = region_volumes(tp, (0, 0, 0), geo, margin_mm=0.5, away_mm=3.0)
    assert r["inside"]["Outer wall"]["volume_mm3"] == pytest.approx(9.0)        # y 0.5..9.5 of a 39 mm wall
    assert r["outside"]["Outer wall"]["volume_mm3"] == pytest.approx(26.5)      # y 13..39.5


@pytest.mark.skipif(not TEMPLATE_ZIP.is_file(), reason="spool-wall-rack checkout not next to this repository")
def test_build_variant_keeps_one_body_and_one_modifier_with_overrides():
    template = zipfile.ZipFile(TEMPLATE_ZIP).read("audit.3mf")
    data, geo = build_variant(template, {"wall_loops": "6"})
    z = zipfile.ZipFile(io.BytesIO(data))
    assert "Metadata/plate_1.gcode" not in z.namelist()
    cfg = z.read("Metadata/model_settings.config").decode()
    assert cfg.count("<part ") == 2 and 'key="wall_loops" value="6"' in cfg
    assert cfg.count('key="sparse_infill_density"') == 1                         # the object's 0 %, modifier cleared
    (blo, bhi), (mlo, mhi) = geo["body_plate_bbox"], geo["modifier_plate_bbox"]
    assert np.allclose(np.subtract(bhi, blo), [40, 60, 10]) and blo[2] == pytest.approx(0, abs=1e-9)
    assert mlo[1] < blo[1] < mhi[1] < bhi[1]                                     # the modifier covers one end


def test_committed_capability_file_contract():
    cap = yaml.safe_load(CAP.read_text())
    assert cap["schema"] == "fdmgen/slicer-capabilities@0.1"
    ctx = cap["context"]
    assert ctx["slicer"] == "OrcaSlicer" and ctx["version"] == "2.4.2" and ctx["printer_model"] == "Bambu Lab P1S"
    assert len(ctx["template_3mf_sha256"]) == 64
    for s in cap["settings"]:
        assert s["status"] in ("honoured", "ignored", "unknown") and s["requested"] and s["measured"] is not None
        assert len(s["receipt"]["gcode_sha256"]) == 64
    status = {(s["key"], tuple(sorted(s["requested"].items()))): s["status"] for s in cap["settings"]}
    assert status[("sparse_infill_density", (("sparse_infill_density", "100%"),))] == "honoured"
    assert status[("layer_height", (("layer_height", "0.1"),))] == "ignored"
    wg = next(s for s in cap["settings"] if s["key"] == "wall_generator")
    assert wg["status"] == "ignored"                                            # proven with a positive control
    assert wg["measured"]["positive_control_object_classic_inside_wall_widths_distinct"] < \
        wg["measured"]["inside_wall_widths_distinct"]
    walls = [s for s in cap["settings"] if s["key"] == "wall_loops"]
    assert all(s["status"] == "honoured" and "internal boundary" in s["non_local_side_effect"] for s in walls)
