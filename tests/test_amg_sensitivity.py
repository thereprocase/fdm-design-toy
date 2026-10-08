"""Independent constitutive/contrast and small direct-solve controls for the pilot."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from fdmgen.fem import element, reference

spec = importlib.util.spec_from_file_location('amg_sensitivity', Path(__file__).parents[1] / 'bench/amg_sensitivity.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


@pytest.mark.parametrize('axis,index', [('x', 0), ('y', 1), ('z', 2)])
def test_ti_axis_compliance_and_isotropic_limit(axis, index):
    np.testing.assert_allclose(pilot.constitutive(1., axis), element.isotropic_C(1., .3), rtol=1e-12, atol=1e-12)
    C = pilot.constitutive(.7, axis)
    S = np.linalg.inv(C)
    moduli = 1 / np.diag(S)[:3]
    expected = np.ones(3); expected[index] = .7
    np.testing.assert_allclose(moduli, expected, atol=1e-12)
    assert np.linalg.eigvalsh(C).min() > 0
    # Uniaxial weak-axis loading: axial compliance 1/Ez and lateral -.3/Ep.
    stress = np.zeros(6); stress[index] = 1
    strain = S @ stress
    assert strain[index] == pytest.approx(1/.7)
    np.testing.assert_allclose(np.delete(strain[:3], index), [-.3, -.3], atol=1e-12)


def test_bands_exercise_actual_contrast_without_activating_exterior():
    mask = np.ones((9, 2, 2), bool); mask[0, 0, 0] = False
    rho, E = pilot.stiffness_field(mask, 1e-6, 'bands')
    np.testing.assert_array_equal(rho[:, 1, 1], [0, 0, 0, 0, 1, 1, 1, 1, 0])
    assert E[0, 0, 0] == 0
    assert E[4, 1, 1] / E[1, 1, 1] == 1e6
    _, uniform = pilot.stiffness_field(mask, 1e-6, 'uniform')
    assert np.unique(uniform[mask]).size == 1


@pytest.mark.parametrize('relaxation', ['block_gauss_seidel', 'block_jacobi', 'residual_block_jacobi'])
@pytest.mark.parametrize('coarse_solver', ['splu', 'pinv'])
@pytest.mark.parametrize('theta', [0., .08, .25])
def test_small_ti_contrast_solve_matches_direct(theta, coarse_solver, relaxation):
    pytest.importorskip('pyamg')
    E = np.ones((5, 2, 2)); E[1:3] = 1e-3
    fixed, load = reference.cantilever(*E.shape)
    Ke = element.box_ke(pilot.constitutive(.7, 'x'), 1, 1, 1)
    A, ids = pilot.assemble_active(E, Ke, fixed)
    rhs = load[ids].copy(); rhs[fixed[ids] != 0] = 0
    ny, nz = E.shape[1:]
    nodes = ids[::3] // 3
    points = np.column_stack(np.unravel_index(nodes, tuple(v+1 for v in E.shape)))
    B = pilot.rigid_candidates(points); B[fixed[ids] != 0] = 0
    result = pilot.solve_case(A, rhs, B, 'energy', 100, strength_threshold=theta, coarse_solver=coarse_solver, relaxation=relaxation)
    exact = np.linalg.solve(A.toarray(), rhs)
    assert result['converged']
    assert result['compliance'] == pytest.approx(rhs @ exact, rel=1e-8)
    audited = pilot.solve_case(A, rhs, B, 'energy', 100, strength_threshold=theta,
                               coarse_solver=coarse_solver, audit=True, free_mask=fixed[ids] == 0, relaxation=relaxation)
    assert audited['history'] == result['history']
    assert audited['preconditioner_audit']['free_space']['max_output_leakage'] < 1e-12
    exhausted = pilot.solve_case(A, rhs, B, 'energy', 1)
    assert not exhausted['converged']


def test_card_corners_use_nominal_poisson_and_normalized_card_matrix():
    from fdmgen.materials.card import load_card
    card = load_card('polymaker-polylite-asa-t0')
    cases, provenance = pilot.parameter_cases(card_path=card.path)
    assert len(cases) == 4
    assert {(c['ratio'], c['shear_ratio']) for c in cases} == {(.85, .2), (.85, .36), (.92, .2), (.92, .36)}
    assert provenance['parameters']['E_z_over_E_p']['borrowed'] is True
    assert provenance['parameters']['G_z_over_E_z']['tag'] == 'H'
    for case in cases:
        assert (case['nu_p'], case['nu_pz']) == (.38, .36)
        C = pilot.constitutive(axis='z', **case)
        expected = card.C('sustained_effective', {'E_z_over_E_p': case['ratio'], 'G_z_over_E_z': case['shear_ratio']}) / 1000
        np.testing.assert_allclose(C, expected, rtol=1e-12, atol=1e-12)
        assert C[3, 3] == pytest.approx(case['ratio'] * case['shear_ratio'])
    with pytest.raises(ValueError, match='cannot be mixed'):
        pilot.parameter_cases(ratios=[1], card_path=card.path)


@pytest.mark.parametrize('shear', [0, -1, float('nan'), float('inf')])
def test_invalid_shear_ratio_refused(shear):
    with pytest.raises(ValueError):
        pilot.constitutive(.85, 'z', shear_ratio=shear)
