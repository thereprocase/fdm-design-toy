'use strict';
const byId = id => document.getElementById(id);
let analysis = null, selected = null, fingerprint = null, tableRequest = 0, draftRequest = 0;
const decisions = new Map();
let proposalOrigin=null,sourceTableBytes=null,referencePose=null;
const removedHelpers=[];
let draftCheckpoint=null,draftCheckpointKind='new';
byId('plan-pose').onclick=()=>{document.querySelector('.massing').scrollIntoView({block:'start'});byId('walls').focus({preventScroll:true});};
byId('review-poses').onclick=()=>document.querySelector('.candidates').scrollIntoView({block:'start'});
const viewer = new PartViewer(byId('part-view'));
byId('all-helper-labels').onchange=()=>{viewer.showAllLabels=byId('all-helper-labels').checked;viewer.schedule();};
let mesh=null,meshHash=null,meshRequest=0,meshBounds=null,activeHelper=null;
byId('return-helper').onclick=()=>{
 if(!activeHelper?.isConnected)return;
 setActiveHelper(activeHelper);
 const target=activeHelper.querySelector(activeHelper.querySelector('[data-spatial]').checked?'[data-geometry="center_mm"]':'[data-key="name"]');
 target.focus({preventScroll:true});target.scrollIntoView({block:'center'});
};
function updatePreview(){
 if(!analysis || !selected || !mesh || meshHash!==analysis.mesh?.sha256){cancelSurfacePlacement();viewer.clear();return;}
 try{viewer.set(mesh,selected.R_design_to_print,selected.t_mm);byId('mesh-status').textContent='Mesh fingerprint matched. Displaying the supplied design-to-print transform.';updateRegions();}
 catch(e){cancelSurfacePlacement();viewer.clear();byId('mesh-status').textContent=e.message;}
}
byId('focus-helper').onclick=()=>{if(activeHelper)viewer.focusRegion(activeHelper.dataset.id);};
byId('view-whole').onclick=()=>viewer.frameAll();
byId('zoom-in').onclick=()=>viewer.zoomBy(1.4);byId('zoom-out').onclick=()=>viewer.zoomBy(1/1.4);
byId('view-iso').onclick=()=>viewer.view('iso');byId('view-top').onclick=()=>viewer.view('top');
byId('view-x').onclick=()=>viewer.view('print-x');byId('view-y').onclick=()=>viewer.view('print-y');
byId('mesh-file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;cancelSurfacePlacement();const request=++meshRequest;
 try{if(file.size>100*1024*1024)throw Error('Preview supports STL files up to 100 MB.');const raw=await file.arrayBuffer(), hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),b=>b.toString(16).padStart(2,'0')).join('');
 if(request!==meshRequest)return;if(hash!==analysis?.mesh?.sha256)throw Error('STL fingerprint does not match this analysis. Load the referenced mesh.');
 mesh=parseSTL(raw);meshBounds={min:[Infinity,Infinity,Infinity],max:[-Infinity,-Infinity,-Infinity]};for(let i=0;i<mesh.length;i++){meshBounds.min[i%3]=Math.min(meshBounds.min[i%3],mesh[i]);meshBounds.max[i%3]=Math.max(meshBounds.max[i%3],mesh[i]);}meshHash=hash;byId('mesh-options').open=false;byId('mesh-status').textContent='Mesh matched. Choose a pose to preview it.';updatePreview();
 }catch(e){
  if(request!==meshRequest)return;cancelSurfacePlacement();
  const retained=mesh&&meshHash===analysis?.mesh?.sha256;
  if(!retained){mesh=null;meshHash=null;meshBounds=null;viewer.clear();}
  byId('mesh-options').open=true;
  byId('mesh-status').textContent=e.message+(retained?' The previously matched mesh is retained; the rejected file is not displayed.':'');
 }
};
const metricNames = {F_L_max:'Layer failure index · conservative corner',F_L_max_vendor_corner:'Layer failure index · vendor-ratio corner',F_L_max_at_mm:'Peak sample location (design frame)',F_L_p99:'99th percentile layer failure index',ovh_fail_mm2:'Overhang area',bridge_candidate_mm2:'Potential bridge area',v_unsupported_mm2:'Voxel unsupported area',brg_worst_span_mm:'Longest bridge span',contact_mm2:'Bed contact',com_margin_mm:'Centre-of-mass margin',base_min_width_mm:'Minimum base width',height_mm:'Height'};
function text(tag, value, parent) {const node=document.createElement(tag);node.textContent=value;parent.append(node);return node;}
function metricNumber(value){return value===0?'0':Math.abs(value)<.001?value.toExponential(2):value.toLocaleString(undefined,{maximumFractionDigits:3});}
function formatted(column) {
  if (!column || column.value === null || column.value === undefined || column.verdict === 'NOT_CHECKED') return 'Not checked';
  const value = Array.isArray(column.value) ? column.value.map(x=>typeof x==='number'?metricNumber(x):String(x)).join(', ') : typeof column.value === 'number' ? metricNumber(column.value) : String(column.value);
  return `${column.verdict === 'FAIL' ? 'FAIL · ' : ''}${value}${column.unit && column.unit!=='1' ? ' '+column.unit : ''}${column.provisional ? ' · provisional' : ''}`;
}
function shellColumn(candidate) {
  const c=candidate.columns?.t_shell_thin_fraction;
  return c?.rule==='SHELL-001'&&c.unit==='fraction'&&c.level==='T'&&['PASS','FAIL'].includes(c.verdict)&&Number.isFinite(c.value)&&c.value>=0&&c.value<=1?c:null;
}
function shellSummary(candidate) {
  const c=shellColumn(candidate);
  return c?`${c.verdict} · ${(100*c.value).toLocaleString(undefined,{maximumFractionDigits:3})}% thin · T${c.provisional?' · provisional':''}`:'Not checked';
}
function validBridgeColumn(c){
 return c?.rule==='BRG-001'&&c.level==='T'&&c.unit==='mm'&&['PASS','FAIL'].includes(c.verdict)&&Number.isFinite(c.value)&&c.value>=0&&Number.isFinite(c.limit_mm)&&c.limit_mm>0;
}
function renderComparison(){
 byId('pin-reference').disabled=!selected;byId('clear-reference').disabled=!referencePose;
 const panel=byId('reference-comparison');panel.hidden=!referencePose||!selected;
 byId('comparison-rows').replaceChildren();
 byId('reference-status').textContent=!referencePose?'Select a pose to keep as a comparison reference.':
   referencePose.id===selected?.id?`Reference: ${referencePose.id}. Select another pose to compare; this does not change the reference.`:
   `Reference: ${referencePose.id}. Selected for planning: ${selected?.id||'none'}.`;
 if(panel.hidden)return;
 byId('reference-name').textContent=`Reference: ${referencePose.id}`;byId('comparison-name').textContent=`Selected: ${selected.id}`;
 for(const [key,label,ceiling] of [['F_L_max','Layer failure · design corner'],['F_L_max_vendor_corner','Layer failure · vendor corner'],['ovh_fail_mm2','Overhang area'],['contact_mm2','Bed contact'],['height_mm','Print height'],['t_support_segments','Support segments · T'],['t_shell_thin_fraction','Thin shell fraction · T'],['t_bridge_span_external_mm','External bridge strand maximum · T'],['t_bridge_span_internal_mm','Internal bridge strand maximum · T'],['t_bridge_span_external_mm','External bridge ceiling maximum · T',true],['t_bridge_span_internal_mm','Internal bridge ceiling maximum · T',true]]){
   const row=text('tr','',byId('comparison-rows'));text('th',label,row).scope='row';
   for(const candidate of [referencePose,selected]){
     const column=candidate.columns?.[key],cell=text('td','',row);
     text('span',ceiling?(validBridgeColumn(column)&&Number.isFinite(column.ceiling_span_mm)&&column.ceiling_span_mm>=0?`${metricNumber(column.ceiling_span_mm)} mm · supplementary`:'Not recorded'):key==='t_shell_thin_fraction'?shellSummary(candidate):formatted(column),cell);
     if(ceiling)text('p','Independent maximum over evaluated roads; may occur on a different road from the strand maximum. The recorded verdict uses the strand model.',cell).className='hint';
     if(column){const details=text('details','',cell);text('summary','Context',details);
       text('p',[column.rule,column.level,column.fidelity||'Method and settings not supplied.'].filter(Boolean).join(' · '),details);}
   }
 }
}
byId('pin-reference').onclick=()=>{if(!selected)return;referencePose=selected;renderComparison();byId('reference-comparison').open=true;};
byId('clear-reference').onclick=()=>{referencePose=null;renderComparison();byId('pin-reference').focus({preventScroll:true});};
function hasSlice(candidate) {
  const c=candidate.columns?.t_support_segments;
  return Number.isFinite(c?.value)&&c.value>=0&&c.verdict!=='NOT_CHECKED';
}
function renderBridge(candidate) {
  const panel=byId('pose-bridges');panel.replaceChildren();
  for(const [key,label] of [['t_bridge_span_external_mm','External bridges'],['t_bridge_span_internal_mm','Internal bridges']]){
    const c=candidate.columns?.[key],section=text('article','',panel);
    text('h4',label,section);
    const valid=validBridgeColumn(c);
    text('p',valid?`${c.verdict} · ${c.value.toLocaleString(undefined,{maximumFractionDigits:3})} mm longest unsupported strand run; recorded limit ${c.limit_mm.toLocaleString()} mm · T${c.provisional?' · provisional':''}`:'Not checked',section);
    if(valid&&c.verdict==='FAIL'){
      const note=text('p','This tool provides no verified helper-edit remedy for this bridge failure. The recorded FAIL uses the strand model. Changing helper boxes does not establish a fix; revised geometry needs fresh slicing and checks.',section);note.className='warning';note.dataset.bridgeRemedy='';
      for(const [label,url]of [['Bracket bridge-model investigation (#9)', 'https://github.com/thereprocase/fdm-design-toy/issues/9'], ['Bridge coupon work (#12)', 'https://github.com/thereprocase/fdm-design-toy/issues/12'], ['Owner decisions: bracket infill and coupon printing (#17)', 'https://github.com/thereprocase/fdm-design-toy/issues/17#issuecomment-6049963530']]){note.append(document.createTextNode(' '));const link=text('a',label,note);link.href=url;link.target='_blank';link.rel='noopener';}
    }
    if(valid)text('p',c.fidelity||'Method and slice scope not supplied.',section);
    if(valid){
      text('p',`Ceiling span maximum: ${Number.isFinite(c.ceiling_span_mm)&&c.ceiling_span_mm>=0?c.ceiling_span_mm.toLocaleString(undefined,{maximumFractionDigits:3})+' mm':'not recorded'}. This supplementary model is twice the distance to the nearest support below; the recorded verdict uses the strand span. These are independent per-measure maxima over all evaluated roads of this type, not two measurements of one road. Physical behaviour needs testing.`,section);
      const cov=c.coverage,kind=key.includes('external')?'external_roads':'internal_roads';
      const complete=cov&&['bridge_roads','external_roads','internal_roads'].every(k=>Number.isInteger(cov[k])&&cov[k]>=0)&&cov.external_roads+cov.internal_roads===cov.bridge_roads&&Number.isFinite(cov.cell_mm)&&cov.cell_mm>0&&Number.isFinite(cov.max_cantilever_mm)&&cov.max_cantilever_mm>=0;
      text('p',complete?`${cov[kind].toLocaleString()} ${label.toLowerCase()} evaluated (${cov.bridge_roads.toLocaleString()} bridge roads total). Raster cell ${cov.cell_mm} mm; longest cantilever across all bridge roads ${cov.max_cantilever_mm} mm (reported, not judged).${cov[kind]===0?' No roads of this type were evaluated; a zero span is not a successful bridge trial.':''}`:'Bridge-road coverage is not established by this column.',section);
    }
    if(c){const details=text('details','',section);text('summary','Recorded bridge column, coverage and provenance',details);const raw=text('pre',JSON.stringify(c,null,2),details);raw.style.whiteSpace='pre-wrap';raw.style.overflowWrap='anywhere';}
  }
}
function failedColumns(candidate) {
  return Object.entries(candidate.columns||{}).filter(([,c])=>c?.verdict==='FAIL');
}
function renderFailedChecks(candidate) {
  const failures=failedColumns(candidate),list=byId('failed-checks');list.replaceChildren();
  byId('failed-check-count').textContent=failures.length?`${failures.length} recorded failed check${failures.length===1?'':'s'} to review. Bed fit does not clear these checks.`:'No recorded FAIL columns. Missing and unchecked evidence still require review; this is not qualification.';
  const names={...metricNames,t_shell_thin_fraction:'Thin shell fraction',t_bridge_span_external_mm:'External bridge span',t_bridge_span_internal_mm:'Internal bridge span',interface_roofs:'Interface roofs',t_support_segments:'Support segments'};
  for(const [key,c] of failures){
    const item=text('li','',list);text('strong',`${names[key]||key.replaceAll('_',' ')} · ${c.rule||'rule not recorded'} · ${c.level||'level not recorded'}${c.provisional?' · provisional':''}`,item);
    text('p',c.fidelity||'No producer explanation supplied; inspect this recorded column.',item);
  }
}
function remember() {if(selected) decisions.set(selected.id,byId('rationale').value);}
function renderPlanningPose(){
 byId('planning-pose').textContent=selected?`Planning pose: ${selected.id}. This is the pose saved in the draft.`:'No pose selected for this draft.';
 if(!selected){byId('planning-pose-checks').textContent='';return;}
 const fit=selected.feasible===true?'fits / stable':selected.feasible===false?'needs review':'not recorded';
 const failures=failedColumns(selected).length;
 byId('planning-pose-checks').textContent=`Design-frame build direction: ${selected.build_dir_design.join(', ')}. Table fit/stability: ${fit}; ${failures} recorded failed check${failures===1?'':'s'}. These results do not verify your helper edits.`;
}
function choose(candidate) {
  cancelSurfacePlacement();remember();selected=candidate;renderPlanningPose();byId('pose-name').textContent=candidate.id;
  byId('direction').textContent=`Build direction (design frame): ${(candidate.build_dir_design || []).join(', ')}`;
  const design=candidate.columns?.F_L_max,vendor=candidate.columns?.F_L_max_vendor_corner;
  byId('strength-range').textContent=Number.isFinite(design?.value)&&Number.isFinite(vendor?.value)&&design.verdict!=='NOT_CHECKED'&&vendor.verdict!=='NOT_CHECKED'?`Material-corner range: ${metricNumber(Math.min(design.value,vendor.value))}–${metricNumber(Math.max(design.value,vendor.value))}. Conservative design corner: ${metricNumber(design.value)}. ${design.fidelity||'FE prescreen; provisional.'}`:'Strength comparison is not checked for both material corners.';
  renderFailedChecks(candidate);
  byId('reasons').replaceChildren();
  const reasons=Array.isArray(candidate.reasons)?candidate.reasons:[];
  reasons.forEach(r=>text('li',String(r),byId('reasons')));
  if(!candidate.feasible && !reasons.length)text('li','This candidate is marked infeasible; the analysis did not supply a reason.',byId('reasons'));
  const interfaces=candidate.columns?.interface_roofs;
  if(interfaces?.verdict==='FAIL')text('li','Interface review: '+interfaces.fidelity,byId('reasons'));
  else if(interfaces?.value)text('li','Interface roof declarations checked; geometry and sliced toolpaths still require verification.',byId('reasons'));
  byId('toolpath-metrics').replaceChildren();
  for(const [key,label] of [['t_support_segments','Support segments'],['t_support_volume_mm3','Support volume'],['t_credited_mm3','Credited material volume']]){
    const column=candidate.columns?.[key];text('dt',label,byId('toolpath-metrics'));text('dd',formatted(column)+(column?' · toolpath evidence':''),byId('toolpath-metrics'));
  }
  const slice=candidate.columns?.t_support_segments;
  byId('toolpath-settings').textContent=slice?.fidelity||'No pose slice supplied. These quantities are not checked.';
  const creditedFidelity=candidate.columns?.t_credited_mm3?.fidelity||'';
  byId('credited-scope').textContent=slice?.fidelity&&creditedFidelity.startsWith(slice.fidelity)?'Credited volume: '+creditedFidelity.slice(slice.fidelity.length).replace(/^;\s*/, ''):creditedFidelity;
  renderBridge(candidate);
  const shell=shellColumn(candidate);
  byId('pose-shell-summary').textContent=shellSummary(candidate);
  byId('pose-shell-fidelity').textContent=shell?.fidelity||'No usable SHELL-001 toolpath screen supplied for this pose.';
  const coverage=shell?.coverage;
  const coverageValid=coverage&&['samples_requested','measured','unmeasured'].every(k=>Number.isInteger(coverage[k])&&coverage[k]>=0)&&coverage.measured+coverage.unmeasured===coverage.samples_requested&&Number.isFinite(coverage.clipped_outside_grid_mm3)&&coverage.clipped_outside_grid_mm3>=0;
  byId('pose-shell-coverage').textContent=!shell?'':coverageValid?`${coverage.measured.toLocaleString()} of ${coverage.samples_requested.toLocaleString()} surface samples measured; ${coverage.unmeasured.toLocaleString()} unmeasured; ${coverage.clipped_outside_grid_mm3.toLocaleString()} mm³ clipped outside the raster. Thin fraction is over measured samples only.`:'Sample coverage is not established by this column.';
  byId('pose-shell-receipt').textContent=JSON.stringify(candidate.columns?.t_shell_thin_fraction||null,null,2);
  byId('pose-shell-details').hidden=!candidate.columns?.t_shell_thin_fraction;
  byId('metrics').replaceChildren();
  for(const [key,label] of Object.entries(metricNames)) {
    const column=candidate.columns?.[key];text('dt',label,byId('metrics'));
    text('dd',formatted(column)+(column?.level?` · ${column.level}`:''),byId('metrics'));
  }
  byId('rationale').value=decisions.get(candidate.id)||'';
  byId('export').disabled=false;byId('plan-pose').disabled=false;renderComparison();renderRows();updatePreview();updateRegions();
}
function renderRows() {
  byId('rows').replaceChildren();
  const rows=analysis.candidates.filter(c=>(!byId('feasible-only').checked || c.feasible===true)&&(!byId('sliced-only').checked || hasSlice(c)));
  byId('feasible-scope').textContent=typeof analysis.feasible_scope==='string'&&analysis.feasible_scope.trim()?'Producer feasibility scope: '+analysis.feasible_scope:'Feasibility scope not supplied by this table. A feasible flag does not mean all checks pass.';
  const sortKey=byId('pose-sort').value;
  if(sortKey!=='analysis'){
    const value=c=>{const m=c.columns?.[sortKey];return m?.verdict!=='NOT_CHECKED'&&Number.isFinite(m?.value)?m.value:null;};
    rows.sort((a,b)=>{
      const x=value(a),y=value(b);
      if(x===null)return y===null?0:1;
      if(y===null)return -1;
      return sortKey==='contact_mm2'?y-x:x-y;
    });
  }
  byId('review-selected').disabled=!selected;byId('review-selected').textContent=selected?'Review selected pose: '+selected.id:'Review selected pose';
  byId('reveal-pose').hidden=!selected||rows.some(c=>c.id===selected.id);
  const sliced=analysis.candidates.filter(c=>hasSlice(c)).length;
  byId('pose-count').textContent=`Showing ${rows.length} of ${analysis.candidates.length} poses; ${sliced} have measured slices.${selected&&!rows.some(c=>c.id===selected.id)?' Selected pose '+selected.id+' is hidden by this filter.':''}`;
  for(const c of rows) {
    const tr=text('tr','',byId('rows'));if(c.id===selected?.id)tr.className='selected';
    const button=text('button',c.id,text('td','',tr));button.type='button';button.setAttribute('aria-pressed',String(c.id===selected?.id));button.onclick=()=>{
      choose(c);
      // Row rendering replaces the activated button; preserve keyboard position.
      byId('rows').querySelector('[aria-pressed="true"]')?.focus({preventScroll:true});
    };
    for(const key of ['F_L_max','ovh_fail_mm2','contact_mm2','t_support_segments'])text('td',formatted(c.columns?.[key]),tr);
    text('td',shellSummary(c),tr);
    text('td',formatted(c.columns?.height_mm),tr);
    const bed=c.columns?.fits_bed;
    const bedKnown=bed?.rule==='BED-001'&&bed.level==='M'&&typeof bed.value==='boolean'&&bed.verdict===(bed.value?'PASS':'FAIL');
    const bedCell=text('td',bedKnown?(bed.value?'Fits':'Does not fit')+' · M'+(bed.provisional?' · provisional':''):'Not checked',tr);
    if(bedKnown&&bed.fidelity)bedCell.title=bed.fidelity;

    const failures=failedColumns(c).length;
    text('td',(c.feasible===true?'Fits / stable':c.feasible===false?'Fit needs review':'Fit not recorded')+`; ${failures} recorded failed check${failures===1?'':'s'}`,tr);
  }
  if(!rows.length){
    const td=text('td','No candidates match these filters. ',text('tr','',byId('rows')));td.colSpan=9;
    const reset=text('button','Show all poses',td);reset.type='button';reset.className='secondary';
    reset.onclick=()=>{
      byId('feasible-only').checked=false;byId('sliced-only').checked=false;renderRows();
      const target=byId('rows').querySelector('[aria-pressed="true"]')||byId('rows').querySelector('button');
      target?.focus();target?.scrollIntoView({block:'nearest',inline:'nearest'});
    };
  }
}
byId('review-selected').onclick=()=>{if(selected){const heading=byId('pose-name');heading.focus({preventScroll:true});heading.scrollIntoView({block:'start'});}};
byId('reveal-pose').onclick=()=>{
  if(!selected)return;
  if(selected.feasible!==true)byId('feasible-only').checked=false;
  if(!hasSlice(selected))byId('sliced-only').checked=false;
  renderRows();
  const button=byId('rows').querySelector('[aria-pressed="true"]');
  button?.focus();button?.scrollIntoView({block:'nearest',inline:'nearest'});
};
byId('table-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;const request=++tableRequest;
  try {
    const bytes=await file.arrayBuffer(), raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes), data=JSON.parse(raw);
    if(!data || typeof data.schema!=='string' || !data.schema || !Array.isArray(data.candidates) || !data.candidates.length)throw Error('Expected an orientation table with a schema and candidates.');
    if(data.mesh?.path!==undefined&&typeof data.mesh.path!=='string')throw Error('Mesh path must be text.');
    for(const key of ['interfaces','keep_outs']){
      if(data[key]===undefined)continue;
      if(!Array.isArray(data[key]))throw Error(`${key} must be a list.`);
      const seen=new Set();
      for(const item of data[key]){
        if(!item||typeof item.id!=='string'||!item.id||seen.has(item.id))throw Error(`${key} entries need unique nonempty ids.`);
        seen.add(item.id);
      }
    }
    const ids=new Set();
    for(const c of data.candidates){if(!c||typeof c.id!=='string'||!c.id||ids.has(c.id)||!c.columns||typeof c.columns!=='object'||Array.isArray(c.columns)||!Array.isArray(c.build_dir_design)||c.build_dir_design.length!==3||!c.build_dir_design.every(Number.isFinite))throw Error('Each candidate needs a unique id, columns and a finite build direction.');ids.add(c.id);try{Plan.validatePose(c);}catch(error){throw Error(`Candidate ${c.id}: ${error.message}`);}}
    const nextFingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    if(request!==tableRequest)return;
    if(!allowDraftReplacement('load another orientation table')){byId('status').textContent='Table replacement cancelled. The current table and draft are unchanged.';event.target.value='';return;}
    fingerprint=nextFingerprint;sourceTableBytes=bytes;byId('download-table').disabled=false;byId('table-download-status').textContent='';analysis=data;viewer.setBed(data.bed);selected=null;referencePose=null;renderComparison();meshRequest++;mesh=null;meshHash=null;cancelSurfacePlacement();viewer.clear();byId('mesh-status').textContent='Load '+(data.mesh?.path?.split('/').pop()||'the matching STL')+' to preview the part.';decisions.clear();byId('workspace').hidden=false;
    byId('part-name').textContent=typeof data.problem==='string'?data.problem:(data.problem?.id||'Part orientation study');
    byId('evidence').textContent=[data.establishes,...(Array.isArray(data.does_not_establish)?data.does_not_establish.map(x=>'Not established: '+x):[data.does_not_establish])].filter(Boolean).map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' · ');
    byId('status').textContent=`Loaded ${data.candidates.length} candidate poses. Select one to inspect it.`;
    byId('pose-name').textContent='Choose a candidate';byId('direction').textContent='';byId('strength-range').textContent='';byId('reasons').replaceChildren();byId('failed-check-count').textContent='';byId('failed-checks').replaceChildren();byId('metrics').replaceChildren();byId('toolpath-metrics').replaceChildren();byId('toolpath-settings').textContent='';byId('credited-scope').textContent='';byId('pose-bridges').replaceChildren();byId('pose-shell-summary').textContent='';byId('pose-shell-fidelity').textContent='';byId('pose-shell-coverage').textContent='';byId('pose-shell-receipt').textContent='';byId('pose-shell-details').hidden=true;byId('rationale').value='';resetPlan();byId('export').disabled=true;byId('plan-pose').disabled=true;byId('export-status').textContent='';renderRows();resumeReviewDraft();
  }catch(error){if(request!==tableRequest)return;byId('status').textContent=`Could not load table: ${error.message}${analysis?' The previous table and current draft remain available.':''}`;}
};
byId('pose-sort').onchange=byId('feasible-only').onchange=byId('sliced-only').onchange=()=>{if(analysis)renderRows();};
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
  const keepOutRefs=text('div','',box);keepOutRefs.className='interface-refs';
  text('p',analysis?.keep_outs?.length?'Keep-outs to track for this helper (global constraints still apply):':'This table has no keep-out declarations. Use a newer table to record keep-out references.',keepOutRefs);
  for(const item of analysis?.keep_outs||[]){const label=text('label','',keepOutRefs),check=document.createElement('input');check.type='checkbox';check.dataset.keepOutId=item.id;check.checked=region.keep_clear?.keep_out_ids?.includes(item.id)||false;label.append(check,document.createTextNode(' '+item.id));const info=text('details','',keepOutRefs);text('summary',item.id+' constraint',info);text('p',item.rule||'No rule description supplied.',info);if(item.derivation)text('p',item.derivation,info);text('p',`Declared frame: ${item.frame||'unspecified'}. Model: ${item.type||'unspecified'}. Selection records intent; geometry checks run in the exporter.`,info);}
  const clearanceLabel=text('label','Required clearance, mm (leave blank until known)',box),clearance=document.createElement('input');clearance.type='number';clearance.min='0';clearance.step='0.1';clearance.dataset.clearance='';clearance.value=region.keep_clear?.clearance_mm??'';clearanceLabel.append(clearance);
  const toggleLabel=text('label','',box),toggle=document.createElement('input');toggle.type='checkbox';toggle.dataset.spatial='';toggle.checked=!!region.geometry;toggleLabel.append(toggle,document.createTextNode(' Place a box-shaped planning region'));
  const spatial=text('div','',box);spatial.className='spatial';spatial.hidden=!toggle.checked;
  text('p','Design-frame millimetres. Centre and size stay attached to the part across print poses.',spatial);
  for(const key of ['center_mm','size_mm']){
    const group=text('div','',spatial);group.className='geometry-group';group.setAttribute('role','group');
    const title=key==='center_mm'?'Box centre — design frame':'Box dimensions — design frame';group.setAttribute('aria-label',title);
    text('h4',title,group);
    const fields=text('div','',group);fields.className='geometry-grid';
    for(let axis=0;axis<3;axis++){
      const label=text('label',`${key==='center_mm'?'Centre':'Size'} ${'XYZ'[axis]}, mm`,fields),field=document.createElement('input');
      field.type='number';field.step='0.1';field.dataset.geometry=key;field.dataset.axis=axis;field.value=region.geometry?.[key]?.[axis]??(key==='center_mm'?0:10);label.append(field);
    }
  }
  const nudge=text('div','',spatial);nudge.className='nudge-controls';
  const stepLabel=text('label','Move centre by',nudge),step=document.createElement('select');step.dataset.nudgeStep='';
  for(const value of [.1,.4,1,5]){const option=text('option',value+' mm',step);option.value=value;}step.value='1';stepLabel.append(step);
  const moves=text('div','',nudge);moves.className='nudge-buttons';
  const status=text('p','Moves use design axes, independent of the print pose. Clearance and bonding are not checked here.',nudge);status.setAttribute('role','status');status.dataset.nudgeStatus='';
  let lastMove=null;
  const centres=()=>[...box.querySelectorAll('[data-geometry="center_mm"]')];
  const undo=text('button','Undo last centre move',nudge);undo.type='button';undo.className='secondary';undo.disabled=true;
  for(let axis=0;axis<3;axis++)for(const sign of [-1,1]){
    const move=text('button',`Move ${'XYZ'[axis]} ${sign<0?'−':'+'}`,moves);move.type='button';move.className='secondary';
    move.onclick=()=>{
      const fields=centres(),before=fields.map(f=>f.value);
      if(before.some(v=>v.trim()===''||!Number.isFinite(Number(v)))){status.textContent='Complete all three centre coordinates before moving.';return;}
      const value=Number(before[axis])+sign*Number(step.value);
      if(!Number.isFinite(value)){status.textContent='Centre move is outside the numeric range.';return;}
      cancelSurfacePlacement();lastMove=before;fields[axis].value=Number(value.toFixed(6));undo.disabled=false;setActiveHelper(box);updateRegions();
      status.textContent=`Moved centre ${sign<0?'−':'+'}${step.value} mm along design ${'XYZ'[axis]}. Geometry checks have not been rerun.`;
    };
  }
  undo.onclick=()=>{if(!lastMove)return;cancelSurfacePlacement();centres().forEach((f,i)=>f.value=lastMove[i]);lastMove=null;undo.disabled=true;updateRegions();status.textContent='Previous centre restored. Geometry checks have not been rerun.';};
  box.addEventListener('input',event=>{if(event.target.matches('[data-geometry="center_mm"]')){cancelSurfacePlacement();lastMove=null;undo.disabled=true;}});
  const place=text('button','Place centre on part',spatial);place.type='button';place.className='secondary';
  place.onclick=()=>{
    if(!mesh||!selected){byId('placement-status').textContent='Load a matching mesh and choose a pose first.';byId('part-view').scrollIntoView({block:'center'});return;}
    setActiveHelper(box);byId('return-helper').hidden=false;byId('cancel-placement').hidden=false;
    byId('placement-status').textContent='Click a surface to place the region centre. Orbit first if needed. Press Escape or Cancel placement to stop.';byId('part-view').style.cursor='crosshair';byId('part-view').scrollIntoView({block:'center'});
    viewer.onPick=point=>{if(!point){byId('placement-status').textContent='No surface at that point. Click the part.';return;}lastMove=centres().map(f=>f.value);undo.disabled=false;for(let a=0;a<3;a++)box.querySelector(`[data-geometry="center_mm"][data-axis="${a}"]`).value=point[a].toFixed(3);cancelSurfacePlacement();byId('placement-status').textContent='Region centre placed on the surface; edit its size or move the centre inward as needed. Undo last centre move restores the previous coordinates.';updateRegions();};
  };
  const z=text('p','',spatial);z.className='hint';z.dataset.printZ='';
  toggle.onchange=()=>{if(!toggle.checked)cancelSurfacePlacement();spatial.hidden=!toggle.checked;updateRegions();};
  box.addEventListener('input',updateRegions);
  // List actions choose their resulting selection on activation. Selecting on
  // focus can reveal preview controls and move the button between down/up.
  box.addEventListener('focusin',event=>{if(!event.target.closest('.helper-list-action'))setActiveHelper(box,false);});
  const duplicate=text('button','Duplicate region',box);duplicate.type='button';duplicate.className='secondary helper-list-action';
  duplicate.onclick=()=>{
    const copy=addHelper();
    const source=[...box.querySelectorAll('input,textarea')],target=[...copy.querySelectorAll('input,textarea')];
    source.forEach((field,i)=>{target[i].value=field.value;if(field.type==='checkbox')target[i].checked=field.checked;});
    const name=copy.querySelector('[data-key="name"]');name.value=(name.value.trim()||'Helper')+' copy';
    copy.querySelector('legend').textContent=name.value;
    copy.querySelector('.spatial').hidden=!copy.querySelector('[data-spatial]').checked;
    box.parentNode.insertBefore(copy,box.nextSibling);
    setActiveHelper(copy);name.focus({preventScroll:true});name.scrollIntoView({block:'center'});
  };
  const remove=text('button','Remove region',box);remove.type='button';remove.className='secondary helper-list-action';remove.onclick=()=>{
    const name=box.querySelector('[data-key="name"]').value.trim()||'Unnamed helper';
    removedHelpers.push({box,index:[...byId('helper-regions').children].indexOf(box)});
    if(removedHelpers.length>20)removedHelpers.shift();
    box.remove();if(activeHelper===box)activeHelper=null;
    cancelSurfacePlacement();
    byId('undo-remove').disabled=false;
    byId('remove-status').textContent=`Removed ${name}. Undo remove restores its fields and position. Up to 20 removals are kept until another draft or table is loaded.`;
    updateRegions();byId('undo-remove').focus({preventScroll:true});
  };
  const editor=document.createElement('details');editor.className='helper-editor';editor.open=true;
  text('summary','Edit helper settings',editor);
  for(const child of [...box.children].slice(1))editor.append(child);
  box.append(editor);byId('helper-regions').append(box);updateRegions();return box;
}
function resetHandoff(){
 byId('handoff-command').textContent='fdmgen massing DRAFT.json --table TABLE.json --template PROFILE.3mf --out out/massing';
 byId('handoff-readiness').textContent='Export this draft to populate its filenames and geometry-input summary.';
 renderEvidenceHandoff(null);
}
function resetPlan(){
  renderPlanningPose();
  cancelSurfacePlacement();clearDraftError();
  resetHandoff();
  clearRemovalHistory();
  proposalOrigin=null;renderProposal();
  activeHelper=null;byId('return-helper').hidden=true;byId('mesh-options').open=true;
  byId('walls').value=4;byId('skin').value=1.6;byId('shell-only').checked=false;byId('helper-panel').hidden=false;
  byId('helper-regions').replaceChildren();byId('draft-status').textContent='';addHelper();checkpointDraft('new');
}
function regionInput(box){
 const r={id:box.dataset.id,...Object.fromEntries(Array.from(box.querySelectorAll('[data-key]'),field=>[field.dataset.key,field.value]))};
 r.keep_clear={note:r.keep_clear,interface_ids:Array.from(box.querySelectorAll('[data-interface-id]:checked'),f=>f.dataset.interfaceId),keep_out_ids:Array.from(box.querySelectorAll('[data-keep-out-id]:checked'),f=>f.dataset.keepOutId),clearance_mm:box.querySelector('[data-clearance]').value===''?null:Number(box.querySelector('[data-clearance]').value)};
 r.geometry=box.querySelector('[data-spatial]').checked?{type:'box',frame:'design',...Object.fromEntries(['center_mm','size_mm'].map(key=>[key,Array.from(box.querySelectorAll(`[data-geometry="${key}"]`),field=>field.value===''?NaN:Number(field.value))]))}:null;
 return r;
}
function planInput(){return {walls:Number(byId('walls').value),skin_mm:Number(byId('skin').value),rationale:byId('rationale').value,shell_only:byId('shell-only').checked,
 helper_regions:Array.from(byId('helper-regions').children,regionInput),...(proposalOrigin?{proposal:proposalOrigin}:{})};}
// Preserve raw form values: incomplete numeric fields must still count as edits.
function draftFormState(){
 return JSON.stringify({pose:selected?.id||null,walls:byId('walls').value,skin:byId('skin').value,
  rationale:byId('rationale').value,shellOnly:byId('shell-only').checked,
  helpers:[...byId('helper-regions').children].map(box=>({id:box.dataset.id,
   fields:[...box.querySelectorAll('input,textarea')].map(field=>field.type==='checkbox'?field.checked:field.value)}))});
}
function updateDraftState(){
 const changed=hasDraftEdits();
 const label=byId('draft-edit-state');label.className=changed?'warning':'hint';
 label.textContent=draftCheckpointKind==='new'
  ?(changed?'Draft edited. Download it to keep these changes.':'No draft downloaded in this session.')
  :changed?`Changes since ${draftCheckpointKind==='opened'?'reopening':'the last download'}. Export an updated draft before running checks.`
  :`No edits since ${draftCheckpointKind==='opened'?'reopening this draft':'the last draft download'}.`;
 const handoff=byId('handoff-snapshot');handoff.className=changed?'warning':'hint';
 handoff.textContent=draftCheckpointKind==='downloaded'
  ?changed?'The commands below describe the last downloaded draft. Current edits are not included; export an updated draft before running them.':'The commands below describe the last downloaded draft. Use the actual saved filenames on your worker.'
  :'No export from this draft is recorded in this session. Export it to populate the commands below, or substitute your saved file paths in the templates.';

}
function checkpointDraft(kind){draftCheckpointKind=kind;draftCheckpoint=draftFormState();updateDraftState();}
function hasDraftEdits(){return draftCheckpoint!==null&&draftFormState()!==draftCheckpoint;}
function allowDraftReplacement(action){return !hasDraftEdits()||confirm(`Discard current draft edits and ${action}? Cancel to export your current draft first.`);}
window.addEventListener('beforeunload',event=>{if(hasDraftEdits()){event.preventDefault();event.returnValue='';}});
document.addEventListener('input',event=>{
 if(event.target.matches('#rationale,#walls,#skin,#shell-only,.helper-region input,.helper-region textarea'))updateDraftState();
});
function helperLabel(box){
 const boxes=[...byId('helper-regions').children],nameOf=b=>b.querySelector('[data-key="name"]').value.trim()||'Helper region',name=nameOf(box);
 return boxes.filter(b=>nameOf(b)===name).length>1?`${name} (helper ${boxes.indexOf(box)+1})`:name;
}
function updateRegions(){
 const valid=[],warnings=byId('region-warnings');warnings.replaceChildren();
 const editors=new Map([...byId('helper-regions').children].map(box=>[box.dataset.id,box]));
 const warn=(message,ids,field='[data-geometry="center_mm"]')=>{
   const item=text('li',message,warnings);
   for(const id of ids){const box=editors.get(id);if(!box)continue;
     const name=helperLabel(box);
     const button=text('button',`Edit ${name}`,item);button.type='button';button.className='secondary';button.dataset.helperId=id;
     button.onclick=()=>{setActiveHelper(box);const target=box.querySelector(field);target?.focus({preventScroll:true});target?.scrollIntoView({block:'center'});};
   }
 };

 refreshHelperSelector();
 if(!byId('shell-only').checked)for(const box of byId('helper-regions').children){const r=regionInput(box),z=box.querySelector('[data-print-z]');z.textContent='';if(!r.geometry)continue;
  try{Plan.geometry(r.geometry);r.active=box===activeHelper;r.previewName=helperLabel(box);valid.push(r);
    if(mesh&&meshBounds&&[0,1,2].some(k=>r.geometry.center_mm[k]+r.geometry.size_mm[k]/2<meshBounds.min[k]||r.geometry.center_mm[k]-r.geometry.size_mm[k]/2>meshBounds.max[k]))warn(`${r.name||'Region'}: box lies outside the part bounds and cannot bond to the body.`,[r.id]);
    if(r.geometry.size_mm.some(x=>x<.84))warn(`${r.name||'Region'}: an edge is below the 0.84 mm planning screen (2 × assumed 0.42 mm line width).`,[r.id],`[data-geometry="size_mm"][data-axis="${r.geometry.size_mm.findIndex(x=>x<.84)}"]`);
    if(selected){const corners=transformMesh(boxCorners(r.geometry),selected.R_design_to_print,selected.t_mm),zs=Array.from(corners).filter((_,i)=>i%3===2);z.textContent=`Print Z extent: ${Math.min(...zs).toFixed(3)}–${Math.max(...zs).toFixed(3)} mm. Layer snapping and body bonding remain unchecked.`;}
  }catch(e){warn(`${r.name||'Region'}: ${e.message}`,[r.id]);}
 }
 for(let i=0;i<valid.length;i++)for(let j=i+1;j<valid.length;j++){
  if(['center_mm','size_mm'].every(key=>valid[i].geometry[key].every((v,k)=>v===valid[j].geometry[key][k])))warn(`${valid[i].name||'Region'} / ${valid[j].name||'Region'}: identical planning boxes. Move, resize or remove the redundant copy as needed.`,[valid[i].id,valid[j].id]);
  if(Plan.boxSeparation(valid[i].geometry,valid[j].geometry).needs_review)warn(`${valid[i].name||'Region'} / ${valid[j].name||'Region'}: overlap or separation is below the nominal 0.84 mm screen. Review sliver modifiers.`,[valid[i].id,valid[j].id]);
 }
 viewer.setRegions(valid);byId('focus-helper').disabled=!viewer.vertices||!valid.some(r=>r.active);updateDraftState();
}
function clearRemovalHistory(){
 removedHelpers.length=0;byId('undo-remove').disabled=true;byId('remove-status').textContent='';
}
byId('undo-remove').onclick=()=>{
 const entry=removedHelpers.pop();if(!entry)return;
 const parent=byId('helper-regions');parent.insertBefore(entry.box,parent.children[entry.index]||null);
 setActiveHelper(entry.box);
 const name=entry.box.querySelector('[data-key="name"]');name.focus({preventScroll:true});name.scrollIntoView({block:'center'});
 byId('undo-remove').disabled=!removedHelpers.length;
 byId('remove-status').textContent=`Restored ${name.value.trim()||'unnamed helper'}. ${removedHelpers.length} earlier removal(s) can still be undone.`;
};
byId('add-helper').onclick=()=>{
 const box=addHelper();setActiveHelper(box);
 const name=box.querySelector('[data-key="name"]');name.focus({preventScroll:true});name.scrollIntoView({block:'center'});
};
byId('shell-only').onchange=()=>{cancelSurfacePlacement();byId('helper-panel').hidden=byId('shell-only').checked;updateRegions();};
byId('draft-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;const request=tableRequest,openRequest=++draftRequest;
  try{
    const raw=JSON.parse(await file.text());if(openRequest!==draftRequest)return;if(request!==tableRequest)throw Error('The analysis changed while opening the draft. Open it again.');
    Plan.restore(raw,analysis,fingerprint); // Reject an incompatible file before asking to discard edits.
    if(!allowDraftReplacement('open this saved draft')){byId('draft-status').textContent='Draft replacement cancelled. Current edits are unchanged.';event.target.value='';return;}
    restoreDraft(raw);
  }catch(error){if(openRequest!==draftRequest)return;byId('draft-status').textContent='Could not reopen draft: '+error.message;}
};
function invalidDraftField(){
 const walls=byId('walls'),skin=byId('skin'),w=Number(walls.value),s=Number(skin.value);
 if(!Number.isInteger(w)||w<1||w>20)return walls;
 if(!Number.isFinite(s)||s<.1||s>20)return skin;
 const rationale=byId('rationale');if(!rationale.value.trim())return rationale;
 if(byId('shell-only').checked)return null;
 const boxes=[...byId('helper-regions').children];
 if(!boxes.length)return byId('add-helper');
 for(const box of boxes){
  for(const key of ['name','location','purpose']){const f=box.querySelector(`[data-key="${key}"]`);if(!f.value.trim())return f;}
  const clearance=box.querySelector('[data-clearance]');if(clearance.value!==''&&(!Number.isFinite(Number(clearance.value))||Number(clearance.value)<0))return clearance;
  const note=box.querySelector('[data-key="keep_clear"]');if(!note.value.trim())return note;
  if(box.querySelector('[data-spatial]').checked)for(const f of box.querySelectorAll('[data-geometry]'))if(f.value===''||!Number.isFinite(Number(f.value))||f.dataset.geometry==='size_mm'&&Number(f.value)<=0)return f;
 }
 return null;
}
function clearDraftError(){
 for(const f of document.querySelectorAll('[data-export-error]')){f.removeAttribute('aria-invalid');f.removeAttribute('aria-errormessage');delete f.dataset.exportError;}
}
document.addEventListener('input',event=>{if(event.target.hasAttribute('data-export-error'))clearDraftError();});
function downloadFile(contents,name){
 const url=URL.createObjectURL(new Blob([contents],{type:'application/json'})),a=document.createElement('a');
 a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function sourceTableFilename(){return `orientation-table-${fingerprint.slice(0,12)}.json`;}
function renderEvidenceHandoff(draft){
 const handoff=Plan.evidenceHandoff(draft,draft?sourceTableFilename():'TABLE.json');
 byId('handoff-project').textContent=handoff.project;byId('handoff-baseline').textContent=handoff.baseline;
 byId('evidence-command').textContent=handoff.command;
 byId('handoff-placeholders').hidden=!handoff.placeholders;
}

byId('download-table').onclick=()=>{
 if(!sourceTableBytes||!fingerprint)return;
 downloadFile(sourceTableBytes,sourceTableFilename());
 byId('table-download-status').textContent=`Original table bytes downloaded as ${sourceTableFilename()}. SHA-256: ${fingerprint}.`;
};
byId('export').onclick=()=>{
  clearDraftError();
  try{
    remember();const draft=Plan.create(analysis,fingerprint,selected,planInput());
    downloadFile(JSON.stringify(draft,null,2)+'\n',Plan.filename(draft));checkpointDraft('downloaded');
    byId('handoff-command').textContent=`fdmgen massing ${Plan.filename(draft)} --table ${sourceTableFilename()} --template PROFILE.3mf --out out/massing`;
    renderEvidenceHandoff(draft);
    byId('export-status').textContent='Draft exported. It includes the source fingerprint and outstanding verification steps.';
    const incomplete=draft.massing.helper_regions.filter(h=>!h.geometry);
    byId('handoff-readiness').textContent=incomplete.length?`Last exported draft: ${incomplete.length} helper(s) without a box: ${incomplete.map(h=>h.name).join(', ')}. Enable their spatial controls and set centre/size, then save again before running the exporter.`:'Last exported draft: geometry inputs needed for export are present. The command still checks source fingerprints and helper geometry.';
    byId('handoff').open=true;
  }catch(error){
    byId('export-status').textContent=error.message;
    const field=invalidDraftField();
    if(field){const helper=field.closest('.helper-region');if(helper)setActiveHelper(helper);if(field.matches('input,textarea')){field.dataset.exportError='';field.setAttribute('aria-invalid','true');field.setAttribute('aria-errormessage','export-status');}field.focus();field.scrollIntoView({block:'center'});}
  }
};

function restoreDraft(raw){
    const restored=Plan.restore(raw,analysis,fingerprint),input=restored.input;
    clearRemovalHistory();
    clearDraftError();
    proposalOrigin=input.proposal||null;renderProposal();
    choose(restored.candidate);byId('rationale').value=input.rationale;decisions.set(restored.candidate.id,input.rationale);
    byId('walls').value=input.walls;byId('skin').value=input.skin_mm;byId('shell-only').checked=input.shell_only;byId('helper-panel').hidden=input.shell_only;
    byId('helper-regions').replaceChildren();input.helper_regions.forEach(addHelper);
    byId('draft-status').textContent=restored.migrated?'Legacy notes restored. Complete each helper location and interface constraint before exporting.':'Draft restored against its original analysis. You can revise it and export again.';
    resetHandoff();byId('export-status').textContent='';updateRegions();checkpointDraft('opened');
}

let pendingReview=null;
function clearReviewTransfer(){
 pendingReview=null;try{sessionStorage.removeItem('fdmgen-review-edit');}catch(error){}
 byId('review-transfer').hidden=true;
 if(location.hash==='#review-edit')history.replaceState(null,'',location.pathname+location.search);
}
byId('cancel-review-transfer').onclick=clearReviewTransfer;
function resumeReviewDraft(){
 if(!pendingReview)return;
 try{
  restoreDraft(pendingReview.draft);
  const target=[...document.querySelectorAll('.helper-region')].find(box=>box.dataset.id===pendingReview.helper_id);
  if(target){target.scrollIntoView({block:'center'});target.querySelector('[data-key="name"]').focus({preventScroll:true});}
  else{byId('walls').scrollIntoView({block:'center'});byId('walls').focus({preventScroll:true});}
  clearReviewTransfer();
 }catch(error){byId('review-transfer-status').textContent='Draft retained for review: '+error.message;}
}
if(location.hash==='#review-edit'){
 byId('review-transfer').hidden=false;
 try{
  pendingReview=JSON.parse(sessionStorage.getItem('fdmgen-review-edit'));
  if(!pendingReview?.draft||(pendingReview.helper_id!==null&&typeof pendingReview.helper_id!=='string'))throw Error('No transferable draft was found.');
  byId('review-transfer-status').textContent='Load the original orientation table to restore the reviewed draft and focus '+(pendingReview.helper_id===null?'its shell controls.':'its helper.')+' Its exact fingerprint must match. The saved draft and review results remain unchanged.';
 }catch(error){pendingReview=null;byId('review-transfer-status').textContent=error.message+' Load the original table and reopen the saved draft manually.';}
}

function cancelSurfacePlacement(){viewer.onPick=null;byId('part-view').style.cursor='';byId('placement-status').textContent='';byId('cancel-placement').hidden=true;}
function stopSurfacePlacement(){
 if(!viewer.onPick)return;
 cancelSurfacePlacement();byId('placement-status').textContent='Placement cancelled. Helper coordinates are unchanged.';
 byId('part-view').focus({preventScroll:true});
}
byId('cancel-placement').onclick=stopSurfacePlacement;
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&viewer.onPick){event.preventDefault();stopSurfacePlacement();}});
function setActiveHelper(box,expand=true){
 if(activeHelper!==box)cancelSurfacePlacement();
 if(box&&expand)box.querySelector('.helper-editor').open=true;
 activeHelper=box;byId('return-helper').hidden=!box;updateRegions();
}
function refreshHelperSelector(){
 if(activeHelper&&!activeHelper.isConnected)activeHelper=null;
 const select=byId('preview-helper');select.replaceChildren();
 const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose a helper';select.append(placeholder);
 const boxes=[...byId('helper-regions').children],shellOnly=byId('shell-only').checked;
 boxes.forEach((box,i)=>{const option=document.createElement('option'),name=helperLabel(box);box.querySelector('legend').textContent=name;option.value=box.dataset.id;option.textContent=name+(box.querySelector('[data-spatial]').checked?'':' — no box yet');select.append(option);box.classList.toggle('active-helper',box===activeHelper&&!shellOnly);});
 byId('return-helper').hidden=shellOnly||!activeHelper;
 select.disabled=shellOnly||!boxes.length;select.value=!shellOnly&&activeHelper?activeHelper.dataset.id:'';
 byId('collapse-other-helpers').disabled=shellOnly||!activeHelper;
 byId('expand-helpers').disabled=shellOnly||!boxes.length;
 byId('active-helper-status').textContent=shellOnly?'Shell-only draft: helper boxes are excluded.':activeHelper?`Editing ${helperLabel(activeHelper)}. ${activeHelper.querySelector('[data-spatial]').checked?'Its box has the solid blue outline; other boxes are dashed orange.':'Enable its spatial box to preview the region.'}`:'Focus a helper field to highlight its box.';
}
byId('collapse-other-helpers').onclick=()=>{for(const box of byId('helper-regions').children)box.querySelector('.helper-editor').open=box===activeHelper;};
byId('expand-helpers').onclick=()=>{for(const editor of document.querySelectorAll('.helper-editor'))editor.open=true;};
byId('preview-helper').onchange=()=>{
 const box=[...byId('helper-regions').children].find(b=>b.dataset.id===byId('preview-helper').value);
 setActiveHelper(box||null);
 if(box){box.scrollIntoView({block:'center'});box.querySelector('[data-key="name"]').focus({preventScroll:true});}
};

function renderProposal(){
 const panel=byId('proposal-evidence');panel.replaceChildren();panel.hidden=!proposalOrigin;
 if(!proposalOrigin)return;
 const p=proposalOrigin;
 text('h3','Original machine proposal',panel);
 text('p','Historical proposal provenance. Editing helpers, shell settings or the pose does not rerun the seed or its checks. Export and verify the current plan again.',panel).className='warning';
 text('p',p.label||'A proposal for review; not an optimum or a strength result.',panel);
 if(p.status==='no_viable_helpers')text('p','No viable helpers were proposed. The empty helper list does not establish that shell-only is sufficient. Review the rejected clusters and revise the plan deliberately.',panel).className='warning';
 text('p',`Generator: ${p.generator}. Original pose: ${p.pose?.id||'not recorded'}. Stress frame: ${p.stress?.frame||'not recorded'}.`,panel);
 if(p.stress?.sha256)text('p',`Recorded stress SHA256: ${p.stress.sha256}. The browser has not verified the stress file.`,panel);
 if(Array.isArray(p.accepted)&&p.accepted.length){
  text('h4','Originally proposed helpers',panel);const list=text('ul','',panel);
  for(const h of p.accepted.filter(h=>h&&typeof h==='object'))text('li',`${h.id}: cluster ${h.cluster}, ${h.cells} cells, F_L max ${h.F_L_max}. Nearest modelled restraint: ${Array.isArray(h.nearest_restraint)?h.nearest_restraint.join(' · ')+' mm':'not recorded'}. Original values, not recomputed for edits.`,list);
 }
 if(Array.isArray(p.rejected)&&p.rejected.length){
  const details=text('details','',panel);text('summary',`${p.rejected.length} rejected clusters at generation`,details);const list=text('ul','',details);
  for(const item of p.rejected)text('li',item&&typeof item==='object'?`Cluster ${item.cluster} · ${item.cells??'unrecorded'} cells: ${item.reason||JSON.stringify(item)}`:String(item),list);
 }
 if(Array.isArray(p.sensitivity)&&p.sensitivity.length){
  const details=text('details','',panel);text('summary','Restraint exclusion sensitivity (original proposal)',details);text('pre',JSON.stringify(p.sensitivity,null,2),details);
 }
 const details=text('details','',panel);text('summary','Complete original proposal provenance',details);text('pre',JSON.stringify(p,null,2),details);
}
