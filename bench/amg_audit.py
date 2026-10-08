"""Measured inverse probes and hierarchy metadata, never an SPD certificate."""
from __future__ import annotations
import hashlib
import numpy as np
from scipy.sparse.linalg import norm as sparse_norm


def inverse_probes(M, free=None, pairs=20, seed=1234):
    """Probe unit vector pairs; optional mask restricts inputs and gap denominator.

    Negative quadratic energy disproves positive definiteness. Positive samples
    cannot prove it. Output outside the input subspace is reported separately.
    """
    n, m = M.shape
    free = np.ones(n, bool) if free is None else np.asarray(free, dtype=bool)
    if n != m or free.shape != (n,) or not free.any() or not isinstance(pairs, int) or pairs < 1:
        raise ValueError('square inverse, nonempty matching mask and positive pair count required')
    Q = np.random.default_rng(seed).normal(size=(n, 2*pairs))
    Q[~free] = 0
    Q /= np.linalg.norm(Q, axis=0)
    MQ = np.column_stack([M @ Q[:, i] for i in range(2*pairs)])
    if not np.isfinite(MQ).all():
        raise ValueError('inverse probe produced nonfinite values')
    energy = np.sum(Q*MQ, axis=0)
    numerator = np.abs(np.sum(Q[:, :pairs]*MQ[:, pairs:], axis=0)
                       - np.sum(Q[:, pairs:]*MQ[:, :pairs], axis=0))
    denominator = np.linalg.norm(MQ[free, pairs:], axis=0)
    # A zero denominator leaves the normalized gap undefined, not silently zero.
    gaps = [float(a/b) if b > 0 else None for a, b in zip(numerator, denominator)]
    norms = np.linalg.norm(MQ, axis=0)
    leakage = [float(a/b) if b > 0 else None
               for a, b in zip(np.linalg.norm(MQ[~free], axis=0), norms)]
    return dict(seed=seed, pairs=pairs, input_dofs=int(free.sum()), total_dofs=n,
                energies=energy.tolist(), min_energy=float(energy.min()),
                symmetry_gaps=gaps, max_symmetry_gap=max((g for g in gaps if g is not None), default=None),
                undefined_symmetry_gaps=sum(g is None for g in gaps),
                max_output_leakage=max((g for g in leakage if g is not None), default=None),
                gap_definition='abs(x.T M y-y.T M x)/(norm(x)*norm((M y)[input subspace]))',
                scope='sampled inverse behavior; positive energies and small gaps do not prove SPD')


def _smoother_description(fn):
    kwargs = getattr(fn, 'keywords', {})
    values = {}
    for key, value in kwargs.items():
        if key == 'Dinv':
            a = np.ascontiguousarray(value)
            values[key] = dict(shape=list(a.shape), sha256=hashlib.sha256(a.tobytes()).hexdigest())
        elif np.isscalar(value):
            values[key] = value.item() if isinstance(value, np.generic) else value
        else:
            values[key] = 'not recorded: nonscalar parameter'
    return dict(function=getattr(getattr(fn, 'func', fn), '__name__', type(fn).__name__), parameters=values)


def hierarchy_structure(ml):
    """Record actual pair settings; equality is not proof of adjoint updates."""
    rows = []
    for level in ml.levels:
        row = dict(dofs=level.A.shape[0])
        if hasattr(level, 'P'):
            size = float(sparse_norm(level.P))
            row['restriction_transpose_relative'] = float(sparse_norm(level.R-level.P.T)/size) if size else None
            row['pre'] = _smoother_description(level.presmoother)
            row['post'] = _smoother_description(level.postsmoother)
            row['recorded_pair_equal'] = row['pre'] == row['post']
        rows.append(row)
    return dict(levels=rows, scope='matching recorded options does not prove that singular-block updates are adjoints')
