"""B10: FP64 reference covariance under all proper grid rotations.

Rotates a masked domain, restraints, loads, non-cubic spacing and TI axis
 together. Establishes reference plumbing, not GPU/orientation-search parity.
"""
import itertools
import numpy as np
import pytest
from scipy.sparse.linalg import spsolve
from fdmgen.fem import element, reference


def rotations():
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((-1, 1), repeat=3):
            R = np.eye(3)[list(perm)] * np.array(signs)[:, None]
            if np.linalg.det(R) > 0:
                yield perm, signs, R


def rotate_C(C, R):
    pairs = [(0,0),(1,1),(2,2),(1,2),(0,2),(0,1)]
    tensor = np.zeros((3,3,3,3))
    for i,(a,b) in enumerate(pairs):
        for j,(c,d) in enumerate(pairs):
            for x,y in {(a,b),(b,a)}:
                for z,w in {(c,d),(d,c)}:
                    tensor[x,y,z,w] = C[i,j]
    rotated = np.einsum('ia,jb,kc,ld,abcd->ijkl',R,R,R,R,tensor)
    return np.array([[rotated[a,b,c,d] for c,d in pairs] for a,b in pairs])


@pytest.mark.parametrize('perm,signs,R', list(rotations()))
def test_masked_ti_compliance_covariance(perm, signs, R):
    shape = (4,3,2); h = np.array([0.5,0.7,0.9])
    E = np.random.default_rng(10).uniform(0.2,1,shape)
    E[2:,2,1] = 0  # notch
    fixed,b = reference.cantilever(*shape)
    active=np.zeros(tuple(n+1 for n in shape),bool)
    for corner in element.CORNERS:
        view=active[corner[0]:corner[0]+shape[0],corner[1]:corner[1]+shape[1],corner[2]:corner[2]+shape[2]]
        view |= E > 0
    fixed[np.repeat(~active.ravel(),3)] = 1
    C = element.ti_C(1,0.7,0.3,0.25,0.3)
    A = reference.assemble(*shape,element.box_ke(C,*h),E.ravel(),fixed)
    b[fixed!=0] = 0
    u = spsolve(A,b)
    node_shape = tuple(n+1 for n in shape)
    def transform(field):
        # Last axis stores vector components; permute the physical node grid.
        out=field.reshape(*node_shape,3).transpose(*perm,3)
        for a,sgn in enumerate(signs):
            if sgn < 0: out=np.flip(out,axis=a)
        return out
    new_fixed=transform(fixed)[...,list(perm)].ravel()
    new_b=(transform(b) @ R.T).ravel()
    new_E=E.transpose(perm)
    for a,sgn in enumerate(signs):
        if sgn < 0: new_E=np.flip(new_E,axis=a)
    new_shape=tuple(shape[a] for a in perm)
    new_C=rotate_C(C,R)
    Ar=reference.assemble(*new_shape,element.box_ke(new_C,*h[list(perm)]),new_E.ravel(),new_fixed)
    ur=spsolve(Ar,new_b)
    assert abs(new_b@ur-b@u)/abs(b@u) < 1e-10
    expected=(transform(u) @ R.T).ravel()
    assert np.linalg.norm(ur-expected)/np.linalg.norm(expected) < 1e-10
