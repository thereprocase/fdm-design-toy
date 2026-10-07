"""Ingest the UI draft against pinned sources, never its copied analysis results.

This boundary checks provenance and geometry inputs. It does not establish body
intersection, interface clearance, bonding, layer snapping, or structural credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import itertools
import json
import re

import numpy as np


def _json(raw: bytes, label: str) -> dict:
    def reject(value):
        raise ValueError(f'{label}: non-finite JSON number {value}')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'{label}: duplicate JSON key {key}')
            result[key] = value
        return result
    try:
        value = json.loads(raw, parse_constant=reject, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ValueError(f'{label}: invalid JSON') from e
    if not isinstance(value, dict):
        raise ValueError(f'{label}: expected an object')
    return value


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label}: expected an object')
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label}: required text')
    return value.strip()


def _number(value, label):
    if type(value) not in (int, float) or not np.isfinite(value):
        raise ValueError(f'{label}: expected a finite number')
    return value


def _array(value, shape, label):
    # Reject booleans and numeric strings rather than silently coercing them.
    raw = np.asarray(value, dtype=object)
    if raw.shape != shape:
        raise ValueError(f'{label}: expected shape {shape}')
    for item in raw.flat:
        _number(item, label)
    return raw.astype(float)


@dataclass
class Helper:
    id: str
    name: str
    location: str
    purpose: str
    center_mm: np.ndarray
    size_mm: np.ndarray
    interface_ids: tuple[str, ...]
    clearance_mm: float | None
    keep_clear_note: str
    keep_out_ids: tuple[str, ...] = ()

    def corners_design_mm(self) -> np.ndarray:
        return self.center_mm + np.array(list(itertools.product([-0.5, 0.5], repeat=3))) * self.size_mm


@dataclass
class PlanningDraft:
    draft_sha256: str
    table_sha256: str
    mesh_sha256: str
    problem: str
    candidate_id: str
    rationale: str
    R_design_to_print: np.ndarray
    t_mm: np.ndarray
    walls: int
    skin_mm: float
    shell_only: bool
    helpers: tuple[Helper, ...]

    def to_print(self, points) -> np.ndarray:
        points = np.asarray(points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
            raise ValueError('Design points must be a finite N x 3 array')
        return points @ self.R_design_to_print.T + self.t_mm


def load_draft(draft_bytes: bytes, table_bytes: bytes, mesh_bytes: bytes) -> PlanningDraft:
    """Validate current UI draft bytes against exact orientation table and body.

    The mesh bytes are fingerprinted here, not parsed: topology checks belong to
    the geometry stage. Legacy prose-only drafts must be reopened in the UI and
    completed before use. Even a valid return value is still unverified intent.
    """
    draft, table = _json(draft_bytes, 'Draft'), _json(table_bytes, 'Table')
    if draft.get('schema') != 'fdmgen.massing-plan.v0.3':
        raise ValueError('Reopen and complete the draft in the UI: v0.3 is required')
    if draft.get('status') != 'draft_requires_verification':
        raise ValueError('Expected a planning draft requiring verification')
    if table.get('schema') != 'fdmgen/orientation-table@0.1':
        raise ValueError('Unsupported orientation table schema')
    source = _object(draft.get('source'), 'Source')
    table_hash = hashlib.sha256(table_bytes).hexdigest()
    mesh_hash = hashlib.sha256(mesh_bytes).hexdigest()
    if source.get('orientation_table_sha256') != table_hash:
        raise ValueError('Orientation table fingerprint mismatch')
    mesh = _object(table.get('mesh'), 'Table mesh')
    if mesh.get('frame') != 'design' or mesh.get('sha256') != mesh_hash:
        raise ValueError('Expected matching body mesh in the design frame')
    if source.get('mesh') != mesh or source.get('problem') != table.get('problem') or source.get('orientation_schema') != table['schema']:
        raise ValueError('Draft source metadata disagrees with the pinned table')
    problem = _text(table.get('problem'), 'Problem')
    orientation = _object(draft.get('orientation'), 'Orientation')
    candidates = table.get('candidates')
    if not isinstance(candidates, list) or not all(isinstance(c, dict) and isinstance(c.get('id'), str) for c in candidates):
        raise ValueError('Invalid table candidates')
    ids = [c['id'] for c in candidates]
    if len(set(ids)) != len(ids) or orientation.get('id') not in ids:
        raise ValueError('Missing or ambiguous selected candidate')
    candidate = candidates[ids.index(orientation['id'])]
    # The copied transform must agree, but it never supplies the authoritative pose.
    for key in ('R_design_to_print', 't_mm', 'build_dir_design', 'spin_deg'):
        if orientation.get(key) != candidate.get(key):
            raise ValueError(f'Copied pose disagrees with table: {key}')
    R = _array(candidate.get('R_design_to_print'), (3, 3), 'Rotation')
    t = _array(candidate.get('t_mm'), (3,), 'Translation')
    direction = _array(candidate.get('build_dir_design'), (3,), 'Build direction')
    if not np.allclose(R.T @ R, np.eye(3), atol=1e-8, rtol=0) or not np.isclose(np.linalg.det(R), 1, atol=1e-8, rtol=0):
        raise ValueError('Pose must be a proper rigid rotation')
    if not np.allclose(R @ direction, [0, 0, 1], atol=1e-8, rtol=0):
        raise ValueError('Pose does not lift the build direction to print +Z')
    decision = _object(orientation.get('designer_decision'), 'Designer decision')
    if decision.get('choice') != 'selected_for_planning' or decision.get('candidate_id') != candidate['id'] or decision.get('table_sha256') != table_hash:
        raise ValueError('Designer decision does not identify this table and pose')
    rationale = _text(decision.get('rationale'), 'Choice rationale')
    massing = _object(draft.get('massing'), 'Massing')
    if massing.get('body') != 'fixed' or type(massing.get('helper_infill_percent')) is not int or massing['helper_infill_percent'] != 100 or massing.get('sparse_infill_structural_credit') is not False:
        raise ValueError('Require fixed body, 100% helpers and no sparse-infill structural credit')
    walls, skin = massing.get('walls'), _number(massing.get('skin_mm'), 'Skin')
    if type(walls) is not int or not 1 <= walls <= 20 or not .1 <= skin <= 20:
        raise ValueError('Invalid shell walls or skin thickness')
    shell_only, regions = massing.get('shell_only'), massing.get('helper_regions')
    if type(shell_only) is not bool or not isinstance(regions, list) or (shell_only and regions) or (not shell_only and not regions):
        raise ValueError('Choose either shell only or one or more helper regions')
    interfaces = table.get('interfaces', [])
    if not isinstance(interfaces, list) or not all(isinstance(i, dict) and isinstance(i.get('id'), str) for i in interfaces):
        raise ValueError('Invalid table interface declarations')
    allowed = {i['id'] for i in interfaces}
    if len(allowed) != len(interfaces):
        raise ValueError('Ambiguous table interface identifiers')
    keep_outs = table.get('keep_outs', [])
    if not isinstance(keep_outs, list) or not all(isinstance(k, dict) and isinstance(k.get('id'), str) for k in keep_outs):
        raise ValueError('Invalid table keep-out declarations')
    allowed_keep_outs = {k['id'] for k in keep_outs}
    if len(allowed_keep_outs) != len(keep_outs):
        raise ValueError('Ambiguous table keep-out identifiers')
    helpers, seen = [], set()
    for region in regions:
        region = _object(region, 'Helper')
        ident = _text(region.get('id'), 'Helper id')
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', ident) or ident in seen:
            raise ValueError('Helper ids must be unique lowercase slugs')
        seen.add(ident)
        geom = _object(region.get('geometry'), f'{ident} geometry; complete the sketch in the UI')
        if geom.get('type') != 'box' or geom.get('frame') != 'design' or region.get('geometry_status') != 'sketch':
            raise ValueError('Expected a design-frame box sketch')
        center = _array(geom.get('center_mm'), (3,), 'Helper centre')
        size = _array(geom.get('size_mm'), (3,), 'Helper size')
        if np.any(size <= 0):
            raise ValueError('Helper sizes must be positive')
        clear = _object(region.get('keep_clear'), 'Keep-clear constraints')
        refs = clear.get('interface_ids')
        if not isinstance(refs, list) or not all(isinstance(i, str) and i in allowed for i in refs) or len(set(refs)) != len(refs):
            raise ValueError('Unknown or duplicate interface reference')
        keep_out_refs = clear.get('keep_out_ids')
        if not isinstance(keep_out_refs, list) or not all(isinstance(k, str) and k in allowed_keep_outs for k in keep_out_refs) or len(set(keep_out_refs)) != len(keep_out_refs):
            raise ValueError('Unknown or duplicate keep-out reference')
        clearance = clear.get('clearance_mm')
        if clearance is not None and _number(clearance, 'Clearance') < 0:
            raise ValueError('Clearance must be nonnegative')
        helpers.append(Helper(ident, _text(region.get('name'), 'Helper name'),
                              _text(region.get('location'), 'Helper location'),
                              _text(region.get('purpose'), 'Helper purpose'), center, size,
                              tuple(refs), clearance, _text(clear.get('note'), 'Keep-clear note'), tuple(keep_out_refs)))
    return PlanningDraft(hashlib.sha256(draft_bytes).hexdigest(), table_hash, mesh_hash,
                         problem, candidate['id'], rationale, R, t, walls, skin,
                         shell_only, tuple(helpers))
