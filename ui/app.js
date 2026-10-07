'use strict';
const byId = id => document.getElementById(id);
let analysis = null, selected = null, fingerprint = null, tableRequest = 0, draftRequest = 0;
const decisions = new Map();
const viewer = new PartViewer(byId('part-view'));
let mesh=null,meshHash=null,meshRequest=0;
function updatePreview(){
 if(!analysis || !selected || !mesh || meshHash!==analysis.mesh?.sha256){viewer.clear();return;}
 try{viewer.set(mesh,selected.R_design_to_print,selected.t_mm);byId('mesh-status').textContent='Mesh fingerprint matched. Displaying the supplied design-to-print transform.';}
 catch(e){viewer.clear();byId('mesh-status').textContent=e.message;}
}
byId('view-iso').onclick=()=>viewer.view('iso');byId('view-top').onclick=()=>viewer.view('top');
byId('mesh-file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;const request=++meshRequest;
 try{if(file.size>100*1024*1024)throw Error('Preview supports STL files up to 100 MB.');const raw=await file.arrayBuffer(), hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),b=>b.toString(16).padStart(2,'0')).join('');
 if(request!==meshRequest)return;if(hash!==analysis?.mesh?.sha256)throw Error('STL fingerprint does not match this analysis. Load the referenced mesh.');
 mesh=parseSTL(raw);meshHash=hash;byId('mesh-status').textContent='Mesh matched. Choose a pose to preview it.';updatePreview();
 }catch(e){if(request!==meshRequest)return;mesh=null;meshHash=null;viewer.clear();byId('mesh-status').textContent=e.message;}
};
const metricNames = {F_L_max:'Layer failure index · conservative corner',F_L_max_vendor_corner:'Layer failure index · vendor-ratio corner',F_L_max_at_mm:'Peak sample location (design frame)',F_L_p99:'99th percentile layer failure index',ovh_fail_mm2:'Overhang area',bridge_candidate_mm2:'Potential bridge area',v_unsupported_mm2:'Voxel unsupported area',brg_worst_span_mm:'Longest bridge span',contact_mm2:'Bed contact',com_margin_mm:'Centre-of-mass margin',base_min_width_mm:'Minimum base width',height_mm:'Height'};
function text(tag, value, parent) {const node=document.createElement(tag);node.textContent=value;parent.append(node);return node;}
function formatted(column) {
  if (!column || column.value === null || column.value === undefined || column.verdict === 'NOT_CHECKED') return 'Not checked';
  const value = Array.isArray(column.value) ? column.value.map(x=>typeof x==='number'?x.toLocaleString(undefined,{maximumFractionDigits:3}):String(x)).join(', ') : typeof column.value === 'number' ? column.value.toLocaleString(undefined,{maximumFractionDigits:3}) : String(column.value);
  return `${column.verdict === 'FAIL' ? 'FAIL · ' : ''}${value}${column.unit && column.unit!=='1' ? ' '+column.unit : ''}${column.provisional ? ' · provisional' : ''}`;
}
function remember() {if(selected) decisions.set(selected.id,byId('rationale').value);}
function choose(candidate) {
  remember();selected=candidate;byId('pose-name').textContent=candidate.id;
  byId('direction').textContent=`Build direction (design frame): ${(candidate.build_dir_design || []).join(', ')}`;
  const design=candidate.columns?.F_L_max,vendor=candidate.columns?.F_L_max_vendor_corner;
  byId('strength-range').textContent=Number.isFinite(design?.value)&&Number.isFinite(vendor?.value)?`Material-corner range: ${Math.min(design.value,vendor.value).toFixed(3)}–${Math.max(design.value,vendor.value).toFixed(3)}. Conservative design corner: ${design.value.toFixed(3)}. ${design.fidelity||'FE prescreen; provisional.'}`:'Strength comparison is not checked for both material corners.';
  byId('reasons').replaceChildren();
  const reasons=Array.isArray(candidate.reasons)?candidate.reasons:[];
  reasons.forEach(r=>text('li',String(r),byId('reasons')));
  if(!candidate.feasible && !reasons.length)text('li','This candidate is marked infeasible; the analysis did not supply a reason.',byId('reasons'));
  const interfaces=candidate.columns?.interface_roofs;
  if(interfaces?.verdict==='FAIL')text('li','Interface review: '+interfaces.fidelity,byId('reasons'));
  else if(interfaces?.value)text('li','Interface roof declarations checked; geometry and sliced toolpaths still require verification.',byId('reasons'));
  byId('metrics').replaceChildren();
  for(const [key,label] of Object.entries(metricNames)) {
    const column=candidate.columns?.[key];text('dt',label,byId('metrics'));
    text('dd',formatted(column)+(column?.level?` · ${column.level}`:''),byId('metrics'));
  }
  byId('rationale').value=decisions.get(candidate.id)||'';
  byId('export').disabled=false;renderRows();updatePreview();
}
function renderRows() {
  byId('rows').replaceChildren();
  const rows=analysis.candidates.filter(c=>!byId('feasible-only').checked || c.feasible);
  for(const c of rows) {
    const tr=text('tr','',byId('rows'));if(c.id===selected?.id)tr.className='selected';
    const button=text('button',c.id,text('td','',tr));button.type='button';button.setAttribute('aria-pressed',String(c.id===selected?.id));button.onclick=()=>choose(c);
    for(const key of ['F_L_max','ovh_fail_mm2','contact_mm2'])text('td',formatted(c.columns?.[key]),tr);
    text('td',c.feasible?'Fits / stable; review checks':'Needs review',tr);
  }
  if(!rows.length){const td=text('td','No candidates match this filter.',text('tr','',byId('rows')));td.colSpan=5;}
}
byId('table-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;const request=++tableRequest;
  try {
    const raw=await file.text(), data=JSON.parse(raw);
    if(!data.schema || !Array.isArray(data.candidates) || !data.candidates.length)throw Error('Expected an orientation table with a schema and candidates.');
    const ids=new Set();
    for(const c of data.candidates){if(typeof c.id!=='string'||ids.has(c.id)||!c.columns||!Array.isArray(c.build_dir_design)||c.build_dir_design.length!==3||!c.build_dir_design.every(Number.isFinite))throw Error('Each candidate needs a unique id, columns and a finite build direction.');ids.add(c.id);}
    const bytes=new TextEncoder().encode(raw);const nextFingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    if(request!==tableRequest)return;
    fingerprint=nextFingerprint;analysis=data;selected=null;meshRequest++;mesh=null;meshHash=null;viewer.clear();byId('mesh-status').textContent='Load '+(data.mesh?.path?.split('/').pop()||'the matching STL')+' to preview the part.';decisions.clear();byId('workspace').hidden=false;
    byId('part-name').textContent=typeof data.problem==='string'?data.problem:(data.problem?.id||'Part orientation study');
    byId('evidence').textContent=[data.establishes,...(Array.isArray(data.does_not_establish)?data.does_not_establish.map(x=>'Not established: '+x):[data.does_not_establish])].filter(Boolean).map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' · ');
    byId('status').textContent=`Loaded ${data.candidates.length} candidate poses. Select one to inspect it.`;
    byId('pose-name').textContent='Choose a candidate';byId('direction').textContent='';byId('strength-range').textContent='';byId('reasons').replaceChildren();byId('metrics').replaceChildren();byId('rationale').value='';resetPlan();byId('export').disabled=true;byId('export-status').textContent='';renderRows();
  }catch(error){if(request!==tableRequest)return;analysis=null;selected=null;byId('workspace').hidden=true;byId('status').textContent=`Could not load table: ${error.message}`;}
};
byId('feasible-only').onchange=()=>{if(analysis)renderRows();};
function addHelper(region={}) {
  const box=document.createElement('fieldset');box.className='helper-region';box.dataset.id=region.id||crypto.randomUUID();
  text('legend',region.name||'Helper region',box);
  for(const [key,label,placeholder] of [['name','Name','e.g. Rear seat rib'],['location','Location on the part','e.g. Between the rear seat and wall plate'],['purpose','Load-carrying purpose','What load should this reinforcement carry?'],['keep_clear','Interfaces and clearances to preserve','e.g. Rod bore, washer seats, assembly access']]) {
    const wrapper=text('label',label,box),field=document.createElement(key==='name'?'input':'textarea');
    field.dataset.key=key;field.value=region[key]||'';field.placeholder=placeholder;
    if(key==='name'){field.type='text';field.oninput=()=>box.querySelector('legend').textContent=field.value.trim()||'Helper region';}else field.rows=2;
    wrapper.append(field);
  }
  const remove=text('button','Remove region',box);remove.type='button';remove.className='secondary';remove.onclick=()=>box.remove();
  byId('helper-regions').append(box);
}
function resetPlan(){
  byId('walls').value=4;byId('skin').value=1.6;byId('shell-only').checked=false;byId('helper-panel').hidden=false;
  byId('helper-regions').replaceChildren();byId('draft-status').textContent='';addHelper();
}
function planInput(){return {walls:Number(byId('walls').value),skin_mm:Number(byId('skin').value),rationale:byId('rationale').value,shell_only:byId('shell-only').checked,
  helper_regions:Array.from(byId('helper-regions').children,box=>({id:box.dataset.id,...Object.fromEntries(Array.from(box.querySelectorAll('[data-key]'),field=>[field.dataset.key,field.value]))}))};}
byId('add-helper').onclick=()=>addHelper();
byId('shell-only').onchange=()=>byId('helper-panel').hidden=byId('shell-only').checked;
byId('draft-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;const request=tableRequest,openRequest=++draftRequest;
  try{
    const raw=JSON.parse(await file.text());if(openRequest!==draftRequest)return;if(request!==tableRequest)throw Error('The analysis changed while opening the draft. Open it again.');
    const restored=Plan.restore(raw,analysis,fingerprint),input=restored.input;
    choose(restored.candidate);byId('rationale').value=input.rationale;decisions.set(restored.candidate.id,input.rationale);
    byId('walls').value=input.walls;byId('skin').value=input.skin_mm;byId('shell-only').checked=input.shell_only;byId('helper-panel').hidden=input.shell_only;
    byId('helper-regions').replaceChildren();input.helper_regions.forEach(addHelper);
    byId('draft-status').textContent=restored.migrated?'Legacy notes restored. Complete each helper location and interface constraint before exporting.':'Draft restored against its original analysis. You can revise it and export again.';
    byId('export-status').textContent='';
  }catch(error){if(openRequest!==draftRequest)return;byId('draft-status').textContent='Could not reopen draft: '+error.message;}
};
byId('export').onclick=()=>{
  try{
    remember();const draft=Plan.create(analysis,fingerprint,selected,planInput());
    const blob=new Blob([JSON.stringify(draft,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download='massing-plan.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    byId('export-status').textContent='Draft exported. It includes the source fingerprint and outstanding verification steps.';
  }catch(error){byId('export-status').textContent=error.message;}
};
