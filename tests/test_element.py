import numpy as np

from fdmgen.fem import element


def test_ke_symmetric_psd_six_rigid_modes():
    for C in (element.isotropic_C(2.0, 0.3), element.ti_C(2.0, 1.7, 0.35, 0.3, 0.6)):
        K = element.box_ke(C, 0.503, 0.503, 0.6)
        assert np.allclose(K, K.T)
        w = np.linalg.eigvalsh(K)
        assert (w > -1e-10 * w.max()).all()
        assert (np.abs(w) < 1e-9 * w.max()).sum() == 6  # 3 translations + 3 rotations


def test_ti_isotropic_limit():
    E, nu = 1.5, 0.3
    assert np.allclose(element.ti_C(E, E, nu, nu, E / (2 * (1 + nu))), element.isotropic_C(E, nu))


def test_ke_scales_linearly_with_size():
    C = element.isotropic_C(1.0, 0.3)
    assert np.allclose(element.box_ke(C, 2, 2, 2), 2 * element.box_ke(C, 1, 1, 1))
