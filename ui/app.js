'use strict';
const byId = id => document.getElementById(id);
let analysis = null, selected = null, fingerprint = null, tableRequest = 0, draftRequest = 0;
const decisions = new Map();
byId('plan-pose').onclick=()=>{document.querySelector('.massing').scrollIntoView({block:'start'});byId('walls').focus({preventScroll:true});};
byId('review-poses').onclick=()=>document.querySelector('.candidates').scrollIntoView({block:'start'});
const viewer = new PartViewer(byId('part-view'));
let mesh=null,meshHash=null,meshRequest=0,meshBounds=null,activeHelper=null;
byId('return-helper').onclick=()=>{if(activeHelper?.isConnected){activeHelper.scrollIntoView({block:'center'});activeHelper.querySelector('[data-geometry="center_mm"]')?.focus({preventScroll:true});}};
function updatePreview(){
 if(!analysis || !selected || !mesh || meshHash!==analysis.mesh?.sha256){viewer.clear();return;}
 try{viewer.set(mesh,selected.R_design_to_print,selected.t_mm);byId('mesh-status').textContent='Mesh fingerprint matched. Displaying the supplied design-to-print transform.';updateRegions();}
 catch(e){viewer.clear();byId('mesh-status').textContent=e.message;}
}
byId('zoom-in').onclick=()=>viewer.zoomBy(1.4);byId('zoom-out').onclick=()=>viewer.zoomBy(1/1.4);
byId('view-iso').onclick=()=>viewer.view('iso');byId('view-top').onclick=()=>viewer.view('top');
byId('mesh-file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;const request=++meshRequest;
 try{if(file.size>100*1024*1024)throw Error('Preview supports STL files up to 100 MB.');const raw=await file.arrayBuffer(), hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),b=>b.toString(16).padStart(2,'0')).join('');
 if(request!==meshRequest)return;if(hash!==analysis?.mesh?.sha256)throw Error('STL fingerprint does not match this analysis. Load the referenced mesh.');
 mesh=parseSTL(raw);meshBounds={min:[Infinity,Infinity,Infinity],max:[-Infinity,-Infinity,-Infinity]};for(let i=0;i<mesh.length;i++){meshBounds.min[i%3]=Math.min(meshBounds.min[i%3],mesh[i]);meshBounds.max[i%3]=Math.max(meshBounds.max[i%3],mesh[i]);}meshHash=hash;byId('mesh-options').open=false;byId('mesh-status').textContent='Mesh matched. Choose a pose to preview it.';updatePreview();
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
  byId('export').disabled=false;byId('plan-pose').disabled=false;renderRows();updatePreview();updateRegions();
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
    byId('pose-name').textContent='Choose a candidate';byId('direction').textContent='';byId('strength-range').textContent='';byId('reasons').replaceChildren();byId('metrics').replaceChildren();byId('rationale').value='';resetPlan();byId('export').disabled=true;byId('plan-pose').disabled=true;byId('export-status').textContent='';renderRows();
  }catch(error){if(request!==tableRequest)return;analysis=null;selected=null;byId('workspace').hidden=true;byId('status').textContent=`Could not load table: ${error.message}`;}
};
byId('feasible-only').onchange=()=>{if(analysis)renderRows();};
function addHelper(region={}) {
  const box=document.createElement('fieldset');box.className='helper-region';box.dataset.id=region.id||crypto.randomUUID();
  text('legend',region.name||'Helper region',box);
  for(const [key,label,placeholder] of [['name','Name','e.g. Rear seat rib'],['location','Location on the part','e.g. Between the rear seat and wall plate'],['purpose','Load-carrying purpose','What load should this reinforcement carry?'],['keep_clear','Interfaces and clearances to preserve','e.g. Rod bore, washer seats, assembly access']]) {
    const wrapper=text('label',label,box),field=document.createElement(key==='name'?'input':'textarea');
    field.dataset.key=key;field.value=(key==='keep_clear'&&typeof region[key]==='object'?region[key]?.note:region[key])||'';field.placeholder=placeholder;
    if(key==='name'){field.type='text';field.oninput=()=>box.querySelector('legend').textContent=field.value.trim()||'Helper region';}else field.rows=2;
    wrapper.append(field);
  }
  const refs=text('div','',box);refs.className='interface-refs';text('p','Keep these interfaces clear:',refs);
  for(const item of analysis?.interfaces||[]){const label=text('label','',refs),check=document.createElement('input');check.type='checkbox';check.dataset.interfaceId=item.id;check.checked=region.keep_clear?.interface_ids?.includes(item.id)||false;label.append(check,document.createTextNode(' '+item.id));}
  const clearanceLabel=text('label','Required clearance, mm (leave blank until known)',box),clearance=document.createElement('input');clearance.type='number';clearance.min='0';clearance.step='0.1';clearance.dataset.clearance='';clearance.value=region.keep_clear?.clearance_mm??'';clearanceLabel.append(clearance);
  const toggleLabel=text('label','',box),toggle=document.createElement('input');toggle.type='checkbox';toggle.dataset.spatial='';toggle.checked=!!region.geometry;toggleLabel.append(toggle,document.createTextNode(' Place a box-shaped planning region'));
  const spatial=text('div','',box);spatial.className='spatial';spatial.hidden=!toggle.checked;
  text('p','Design-frame millimetres. Centre and size stay attached to the part across print poses.',spatial);
  const fields=text('div','',spatial);fields.className='geometry-grid';
  for(const key of ['center_mm','size_mm'])for(let axis=0;axis<3;axis++){
    const label=text('label',`${key==='center_mm'?'Centre':'Size'} ${'XYZ'[axis]}, mm`,fields),field=document.createElement('input');
    field.type='number';field.step='0.1';field.dataset.geometry=key;field.dataset.axis=axis;field.value=region.geometry?.[key]?.[axis]??(key==='center_mm'?0:10);label.append(field);
  }
  const place=text('button','Place centre on part',spatial);place.type='button';place.className='secondary';
  place.onclick=()=>{
    if(!mesh||!selected){byId('placement-status').textContent='Load a matching mesh and choose a pose first.';byId('part-view').scrollIntoView({block:'center'});return;}
    activeHelper=box;byId('return-helper').hidden=false;
    byId('placement-status').textContent='Click a surface to place the region centre. Orbit first if needed.';byId('part-view').style.cursor='crosshair';byId('part-view').scrollIntoView({block:'center'});
    viewer.onPick=point=>{if(!point){byId('placement-status').textContent='No surface at that point. Click the part.';return;}for(let a=0;a<3;a++)box.querySelector(`[data-geometry="center_mm"][data-axis="${a}"]`).value=point[a].toFixed(3);viewer.onPick=null;byId('part-view').style.cursor='';byId('placement-status').textContent='Region centre placed on the surface; edit its size or move the centre inward as needed.';updateRegions();};
  };
  const z=text('p','',spatial);z.className='hint';z.dataset.printZ='';
  toggle.onchange=()=>{spatial.hidden=!toggle.checked;updateRegions();};
  box.addEventListener('input',updateRegions);
  const remove=text('button','Remove region',box);remove.type='button';remove.className='secondary';remove.onclick=()=>{box.remove();if(activeHelper===box){activeHelper=null;byId('return-helper').hidden=true;}viewer.onPick=null;byId('part-view').style.cursor='';updateRegions();};
  byId('helper-regions').append(box);updateRegions();
}
function resetPlan(){
  activeHelper=null;byId('return-helper').hidden=true;byId('mesh-options').open=true;
  byId('walls').value=4;byId('skin').value=1.6;byId('shell-only').checked=false;byId('helper-panel').hidden=false;
  byId('helper-regions').replaceChildren();byId('draft-status').textContent='';addHelper();
}
function regionInput(box){
 const r={id:box.dataset.id,...Object.fromEntries(Array.from(box.querySelectorAll('[data-key]'),field=>[field.dataset.key,field.value]))};
 r.keep_clear={note:r.keep_clear,interface_ids:Array.from(box.querySelectorAll('[data-interface-id]:checked'),f=>f.dataset.interfaceId),keep_out_ids:[],clearance_mm:box.querySelector('[data-clearance]').value===''?null:Number(box.querySelector('[data-clearance]').value)};
 r.geometry=box.querySelector('[data-spatial]').checked?{type:'box',frame:'design',...Object.fromEntries(['center_mm','size_mm'].map(key=>[key,Array.from(box.querySelectorAll(`[data-geometry="${key}"]`),field=>field.value===''?NaN:Number(field.value))]))}:null;
 return r;
}
function planInput(){return {walls:Number(byId('walls').value),skin_mm:Number(byId('skin').value),rationale:byId('rationale').value,shell_only:byId('shell-only').checked,
 helper_regions:Array.from(byId('helper-regions').children,regionInput)};}
function updateRegions(){
 const valid=[],warnings=byId('region-warnings');warnings.replaceChildren();
 if(!byId('shell-only').checked)for(const box of byId('helper-regions').children){const r=regionInput(box),z=box.querySelector('[data-print-z]');z.textContent='';if(!r.geometry)continue;
  try{Plan.geometry(r.geometry);valid.push(r);
    if(mesh&&meshBounds&&[0,1,2].some(k=>r.geometry.center_mm[k]+r.geometry.size_mm[k]/2<meshBounds.min[k]||r.geometry.center_mm[k]-r.geometry.size_mm[k]/2>meshBounds.max[k]))text('li',`${r.name||'Region'}: box lies outside the part bounds and cannot bond to the body.`,warnings);
    if(r.geometry.size_mm.some(x=>x<.84))text('li',`${r.name||'Region'}: an edge is below the 0.84 mm planning screen (2 × assumed 0.42 mm line width).`,warnings);
    if(selected){const corners=transformMesh(boxCorners(r.geometry),selected.R_design_to_print,selected.t_mm),zs=Array.from(corners).filter((_,i)=>i%3===2);z.textContent=`Print Z extent: ${Math.min(...zs).toFixed(3)}–${Math.max(...zs).toFixed(3)} mm. Layer snapping and body bonding remain unchecked.`;}
  }catch(e){text('li',`${r.name||'Region'}: ${e.message}`,warnings);}
 }
 for(let i=0;i<valid.length;i++)for(let j=i+1;j<valid.length;j++){
  if(Plan.boxSeparation(valid[i].geometry,valid[j].geometry).needs_review)text('li',`${valid[i].name||'Region'} / ${valid[j].name||'Region'}: overlap or separation is below the nominal 0.84 mm screen. Review sliver modifiers.`,warnings);
 }
 viewer.setRegions(valid);
}
byId('add-helper').onclick=()=>addHelper();
byId('shell-only').onchange=()=>{byId('helper-panel').hidden=byId('shell-only').checked;updateRegions();};
byId('draft-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;const request=tableRequest,openRequest=++draftRequest;
  try{
    const raw=JSON.parse(await file.text());if(openRequest!==draftRequest)return;if(request!==tableRequest)throw Error('The analysis changed while opening the draft. Open it again.');
    const restored=Plan.restore(raw,analysis,fingerprint),input=restored.input;
    choose(restored.candidate);byId('rationale').value=input.rationale;decisions.set(restored.candidate.id,input.rationale);
    byId('walls').value=input.walls;byId('skin').value=input.skin_mm;byId('shell-only').checked=input.shell_only;byId('helper-panel').hidden=input.shell_only;
    byId('helper-regions').replaceChildren();input.helper_regions.forEach(addHelper);
    byId('draft-status').textContent=restored.migrated?'Legacy notes restored. Complete each helper location and interface constraint before exporting.':'Draft restored against its original analysis. You can revise it and export again.';
    byId('export-status').textContent='';updateRegions();
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
