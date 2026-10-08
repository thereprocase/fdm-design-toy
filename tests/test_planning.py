"""Draft boundary known answers: pinned bytes, authoritative frame, no geometry claims."""
import copy
import hashlib
import json

import numpy as np
import pytest

from fdmgen.planning import load_draft


def inputs():
    body = b'body bytes; mesh parsing is a downstream responsibility'
    mesh = {'frame': 'design', 'sha256': hashlib.sha256(body).hexdigest()}
    candidate = {'id': 'side', 'R_design_to_print': [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
                 't_mm': [10, 20, 30], 'build_dir_design': [0, 0, 1], 'spin_deg': 90,
                 'columns': {'F_L_max': {'value': .1}}}
    table = {'schema': 'fdmgen/orientation-table@0.1', 'problem': 'fixture', 'mesh': mesh,
             'candidates': [candidate], 'interfaces': [{'id': 'seat'}]}
    raw = json.dumps(table).encode()
    digest = hashlib.sha256(raw).hexdigest()
    draft = {'schema': 'fdmgen.massing-plan.v0.3', 'status': 'draft_requires_verification',
             'source': {'orientation_table_sha256': digest, 'orientation_schema': table['schema'],
                        'problem': 'fixture', 'mesh': copy.deepcopy(mesh)},
             'orientation': {**copy.deepcopy(candidate), 'designer_decision': {
                 'choice': 'selected_for_planning', 'candidate_id': 'side',
                 'table_sha256': digest, 'rationale': 'Protect seat'}},
             'massing': {'body': 'fixed', 'walls': 4, 'skin_mm': 1.6,
                        'helper_infill_percent': 100, 'sparse_infill_structural_credit': False,
                        'shell_only': False, 'helper_regions': [{
                            'id': 'helper-1', 'name': 'Seat backing', 'location': 'Seat',
                            'purpose': 'Transfer load', 'geometry_status': 'sketch',
                            'geometry': {'type': 'box', 'frame': 'design', 'center_mm': [1, 2, 3], 'size_mm': [2, 4, 6]},
                            'keep_clear': {'interface_ids': ['seat'], 'keep_out_ids': [],
                                           'clearance_mm': .2, 'note': 'Preserve bore'}}]}}
    return draft, raw, body


def test_known_frame_and_intent():
    draft, table, body = inputs()
    plan = load_draft(json.dumps(draft).encode(), table, body)
    helper = plan.helpers[0]
    corners = plan.to_print(helper.corners_design_mm())
    np.testing.assert_allclose(corners.min(axis=0), [6, 20, 30])
    np.testing.assert_allclose(corners.max(axis=0), [10, 22, 36])
    assert helper.interface_ids == ('seat',)
    assert helper.clearance_mm == .2
    assert plan.walls == 4 and plan.skin_mm == 1.6
    # Copied metrics are deliberately not an input to downstream analysis.
    draft['orientation']['columns']['F_L_max']['value'] = 0
    again = load_draft(json.dumps(draft).encode(), table, body)
    np.testing.assert_equal(again.R_design_to_print, plan.R_design_to_print)
    assert not hasattr(again, 'columns')


@pytest.mark.parametrize('source', ['table', 'body', 'metadata', 'pose', 'decision'])
def test_source_mismatches(source):
    draft, table, body = inputs()
    if source == 'table': table += b' '
    if source == 'body': body += b' '
    if source == 'metadata': draft['source']['mesh']['frame'] = 'print'
    if source == 'pose': draft['orientation']['t_mm'][0] += 1
    if source == 'decision': draft['orientation']['designer_decision']['candidate_id'] = 'other'
    with pytest.raises(ValueError): load_draft(json.dumps(draft).encode(), table, body)


@pytest.mark.parametrize('change', ['negative', 'nan', 'bool', 'missing', 'path', 'duplicate', 'reference', 'clearance', 'keepout', 'credit', 'shell'])
def test_invalid_helpers_and_massing(change):
    draft, table, body = inputs()
    m = draft['massing']; h = m['helper_regions'][0]
    if change == 'negative': h['geometry']['size_mm'][0] = -1
    if change == 'nan': h['geometry']['size_mm'][0] = float('nan')
    if change == 'bool': h['geometry']['size_mm'][0] = True
    if change == 'missing': h['geometry'] = None
    if change == 'path': h['id'] = '../outside'
    if change == 'duplicate': m['helper_regions'].append(copy.deepcopy(h))
    if change == 'reference': h['keep_clear']['interface_ids'] = ['unknown']
    if change == 'clearance': h['keep_clear']['clearance_mm'] = -1
    if change == 'keepout': h['keep_clear']['keep_out_ids'] = ['not-declared']
    if change == 'credit': m['sparse_infill_structural_credit'] = True
    if change == 'shell': m['shell_only'] = True
    with pytest.raises(ValueError): load_draft(json.dumps(draft).encode(), table, body)


def test_shell_only_and_tiny_boxes_remain_intent():
    draft, table, body = inputs()
    draft['massing']['helper_regions'][0]['geometry']['size_mm'] = [.5, .5, .5]
    assert len(load_draft(json.dumps(draft).encode(), table, body).helpers) == 1
    draft['massing'].update(shell_only=True, helper_regions=[])
    plan = load_draft(json.dumps(draft).encode(), table, body)
    assert plan.shell_only and not plan.helpers


def test_nonrigid_table_and_duplicate_json_rejected():
    draft, table, body = inputs()
    with pytest.raises(ValueError, match='duplicate JSON key'):
        load_draft(b'{"schema":1,"schema":2}', table, body)
    changed = json.loads(table)
    changed['candidates'][0]['R_design_to_print'][0][1] = -2
    draft['orientation']['R_design_to_print'][0][1] = -2
    table = json.dumps(changed).encode()
    digest = hashlib.sha256(table).hexdigest()
    draft['source']['orientation_table_sha256'] = digest
    draft['orientation']['designer_decision']['table_sha256'] = digest
    with pytest.raises(ValueError, match='proper rigid rotation'):
        load_draft(json.dumps(draft).encode(), table, body)


def test_keep_out_references_are_pinned_and_preserved():
    draft, table, body = inputs()
    t = json.loads(table)
    t['keep_outs'] = [{'id': 'moulding', 'type': 'box'}, {'id': 'slide', 'type': 'not_derived'}]
    table = json.dumps(t).encode()
    digest = hashlib.sha256(table).hexdigest()
    draft['source']['orientation_table_sha256'] = digest
    draft['orientation']['designer_decision']['table_sha256'] = digest
    refs = draft['massing']['helper_regions'][0]['keep_clear']
    refs['keep_out_ids'] = ['moulding', 'slide']
    plan = load_draft(json.dumps(draft).encode(), table, body)
    assert plan.helpers[0].keep_out_ids == ('moulding', 'slide')
    # A reference is not a clearance verdict; geometry remains downstream.
    for ids in [['unknown'], ['slide', 'slide'], [True]]:
        refs['keep_out_ids'] = ids
        with pytest.raises(ValueError, match='keep-out reference'):
            load_draft(json.dumps(draft).encode(), table, body)


@pytest.mark.parametrize('otherwise_valid', [False, True])
def test_unfinished_work_snapshot_is_not_a_backend_draft(otherwise_valid):
    draft, table, body = inputs()
    # Prove the control reaches the parser successfully before changing only its
    # schema; rejection must not depend on unfinished fields being invalid.
    assert load_draft(json.dumps(draft).encode(), table, body).walls == 4
    snapshot = draft if otherwise_valid else {
        'orientation_table_sha256': hashlib.sha256(table).hexdigest(),
        'pose': 'side', 'walls': '', 'skin': '1.6', 'rationale': '',
        'shell_only': False, 'proposal': None, 'helpers': [],
    }
    snapshot['schema'] = 'fdmgen.work-snapshot.v0.1'
    with pytest.raises(ValueError, match='v0.3 is required'):
        load_draft(json.dumps(snapshot).encode(), table, body)
