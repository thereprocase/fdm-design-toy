'use strict';
// Read-only probe evidence. The planning document does not yet carry a verified
// slicer/template context, so these observations cannot certify this draft.
(function renderCapabilities() {
  const root = document.getElementById('modifier-evidence');
  const add = (tag, value, parent = root) => {
    const node = document.createElement(tag);
    node.textContent = value;
    parent.append(node);
    return node;
  };
  const {evidence, source, sha256} = modifierCapabilities;
  add('h3', 'What can a helper modifier change?');
  const solid = evidence.settings.find(s => s.key === 'sparse_infill_density' && s.requested.sparse_infill_density === '100%');
  const ignored = [...new Set(evidence.settings.filter(s => s.status === 'ignored').map(s => s.key))];
  add('p', `100% helper infill: ${solid?.status || 'not checked'} in the tested profile. Ignored modifier requests: ${ignored.join(', ') || 'none recorded'}. Inspect the probes below for requested values and side effects.`);
  add('p', 'Reference evidence only: this draft has no verified slicer/template match. These are per-modifier observations; the body walls and skins above remain whole-body planning intent.').className = 'hint';
  const context = add('details', '');
  add('summary', 'Tested slicer, profile and evidence limits', context);
  add('p', evidence.scope, context);
  add('pre', JSON.stringify(evidence.context, null, 2), context);
  add('p', evidence.method, context);
  add('p', evidence.establishes, context);
  add('p', evidence.does_not_establish, context);
  add('p', `Catalog: ${source} · SHA256 ${sha256}`, context);
  const probes = add('details', '');
  add('summary', 'Inspect measured overrides and side effects', probes);
  add('p', 'Honoured means the requested probe changed the slice. It does not prove that another value or combination works, or that the resulting print carries the load. Sparse infill probes receive no structural credit.', probes);
  for (const setting of evidence.settings) {
    const record = add('details', '', probes);
    record.dataset.capability = setting.receipt.probe;
    const requested = Object.entries(setting.requested).map(([key, value]) => `${key}=${value}`).join(', ');
    add('summary', `${requested} — ${setting.status === 'unknown' ? 'Not checked' : setting.status}${setting.non_local_side_effect ? ' · side effect' : ''}`, record);
    if (setting.note) add('p', setting.note, record);
    if (setting.non_local_side_effect) add('p', `Side effect: ${setting.non_local_side_effect}`, record).className = 'warning';
    add('pre', JSON.stringify(setting.measured, null, 2), record);
    add('p', 'Recorded slice provenance (G-code contents are not verified by this page):', record);
    add('pre', JSON.stringify(setting.receipt, null, 2), record);
  }
})();
