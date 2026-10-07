"""Material card schema + T0 PolyLite ASA card (#8): lint, PD check, both strength corners."""
import copy

import numpy as np
import pytest

pytest.importorskip("yaml")

from fdmgen.fem.element import ti_C
from fdmgen.materials import lint_card, load_card, pd_reasons

ASA = "polymaker-polylite-asa-t0"


def test_card_lints_clean_and_is_t0():
    c = load_card(ASA)
    assert lint_card(c.data) == []
    assert c.tier == "T0"
    assert c.data["moduli"]["E_z_over_E_p"]["borrowed"] is True


def test_strength_corners_vendor_ratio_and_half_xt():
    st = load_card(ASA).strength_corners()
    assert st["vendor_ratio"]["Z_t"] == 32.0 and st["vendor_ratio"]["X_t"] == 43.8
    assert st["half_X_t"]["Z_t"] == pytest.approx(21.9, abs=1e-12)
    assert st["vendor_ratio"]["S_il"] == pytest.approx([16.0, 32.0])
    d = st["design"]                               # conservative corner: lowest Z_t and lowest S_il/Z_t
    assert d["from"] == "half_X_t" and d["Z_t"] == pytest.approx(21.9) and d["S_il"] == pytest.approx(10.95)


def test_stiffness_bases_and_ti_matrix():
    c = load_card(ASA)
    k = c.constants("short_term")
    assert k["E_p"] == 2379 and k["E_z"] == pytest.approx(0.87 * 2379) and k["G_z"] == pytest.approx(0.32 * 0.87 * 2379)
    assert c.constants("sustained_effective")["E_p"] == 1000
    C = c.C("short_term")
    assert np.allclose(C, ti_C(k["E_p"], k["E_z"], k["nu_p"], k["nu_pz"], k["G_z"]))
    # ratios are shared by both bases, so the sustained matrix is the short-term one scaled by 1000/2379
    assert np.allclose(c.C("sustained_effective"), C * 1000 / 2379, rtol=1e-12)
    # uniaxial in-plane stress reproduces E_p and the Poisson convention eps_z = -nu_pz/E_p sigma_x
    eps = np.linalg.solve(C, [1.0, 0, 0, 0, 0, 0])
    assert 1 / eps[0] == pytest.approx(2379) and -eps[2] / eps[0] == pytest.approx(0.36)
    with pytest.raises(ValueError, match="modulus basis"):
        c.constants("long_term")


def test_pd_at_every_interval_corner():
    c = load_card(ASA)
    corners = c.stiffness_corners()
    assert len(corners) == 16
    for corner in corners:
        for basis in ("short_term", "sustained_effective"):
            assert pd_reasons(**c.constants(basis, corner)) == []
            assert np.linalg.eigvalsh(c.C(basis, corner)).min() > 0


def test_pd_check_agrees_with_eigenvalues():
    rng = np.random.default_rng(7)
    for _ in range(2000):
        E_p, E_z = rng.uniform(100, 3000, 2)
        nu_p, nu_pz = rng.uniform(-0.99, 0.99), rng.uniform(-1.5, 1.5)
        G_z = rng.uniform(10, 1000)
        analytic = not pd_reasons(E_p, E_z, nu_p, nu_pz, G_z)
        try:
            ti_C(E_p, E_z, nu_p, nu_pz, G_z)
            numeric = True
        except ValueError:
            numeric = False
        assert analytic == numeric, (E_p, E_z, nu_p, nu_pz, G_z)


def test_lint_messages():
    base = load_card(ASA).data
    d = copy.deepcopy(base)
    d["moduli"]["nu_pz"].update(value=0.75, interval=[0.7, 0.8])     # too large for nu_p 0.38
    assert any("not positive definite" in e and "nu_pz" in e for e in lint_card(d))
    d = copy.deepcopy(base)
    del d["strengths"]["Z_t"]["half_X_t"]
    assert any("both corners" in e for e in lint_card(d))
    d = copy.deepcopy(base)
    d["tier"] = "T1"
    assert any("own-coupon (U) Z_t" in e for e in lint_card(d))
    d = copy.deepcopy(base)
    del d["moduli"]["E_p"]["sustained_effective"]
    assert any("both modulus bases" in e for e in lint_card(d))
    d = copy.deepcopy(base)
    d["moduli"]["nu_p"].pop("interval")
    assert any("heuristic (H) value needs an interval" in e for e in lint_card(d))
    d = copy.deepcopy(base)
    d["moduli"]["E_z_over_E_p"]["value"] = 0.95
    assert any("outside its interval" in e for e in lint_card(d))
