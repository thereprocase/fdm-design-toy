import numpy as np
import pytest
from fdmgen.fem.element import CORNERS, isotropic_C
from fdmgen.fem.stress import centre_stress, rotate_stress


def test_affine_patch_and_engineering_shear():
    h = np.array([.5, .8, 1.3])
    gradient = np.array([[.01, .02, .03], [.04, -.02, .05], [.06, .07, .03]])
    u = (CORNERS*h) @ gradient.T + [2, 3, 4]
    C = isotropic_C(1000, .3)
    expected = C @ [.01, -.02, .03, .12, .09, .06]
    np.testing.assert_allclose(centre_stress(u, C, h), expected, atol=1e-10)


def test_rigid_motion_has_zero_stress():
    x = CORNERS * [2, 3, 4]
    u = np.cross([.04, .02, -.03], x) + [1, 2, 3]
    np.testing.assert_allclose(centre_stress(u, isotropic_C(1000, .3), [2, 3, 4]), 0, atol=1e-10)


def test_uniaxial_stress_rotates_with_direction():
    q = np.array([1., 2., 3.]); q /= np.linalg.norm(q)
    axis = np.cross([1, 0, 0], q)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(3)+K+K@K/(1+q[0])
    expected = 7*np.outer(q, q)
    actual = rotate_stress([7, 0, 0, 0, 0, 0], R)
    np.testing.assert_allclose(actual, expected[[0, 1, 2, 1, 0, 0], [0, 1, 2, 2, 2, 1]], atol=1e-12)
    np.testing.assert_allclose(rotate_stress(actual, R.T), [7, 0, 0, 0, 0, 0], atol=1e-12)


def test_rotation_rejects_reflection():
    with pytest.raises(ValueError):
        rotate_stress(np.zeros(6), np.diag([-1, 1, 1]))
