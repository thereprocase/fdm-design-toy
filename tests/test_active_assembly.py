"""Independent known-answer checks for the CPU AMG investigation's compact assembly."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from fdmgen.fem import element, reference

spec=importlib.util.spec_from_file_location('amg_pilot',Path(__file__).parents[1]/'bench/amg_bracket.py')
pilot=importlib.util.module_from_spec(spec); spec.loader.exec_module(pilot)


@pytest.mark.parametrize('masked',[False,True])
def test_compact_assembly_matches_full_reference(masked):
    shape=(4,3,2)
    E=np.random.default_rng(31).uniform(.1,1,shape)
    if masked: E[2:,1:,:]=0
    fixed,b=reference.cantilever(*shape)
    fixed[3*18+1]=1  # a partial-component restraint in addition to the clamp
    Ke=element.box_ke(element.ti_C(1,.8,.3,.2,.3),.5,.7,.9)
    compact,ids=pilot.assemble_active(E,Ke,fixed)
    full=reference.assemble(*shape,Ke,E.ravel(),fixed)
    delta=compact-full[ids][:,ids]
    assert np.linalg.norm(delta.data) < 1e-12
    assert np.all(np.diff(ids)>0)
    assert len(ids)%3 == 0
    if masked: assert len(ids)<full.shape[0]


def test_rigid_candidates_have_zero_element_energy():
    h=np.array([.5,.7,.9]); points=element.CORNERS*h
    B=pilot.rigid_candidates(points)
    K=element.box_ke(element.isotropic_C(1,.3),*h)
    assert np.linalg.matrix_rank(B)==6
    assert np.linalg.norm(K@B)<1e-12


@pytest.mark.parametrize('bad',[np.zeros((2,2,2)),np.full((2,2,2),-1),np.full((2,2,2),np.nan)])
def test_invalid_active_field(bad):
    with pytest.raises(ValueError):
        pilot.assemble_active(bad,np.eye(24),np.zeros(81))
