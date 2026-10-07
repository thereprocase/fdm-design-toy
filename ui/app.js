'use strict';
const byId = id => document.getElementById(id);
let analysis = null, selected = null, fingerprint = null, tableRequest = 0;
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
const metricNames = {F_L_max:'Maximum layer failure index',F_L_p99:'99th percentile layer failure index',ovh_fail_mm2:'Overhang area',bridge_candidate_mm2:'Potential bridge area',v_unsupported_mm2:'Voxel unsupported area',brg_worst_span_mm:'Longest bridge span',contact_mm2:'Bed contact',com_margin_mm:'Centre-of-mass margin',base_min_width_mm:'Minimum base width',height_mm:'Height'};
function text(tag, value, parent) {const node=document.createElement(tag);node.textContent=value;parent.append(node);return node;}
function formatted(column) {
  if (!column || column.value === null || column.value === undefined || column.verdict === 'NOT_CHECKED') return 'Not checked';
  const value = typeof column.value === 'number' ? column.value.toLocaleString(undefined,{maximumFractionDigits:3}) : String(column.value);
  return `${column.verdict === 'FAIL' ? 'FAIL · ' : ''}${value}${column.unit ? ' '+column.unit : ''}${column.provisional ? ' · provisional' : ''}`;
}
function remember() {if(selected) decisions.set(selected.id,byId('rationale').value);}
function choose(candidate) {
  remember();selected=candidate;byId('pose-name').textContent=candidate.id;
  byId('direction').textContent=`Build direction (design frame): ${(candidate.build_dir_design || []).join(', ')}`;
  byId('reasons').replaceChildren();
  const reasons=Array.isArray(candidate.reasons)?candidate.reasons:[];
  reasons.forEach(r=>text('li',String(r),byId('reasons')));
  if(!candidate.feasible && !reasons.length)text('li','This candidate is marked infeasible; the analysis did not supply a reason.',byId('reasons'));
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
    byId('pose-name').textContent='Choose a candidate';byId('direction').textContent='';byId('reasons').replaceChildren();byId('metrics').replaceChildren();byId('rationale').value='';byId('helpers').value='';byId('export').disabled=true;byId('export-status').textContent='';renderRows();
  }catch(error){if(request!==tableRequest)return;analysis=null;selected=null;byId('workspace').hidden=true;byId('status').textContent=`Could not load table: ${error.message}`;}
};
byId('feasible-only').onchange=()=>{if(analysis)renderRows();};
byId('export').onclick=()=>{
  remember();const walls=Number(byId('walls').value),skin=Number(byId('skin').value),rationale=byId('rationale').value.trim(),helpers=byId('helpers').value.trim();
  if(!selected || !Number.isInteger(walls)||walls<1||walls>20||!Number.isFinite(skin)||skin<.1||skin>20||!rationale||!helpers){byId('export-status').textContent='Add a choice rationale and helper intent, with 1–20 walls and 0.1–20 mm skins.';return;}
  const draft={schema:'fdmgen.massing-plan.v0.1',status:'draft_requires_verification',source:{orientation_table_sha256:fingerprint,orientation_schema:analysis.schema,problem:analysis.problem,mesh:analysis.mesh},orientation:{...selected,designer_decision:{choice:'selected_for_planning',rationale}},massing:{body:'fixed',walls,skin_mm:skin,helper_infill_percent:100,sparse_infill_structural_credit:false,helper_intent:helpers},outstanding_checks:['Create and validate helper geometry','Verify interfaces and helper bonding','Slice and check credited material and printability','Verify load cases and material evidence; physical testing remains separate']};
  const blob=new Blob([JSON.stringify(draft,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='massing-plan.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);byId('export-status').textContent='Draft exported. It includes the source fingerprint and outstanding verification steps.';
};
