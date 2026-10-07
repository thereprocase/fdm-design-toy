"""Orientation analysis (#11): poses, F_L known answers (PLAN P1 acceptance), printability table."""
import numpy as np
import pytest

pytest.importorskip("scipy")
pytest.importorskip("yaml")

from fdmgen.materials import load_card
from fdmgen.orient import (
    SCHEMA,
    StressField,
    build_table,
    candidate_poses,
    hull_facets,
    interlayer_index,
    place,
    rotation_to_z,
)


def box_mesh(a, b, c):
    """Closed outward-wound box [0,a] x [0,b] x [0,c]."""
    v = np.array([[x, y, z] for x in (0, a) for y in (0, b) for z in (0, c)], float)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    f = []
    for q in quads:
        f += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    f = np.array(f)
    tri = v[f]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()
    return v, (f if vol > 0 else f[:, ::-1])


def test_rotation_to_z_is_proper_for_all_directions():
    rng = np.random.default_rng(3)
    for d in list(rng.normal(size=(50, 3))) + [np.array([0, 0, 1.0]), np.array([0, 0, -1.0])]:
        R = rotation_to_z(d)
        assert np.allclose(R @ (d / np.linalg.norm(d)), [0, 0, 1], atol=1e-12)
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-12) and np.isclose(np.linalg.det(R), 1.0)
    v, _ = box_mesh(10, 20, 30)
    V, _R, _t = place(v, [1, 0, 0])
    assert V[:, 2].min() == pytest.approx(0.0) and V[:, 2].max() == pytest.approx(10.0)


def test_box_hull_facets_and_candidate_poses():
    v, _f = box_mesh(10, 20, 30)
    areas = sorted(a for _, a in hull_facets(v))
    assert areas == pytest.approx([200, 200, 300, 300, 600, 600])
    poses = candidate_poses(v)
    assert len(poses) == 6 and all(p.kind == "stable_facet" for p in poses)   # axis poses merged as duplicates
    assert all(p.meta.get("also") for p in poses)


SIG, TAU, ZT, SIL = 7.0, 3.0, 21.9, 10.95


def test_fl_uniaxial_bar_standing_vs_flat():
    s = np.array([[0, 0, SIG, 0, 0, 0]])                 # sigma_zz along the bar axis z
    assert interlayer_index(s, [0, 0, 1], ZT, SIL)[0][0] == pytest.approx(SIG / ZT)    # standing: layers across load
    assert interlayer_index(s, [1, 0, 0], ZT, SIL)[0][0] == pytest.approx(0.0)         # flat: layers along load
    assert interlayer_index(-s, [0, 0, 1], ZT, SIL)[0][0] == pytest.approx(0.0)        # compression opens nothing
    sh = np.array([[0, 0, 0, 0, TAU, 0]])                # tau_xz
    assert interlayer_index(sh, [0, 0, 1], ZT, SIL)[0][0] == pytest.approx(TAU / SIL)


def test_fl_even_in_d_and_rotation_covariant():
    rng = np.random.default_rng(11)
    s = rng.normal(size=(200, 6)) * 5
    from fdmgen.orient.failure import VOIGT, tensor
    for _ in range(20):
        d = rng.normal(size=3)
        a = interlayer_index(s, d, ZT, SIL)[0]
        assert np.allclose(a, interlayer_index(s, -d, ZT, SIL)[0], rtol=0, atol=1e-12)
        Q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        T = Q @ tensor(s) @ Q.T
        sr = np.stack([T[:, i, j] for i, j in VOIGT], axis=1)
        assert np.allclose(a, interlayer_index(sr, Q @ d, ZT, SIL)[0], rtol=1e-12, atol=1e-12)


def _bar_stress(v, sigma):
    """Uniform axial stress along x sampled at a few interior points of the bar."""
    c = np.c_[np.linspace(5, 95, 10), np.full(10, 5.0), np.full(10, 5.0)]
    s = np.zeros((10, 6))
    s[:, 0] = sigma
    return StressField(c, s, np.full(10, 100.0), meta={"model": "uniform uniaxial test field"})


def test_table_for_a_slender_bar(tmp_path):
    v, f = box_mesh(100, 10, 10)                         # bar along x
    card = load_card("polymaker-polylite-asa-t0")
    t = build_table(v, f, card=card, stress=_bar_stress(v, SIG), provenance={"problem": "bar-test"})
    assert t["schema"] == SCHEMA and t["problem"] == "bar-test"
    rows = {tuple(np.round(r["build_dir_design"], 6)): r for r in t["candidates"]}
    zt = card.strength_corners()["design"]["Z_t"]
    standing = rows[(1.0, 0.0, 0.0)] if (1.0, 0.0, 0.0) in rows else rows[(-1.0, 0.0, 0.0)]
    assert standing["columns"]["F_L_max"]["value"] == pytest.approx(SIG / zt)
    assert not standing["feasible"] and any("topple" in s for s in standing["reasons"])   # 100 mm on a 10 mm base
    lying = [r for r in t["candidates"] if abs(r["build_dir_design"][0]) < 1e-9]
    assert len(lying) == 4 and all(r["columns"]["F_L_max"]["value"] == pytest.approx(0.0) for r in lying)
    assert all(r["feasible"] and r["columns"]["ovh_fail_mm2"]["value"] == 0.0 for r in lying)
    assert t["candidates"][0]["rank"] == 0 and t["candidates"][0]["pareto"]
    assert all(c["level"] in ("V", "M", "T", "FE") for c in t["candidates"][0]["columns"].values())


def test_table_without_stress_marks_fl_not_checked():
    v, f = box_mesh(30, 20, 10)
    t = build_table(v, f)
    c = t["candidates"][0]["columns"]
    assert c["F_L_max"]["value"] is None and c["F_L_max"]["verdict"] == "NOT_CHECKED"
    assert t["candidates"][0]["build_dir_design"] in ([0, 0, 1.0], [0, 0, -1.0])     # lowest: lying on a 30 x 20 face


def test_stress_npz_schema(tmp_path):
    p = tmp_path / "s.npz"
    np.savez(p, centres_mm=np.zeros((2, 3)), stress_mpa=np.zeros((2, 6)), cell_volume_mm3=np.ones(2),
             cell_indices=np.zeros((2, 3), int), solid_mask=np.ones((1, 1, 2), bool), model=np.array("iso R1"))
    sf = StressField.load(p)
    assert sf.stress.shape == (2, 6) and sf.meta["model"] == "iso R1"
    np.savez(p, centres_mm=np.zeros((2, 3)), stress_mpa=np.zeros((2, 3)), cell_volume_mm3=np.ones(2))
    with pytest.raises(ValueError, match="Voigt"):
        StressField.load(p)


FIXTURE = __import__("pathlib").Path(__file__).parent / "fixtures" / "orient" / "spool-rack-g2-ef.orientation-table.json"
CANDIDATE_KEYS = {"id", "kind", "build_dir_design", "spin_deg", "R_design_to_print", "t_mm", "feasible", "reasons",
                  "pareto", "rank", "designer_decision", "columns"}
COLUMN_KEYS = {"ovh_fail_mm2", "bridge_candidate_mm2", "v_unsupported_mm2", "brg_worst_span_mm", "contact_mm2",
               "com_margin_mm", "base_min_width_mm", "height_mm", "fits_bed", "F_L_max", "F_L_p99"}
CELL_KEYS = {"value", "unit", "rule", "level", "verdict", "provisional", "fidelity"}


def test_sample_table_honours_the_ui_contract():
    """The contract agreed with the UI work (fields may be added, never renamed)."""
    import json
    t = json.loads(FIXTURE.read_text())
    assert t["schema"] == SCHEMA and t["problem"] == "spool-rack-g2-ef" and t["mesh"]["frame"] == "design"
    assert {"establishes", "does_not_establish", "generated", "candidates"} <= set(t)
    for c in t["candidates"]:
        assert CANDIDATE_KEYS <= set(c) and COLUMN_KEYS <= set(c["columns"])
        assert all(CELL_KEYS <= set(cell) for cell in c["columns"].values())
        assert c["kind"] in ("stable_facet", "axis", "sphere", "user")
    best = t["candidates"][0]
    assert best["rank"] == 0 and best["build_dir_design"] == [0.0, 0.0, 1.0]      # the existing flat-on-side pose
