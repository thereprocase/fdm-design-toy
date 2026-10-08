"""Explicit first-level constraint treatment for nodal strength, never physical A."""
from __future__ import annotations
import hashlib
import numpy as np

POLICIES = ('original', 'zero', 'mean')


def strength_options(A, theta, free=None, policy='original'):
    """Keep identity constraints in the solve; optionally exclude/rescale in graph.

    Later levels use ordinary symmetric strength. Coverage describes tentative
    aggregation only; complete coverage does not establish solver convergence.
    """
    from pyamg.strength import symmetric_strength_of_connection
    from pyamg.aggregation.aggregate import standard_aggregation
    if policy not in POLICIES or not np.isfinite(theta) or not 0 <= theta <= 1:
        raise ValueError('known strength policy and theta in [0,1] required')
    if A.shape[0] != A.shape[1] or A.shape[0] % 3:
        raise ValueError('square matrix with three DOFs per node required')
    if free is not None:
        free = np.asarray(free)
        if free.dtype != bool or free.shape != (A.shape[0],):
            raise ValueError('boolean free mask matching matrix required')
    elif policy != 'original':
        raise ValueError('constraint-aware strength requires a free mask')
    graph = A.copy().tocsr()
    if policy != 'original':
        # Only identity rows are allowed to be rewritten in the graph copy.
        rows = graph[~free].copy(); rows.eliminate_zeros()
        if (not np.all(np.diff(rows.indptr) == 1)
                or not np.array_equal(rows.indices, np.flatnonzero(~free))
                or not np.all(rows.data == 1)):
            raise ValueError('fixed DOFs must have identity rows')
        diagonal = graph.diagonal().reshape(-1, 3)
        node_free = free.reshape(-1, 3)
        means = np.divide((diagonal * node_free).sum(axis=1), node_free.sum(axis=1),
                          out=np.zeros(len(diagonal)), where=node_free.sum(axis=1) > 0)
        diagonal[~node_free] = (0 if policy == 'zero' else
                               np.broadcast_to(means[:, None], diagonal.shape)[~node_free])
        graph.setdiag(diagonal.ravel()); graph.eliminate_zeros()
    S = symmetric_strength_of_connection(graph.tobsr(blocksize=(3, 3)), theta=theta)
    aggregates, _ = standard_aggregation(S)
    uncovered = np.repeat(np.diff(aggregates.indptr) == 0, 3)
    metadata = dict(method='symmetric', theta=theta, blocksize=3, constraint_policy=policy,
                    applies_to='first strength graph only; physical A and later-level strength unchanged',
                    first_graph_sha256={key: hashlib.sha256(np.ascontiguousarray(getattr(S, key)).tobytes()).hexdigest()
                                        for key in ('data', 'indices', 'indptr')},
                    first_aggregate_count=aggregates.shape[1],
                    unassigned_free_dofs=int((uncovered & free).sum()) if free is not None else None,
                    coverage_scope='tentative aggregate coverage, not convergence or physical validation')
    ordinary = ('symmetric', {'theta': theta})
    options = ordinary if policy == 'original' else [('predefined', {'C': S}), ordinary]
    return options, metadata
