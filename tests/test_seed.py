"""Stress-seeded helper proposals: known answers on a box with a mount bore, round trip through load_draft."""
import hashlib
import json

import numpy as np
import pytest

pytest.importorskip("scipy")
trimesh = pytest.importorskip("trimesh")

from fdmgen.massing.seed import dumps, seed_draft
from fdmgen.materials import load_card
from fdmgen.orient import StressField, build_table
from fdmgen.planning import load_draft

CARD = load_card("polymaker-polylite-asa-t0")
BORE = {"id": "mount", "type": "screw_clearance", "axis": "X", "center_yz_mm": [5.0, 5.0], "d_mm": 5.2,
        "role": "interface", "support": "forbidden"}


def setup(hot):
    body = trimesh.creation.box(extents=(60, 40, 10))
    body.apply_translation((30, 20, 5))                   # x 0..60, y 0..40, z 0..10
    mesh_bytes = trimesh.exchange.stl.export_stl(body)
    prov = {"problem": "box", "mesh": {"path": "box.stl", "sha256": hashlib.sha256(mesh_bytes).hexdigest(), "frame": "design"}}
    table = build_table(body.vertices, body.faces, provenance=prov, interfaces=[BORE], keep_outs=[])
    tb = json.dumps(table).encode()
    h = 2.0
    idx = np.array([[i, j, k] for i in range(30) for j in range(20) for k in range(5)])
    centres = (idx + 0.5) * h
    stress = np.zeros((len(idx), 6))
    for c in hot:                                          # sigma_zz hot spots: opening stress across layers in +Z
        stress[np.linalg.norm(centres - c, axis=1) < 5, 2] = 10.0
    sf = StressField(centres, stress, np.full(len(idx), h ** 3), meta={"model": "synthetic"})
    sf.cell_indices = idx
    return body, table, tb, mesh_bytes, sf


def test_seed_rejects_restraint_adjacent_and_accepts_the_rest():
    body, table, tb, mb, sf = setup([(3, 5, 5), (40, 25, 5)])
    d = seed_draft(table, tb, body.vertices, sf, b"npz", CARD, restraint_ids=("mount",), min_cells=4)
    p = d["proposal"]
    assert p["status"] == "helpers_proposed" and len(p["accepted"]) == 1
    assert any(r["reason"].startswith("restraint_adjacent") for r in p["rejected"])
    region = d["massing"]["helper_regions"][0]
    assert region["keep_clear"]["interface_ids"] == ["mount"] and region["keep_clear"]["clearance_mm"] == 0.5
    c = np.array(region["geometry"]["center_mm"])
    assert np.allclose(c[:2], [40, 25], atol=2.5) and region["geometry"]["frame"] == "design"
    assert "candidate, not load-path evidence" in region["purpose"] and "not an optimum" in d["orientation"]["designer_decision"]["rationale"]
    assert p["stress"]["sha256"] == hashlib.sha256(b"npz").hexdigest() and p["seed"]["interface_refs"] == "all"
    assert [s["restraint_margin_mm"] for s in p["sensitivity"]] == [0.0, 4.8, 9.6, 16.0]
    plan = load_draft(dumps(d), tb, mb)                    # the UI's own validator accepts it
    assert plan.helpers[0].interface_ids == ("mount",) and plan.helpers[0].clearance_mm == 0.5


def test_seed_with_only_restraint_adjacent_hot_spots_says_so():
    body, table, tb, mb, sf = setup([(3, 5, 5)])
    d = seed_draft(table, tb, body.vertices, sf, b"npz", CARD, restraint_ids=("mount",), min_cells=4)
    assert d["proposal"]["status"] == "no_viable_helpers" and d["massing"]["shell_only"] is True
    assert d["proposal"]["rejected"] and not d["massing"]["helper_regions"]
    load_draft(dumps(d), tb, mb)
