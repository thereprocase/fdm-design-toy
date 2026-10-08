'use strict';
const byId = id => document.getElementById(id);
let analysis = null, selected = null, fingerprint = null, tableRequest = 0, draftRequest = 0;
const decisions = new Map();
let renderedPoseNotes=null;
let proposalOrigin=null,sourceTableBytes=null,referencePose=null,orientationEvidenceBundle=null,orientationRoad=null;
const removedHelpers=[];
let draftCheckpoint=null,draftCheckpointKind='new';
const savedPoseNotes=new Map();
byId('plan-pose').onclick=()=>{document.querySelector('.massing').scrollIntoView({block:'start'});byId('walls').focus({preventScroll:true});};
byId('review-poses').onclick=()=>document.querySelector('.candidates').scrollIntoView({block:'start'});
const viewer = new PartViewer(byId('part-view'));
function renderPoseRoads(){
 orientationRoad=null;viewer.setRoadWitness(null);byId('pose-road-buttons').replaceChildren();byId('pose-road-hide').hidden=true;byId('pose-road-selected').textContent='';byId('pose-road-source').textContent='';byId('pose-road-provenance').hidden=true;
 const item=orientationEvidenceBundle?.receipts.find(x=>x.entry.pose===selected?.id&&x.entry.check==='bridge-check');
 if(!item){byId('pose-road-status').textContent='Open an orientation evidence bundle and select a pose to locate its recorded bridges.';return;}
 try{
  const roads=BridgeLocations.locations(item.receipt,{orientation:selected,source:{mesh:analysis.mesh,orientation_table_sha256:orientationEvidenceBundle.manifest.table.root_sha256}});
  byId('pose-road-status').textContent=selected.id+' · '+item.entry.slice_kind+' · '+(roads.length?'Choose a recorded maximum. Matching STL required to draw it.':'This receipt has no location geometry; numeric bridge checks remain available.');
  byId('pose-road-source').textContent=JSON.stringify({receipt_sha256:item.entry.sha256,receipt:item.receipt},null,2);byId('pose-road-provenance').hidden=false;
  for(const road of roads){const button=text('button',road.role+' '+road.model+' · '+road.value_mm+' mm',byId('pose-road-buttons'));button.type='button';button.className='secondary';button.dataset.roadId=road.id;button.setAttribute('aria-pressed','false');
   button.onclick=()=>{cancelSurfacePlacement();orientationRoad=road;for(const choice of byId('pose-road-buttons').children)choice.setAttribute('aria-pressed',String(choice===button));viewer.setRoadWitness(road.source.design_mm);byId('pose-road-hide').hidden=false;byId('pose-road-selected').textContent=selected.id+' · '+item.entry.slice_kind+' · '+road.role+' '+road.model+' · '+road.value_mm+' mm. Dashed: full road; solid: bounded unsupported run; dot: ceiling witness. Drawn through the body for location only. Slicer roles do not prove open-air/core geometry or a helper remedy. Recorded slice only; not a check of current helper edits. This display does not change the draft.';};
  }
 }catch(error){byId('pose-road-status').textContent=error.message+' Numeric bridge checks remain available.';}
}
byId('pose-road-hide').onclick=()=>{const old=byId('pose-road-buttons').querySelector('[aria-pressed="true"]');old?.setAttribute('aria-pressed','false');orientationRoad=null;viewer.setRoadWitness(null);old?.focus({preventScroll:true});byId('pose-road-hide').hidden=true;byId('pose-road-selected').textContent='Bridge road hidden; source receipt retained.';};
byId('all-helper-labels').onchange=()=>{viewer.showAllLabels=byId('all-helper-labels').checked;viewer.schedule();};
let mesh=null,meshHash=null,meshRequest=0,meshBounds=null,activeHelper=null;
byId('return-helper').onclick=()=>{
 if(!activeHelper?.isConnected)return;
 setActiveHelper(activeHelper);
 const target=activeHelper.querySelector(activeHelper.querySelector('[data-spatial]').checked?'[data-geometry="center_mm"]':'[data-key="name"]');
 target.focus({preventScroll:true});target.scrollIntoView({block:'center'});
 document.querySelector('.preview').scrollTop=0;
};
let keepoutGeometry=null,keepoutRequest=0;
function updateKeepoutVisibility(){
 const items=keepoutGeometry?keepoutGeometry.items.filter(x=>byId('keepout-items').querySelector(`[data-keepout-preview="${CSS.escape(x.id)}"]`)?.checked):[];
 viewer.setKeepouts(items.map(x=>({...x,lines:KeepoutRender.segments(x)})));
 byId('keepout-visibility').hidden=!items.length;
 byId('keepout-visible-names').textContent=items.length?'Keep-out overlays enabled: '+items.map(x=>x.id).join(', ')+'. Magenta dashed lines · render only.':'';
}
byId('hide-keepouts').onclick=()=>{
 for(const input of byId('keepout-items').querySelectorAll('input'))input.checked=false;
 updateKeepoutVisibility();byId('part-view').focus({preventScroll:true});
};
function clearKeepouts(){
 keepoutRequest++;keepoutGeometry=null;updateKeepoutVisibility();byId('keepout-file').value='';byId('keepout-items').replaceChildren();byId('keepout-source').textContent='';byId('keepout-provenance').hidden=true;byId('keepout-status').textContent='No keep-out geometry loaded.';
}
function renderKeepoutOptions(){
 const list=byId('keepout-items');list.replaceChildren();updateKeepoutVisibility();
 for(const item of keepoutGeometry.items){
  const label=text('label','',list),input=document.createElement('input');input.type='checkbox';input.dataset.keepoutPreview=item.id;input.disabled=!item.rendered;label.append(input,document.createTextNode(' '+item.id));
  text('p',item.rendered?item.rule:'Not drawn: '+item.reason,list).className='hint';
  input.onchange=updateKeepoutVisibility;
 }
 byId('keepout-source').textContent=JSON.stringify(keepoutGeometry,null,2);byId('keepout-provenance').hidden=false;
}
byId('keepout-file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;const request=++keepoutRequest,tableHash=fingerprint;
 try{
  if(file.size>5*1024*1024)throw Error('Keep-out geometry supports JSON files up to 5 MB.');
  const data=JSON.parse(await file.text());if(request!==keepoutRequest)return;
  if(tableHash!==fingerprint)throw Error('The table changed; reopen the geometry.');
  KeepoutRender.validate(data,analysis,fingerprint);keepoutGeometry=data;renderKeepoutOptions();
  byId('keepout-status').textContent='Table and mesh fingerprints matched. Choose the constraints to draw; this does not change the draft.';
 }catch(e){if(request===keepoutRequest)byId('keepout-status').textContent=e.message+(keepoutGeometry?' Previously matched geometry and visibility are retained.':'');}
};
function updatePreview(){
 if(!analysis || !selected || !mesh || meshHash!==analysis.mesh?.sha256){cancelSurfacePlacement();viewer.clear();return;}
 try{viewer.set(mesh,selected.R_design_to_print,selected.t_mm);byId('mesh-status').textContent='Mesh fingerprint matched. Displaying the supplied design-to-print transform.';updateRegions();viewer.setRoadWitness(orientationRoad?.source.design_mm||null);}
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
function comparisonSliceKind(column){return ['shell-only','project'].includes(column?.receipt?.slice_kind)?column.receipt.slice_kind:null;}
function renderComparison(){
 byId('pin-reference').disabled=!selected;byId('clear-reference').disabled=!referencePose;
 const panel=byId('reference-comparison');panel.hidden=!referencePose||!selected;
 byId('comparison-rows').replaceChildren();
 byId('reference-status').textContent=!referencePose?'Select a pose to keep as a comparison reference.':
   referencePose.id===selected?.id?`Reference: ${referencePose.id}. Select another pose to compare; this does not change the reference.`:
   `Reference: ${referencePose.id}. Selected for planning: ${selected?.id||'none'}.`;
 if(panel.hidden)return;
 byId('reference-name').textContent=`Reference: ${referencePose.id}`;byId('comparison-name').textContent=`Selected: ${selected.id}`;
 const notesRow=text('tr','',byId('comparison-rows'));text('th','Your planning notes · not measured evidence',notesRow).scope='row';
 const notes=poseNotes();for(const candidate of [referencePose,selected]){const cell=text('td',notes[candidate.id]||'No note recorded.',notesRow);cell.dataset.comparisonNote=candidate.id;cell.style.whiteSpace='pre-wrap';cell.style.overflowWrap='anywhere';}
 const sliceKeys=['t_shell_thin_fraction','t_bridge_span_external_mm','t_bridge_span_internal_mm'];
 const differentKinds=sliceKeys.some(key=>{const a=comparisonSliceKind(referencePose.columns?.[key]),b=comparisonSliceKind(selected.columns?.[key]);return a&&b&&a!==b;});
 let sliceNote=byId('comparison-slice-context');
 if(!sliceNote){sliceNote=text('p','',panel);sliceNote.id='comparison-slice-context';panel.insertBefore(sliceNote,panel.querySelector('.table-wrap'));}
 sliceNote.hidden=!sliceKeys.some(key=>referencePose.columns?.[key]||selected.columns?.[key]);
 sliceNote.className=differentKinds?'warning':'hint';
 sliceNote.textContent=differentKinds?'Slice kinds differ in this comparison (helper project versus shell-only). These values are not a controlled orientation comparison: helper geometry and settings may also differ. Review each result’s source and method.':'Slice kinds are recorded below where available. Equal kinds alone do not establish matching geometry or slicer settings; compare each result’s source and method.';

 for(const [key,label,ceiling] of [['F_L_max','Layer failure · design corner'],['F_L_max_vendor_corner','Layer failure · vendor corner'],['ovh_fail_mm2','Overhang area'],['contact_mm2','Bed contact'],['height_mm','Print height'],['t_support_segments','Support segments · T'],['t_shell_thin_fraction','Thin shell fraction · T'],['t_bridge_span_external_mm','External bridge strand maximum · T'],['t_bridge_span_internal_mm','Internal bridge strand maximum · T'],['t_bridge_span_external_mm','External bridge ceiling maximum · T',true],['t_bridge_span_internal_mm','Internal bridge ceiling maximum · T',true]]){
   const row=text('tr','',byId('comparison-rows'));text('th',label,row).scope='row';
   for(const candidate of [referencePose,selected]){
     const column=candidate.columns?.[key],cell=text('td','',row);
     text('span',ceiling?(validBridgeColumn(column)&&Number.isFinite(column.ceiling_span_mm)&&column.ceiling_span_mm>=0?`${metricNumber(column.ceiling_span_mm)} mm · supplementary`:'Not recorded'):key==='t_shell_thin_fraction'?shellSummary(candidate):formatted(column),cell);
     if(sliceKeys.includes(key)){const kind=text('p','Slice kind: '+(comparisonSliceKind(column)||'not recorded'),cell);kind.className='hint';kind.dataset.sliceKind='';}
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
  return (Number.isFinite(c?.value)&&c.value>=0&&c.verdict!=='NOT_CHECKED')||!!shellColumn(candidate)||['t_bridge_span_external_mm','t_bridge_span_internal_mm'].some(key=>validBridgeColumn(candidate.columns?.[key]));
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
    const role={t_bridge_span_external_mm:'external',t_bridge_span_internal_mm:'internal'}[key];
    const road=role&&byId('pose-road-buttons').querySelector(`[data-road-id="${role}-strand"]`);
    if(road){
      const locate=text('button','Locate recorded strand',item);locate.type='button';locate.className='secondary';locate.dataset.locateFailedBridge=role;
      locate.onclick=()=>{byId('pose-road-options').open=true;road.click();road.scrollIntoView({block:'center'});road.focus({preventScroll:true});};
    }

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
  cancelSurfacePlacement();remember();selected=candidate;renderPoseRoads();renderPlanningPose();byId('pose-name').textContent=candidate.id;
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
  byId('toolpath-settings').textContent=slice?.fidelity||'No support-column slicer context supplied. Consult each available shell or bridge result for its own source and method.';
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
async function loadOrientationTable(file,request,bundle=null){
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
    if(!allowDraftReplacement('load another orientation table')){byId('status').textContent='Table replacement cancelled. The current table and draft are unchanged.';return false;}
    if(!bundle)byId('orientation-bundle-files').value='';
    clearOrientationBundle();clearKeepouts();fingerprint=nextFingerprint;sourceTableBytes=bytes;byId('download-table').disabled=false;byId('table-download-status').textContent='';analysis=data;viewer.setBed(data.bed);selected=null;referencePose=null;renderComparison();meshRequest++;mesh=null;meshHash=null;cancelSurfacePlacement();viewer.clear();byId('mesh-status').textContent='Load '+(data.mesh?.path?.split('/').pop()||'the matching STL')+' to preview the part.';decisions.clear();byId('workspace').hidden=false;
    byId('part-name').textContent=typeof data.problem==='string'?data.problem:(data.problem?.id||'Part orientation study');
    byId('evidence').textContent=[data.establishes,...(Array.isArray(data.does_not_establish)?data.does_not_establish.map(x=>'Not established: '+x):[data.does_not_establish])].filter(Boolean).map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' · ');
    byId('status').textContent=`Loaded ${data.candidates.length} candidate poses. Select one to inspect it.`;
    byId('pose-name').textContent='Choose a candidate';byId('direction').textContent='';byId('strength-range').textContent='';byId('reasons').replaceChildren();byId('failed-check-count').textContent='';byId('failed-checks').replaceChildren();byId('metrics').replaceChildren();byId('toolpath-metrics').replaceChildren();byId('toolpath-settings').textContent='';byId('credited-scope').textContent='';byId('pose-bridges').replaceChildren();byId('pose-shell-summary').textContent='';byId('pose-shell-fidelity').textContent='';byId('pose-shell-coverage').textContent='';byId('pose-shell-receipt').textContent='';byId('pose-shell-details').hidden=true;byId('rationale').value='';resetPlan();byId('export').disabled=true;byId('plan-pose').disabled=true;byId('export-status').textContent='';renderRows();resumeReviewDraft();
    if(bundle)renderOrientationBundle(bundle);
    return true;
  }catch(error){if(request!==tableRequest)return;byId('status').textContent=`Could not load table: ${error.message}${analysis?' The previous table and current draft remain available.':''}`;return false;}
}

byId('table-file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;const accepted=await loadOrientationTable(file,++tableRequest);if(accepted===false)event.target.value='';
};
function clearOrientationBundle(){
 orientationEvidenceBundle=null;renderPoseRoads();if(selected)renderFailedChecks(selected);
 byId('orientation-bundle-summary').hidden=true;byId('orientation-bundle-poses').replaceChildren();byId('orientation-bundle-manifest').textContent='';byId('orientation-bundle-status').textContent='No orientation bundle verified for this table.';
}
function renderOrientationBundle(bundle){
 orientationEvidenceBundle=bundle;renderPoseRoads();if(selected)renderFailedChecks(selected);
 const m=bundle.manifest,failures=m.receipts.filter(r=>r.verdict==='FAIL').length;
 byId('orientation-bundle-summary').hidden=false;
 byId('orientation-bundle-count').textContent=`${m.slices.length} pose slices; ${m.receipts.length} receipt fingerprints checked; ${failures} FAIL receipts. File verification does not qualify a pose.`;
 byId('orientation-bundle-scope').textContent=(m.establishes||'Recorded shell and bridge toolpath checks.')+' Not established: '+(m.does_not_establish||'physical qualification or a pose ranking.')+' The input G-code and part source files were not opened by this browser; their hashes are recorded provenance.';
 const rows=byId('orientation-bundle-poses');rows.replaceChildren();
 for(const slice of m.slices){
  const row=text('article','',rows);row.dataset.bundlePose=slice.pose;text('h3',slice.pose+' · '+slice.slice_kind,row);
  const button=text('button','Review '+slice.pose,row);button.type='button';button.className='secondary';
  button.onclick=()=>{choose(analysis.candidates.find(c=>c.id===slice.pose));byId('pose-name').focus({preventScroll:true});byId('pose-name').scrollIntoView({block:'start'});};
  text('p','Recorded G-code SHA-256: '+slice.gcode_sha256,row).className='hint';
  for(const item of bundle.receipts.filter(r=>r.entry.pose===slice.pose)){
   const details=text('details','',row);text('summary',item.receipt.result.rule+' · T · '+item.entry.verdict+' · '+item.entry.check,details);
   const profile=item.receipt.gcode?.print_settings_id;
   text('p','Recorded process profile: '+(typeof profile==='string'&&profile.trim()?profile:'Not recorded'),details).dataset.processProfile='';
   text('p','This is the receipt’s profile identifier, not confirmation that the production process is bound. Confirm the production profile in the owner-decision discussion.',details).className='hint';
   text('p','Receipt SHA-256: '+item.entry.sha256,details);text('pre',JSON.stringify(item.receipt,null,2),details);
  }
 }
 byId('orientation-bundle-manifest').textContent=JSON.stringify({manifest_sha256:bundle.manifestHash,...m},null,2);
 byId('orientation-bundle-status').textContent='Complete bundle verified. Loaded its exact enriched table; choose a pose to review the recorded results.';
}
byId('orientation-bundle-files').onchange=async event=>{
 const files=[...event.target.files];if(!files.length)return;const request=++tableRequest;
 try{
  const bundle=await OrientBundle.load(files);if(request!==tableRequest)return;
  const accepted=await loadOrientationTable({arrayBuffer:async()=>bundle.tableBytes},request,bundle);
  if(request===tableRequest&&!accepted){event.target.value='';byId('orientation-bundle-status').textContent=byId('status').textContent+' The previous bundle summary, if any, is retained.';}
 }catch(error){if(request!==tableRequest)return;byId('orientation-bundle-status').textContent='Could not open orientation bundle: '+error.message+' The current table, draft and previous bundle summary remain unchanged.';}
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
  const allInterfaces=text('button','Select all interfaces',refs);allInterfaces.type='button';allInterfaces.className='secondary helper-list-action';allInterfaces.dataset.selectInterfaces='';
  const coverage=text('p','',refs);coverage.className='hint';coverage.dataset.interfaceCoverage='';coverage.setAttribute('role','status');
  allInterfaces.onclick=()=>{const checks=[...box.querySelectorAll('[data-interface-id]')];for(const check of checks)check.checked=true;updateRegions();checks[0]?.focus({preventScroll:true});};
  for(const item of analysis?.interfaces||[]){const label=text('label','',refs),check=document.createElement('input');check.type='checkbox';check.dataset.interfaceId=item.id;check.checked=region.keep_clear?.interface_ids?.includes(item.id)||false;label.append(check,document.createTextNode(' '+item.id));
    const info=text('details','',refs);info.dataset.interfaceDetail=item.id;
    text('summary',item.id+' declaration',info);
    text('p',`Model: ${item.type||'not supplied'}. Axis: ${item.axis||'not supplied'}. Support: ${item.support||'not supplied'}. Frame: ${item.frame||'not declared in this interface'}.`,info);
    text('p','Recorded interface data, not a clearance check. Selecting this reference records planning intent; inspect KEEP-CLEAR results after export.',info).className='hint';
    const raw=text('pre',JSON.stringify(item,null,2),info);raw.style.whiteSpace='pre-wrap';raw.style.overflowWrap='anywhere';
  }
  const keepOutRefs=text('div','',box);keepOutRefs.className='interface-refs';
  text('p',analysis?.keep_outs?.length?'Keep-outs to track for this helper (global constraints still apply):':'This table has no keep-out declarations. Use a newer table to record keep-out references.',keepOutRefs);
  if(analysis?.keep_outs?.length)text('p','Keep-outs are drawn only when you load matching geometry and enable them under Optional: preview part keep-outs. Selecting a reference records intent; use the exporter’s KEEP-OUT results to inspect the modelled geometry check.',keepOutRefs).className='hint';
  for(const item of analysis?.keep_outs||[]){const label=text('label','',keepOutRefs),check=document.createElement('input');check.type='checkbox';check.dataset.keepOutId=item.id;check.checked=region.keep_clear?.keep_out_ids?.includes(item.id)||false;label.append(check,document.createTextNode(' '+item.id));const info=text('details','',keepOutRefs);text('summary',item.id+' constraint',info);text('p',item.rule||'No rule description supplied.',info);if(item.derivation)text('p',item.derivation,info);text('p',`Declared frame: ${item.frame||'unspecified'}. Model: ${item.type||'unspecified'}. Selection records intent; geometry checks run in the exporter.`,info);}
  const clearanceLabel=text('label','Extra clearance, mm (blank still checks with no extra gap)',box),clearance=document.createElement('input');clearance.type='number';clearance.min='0';clearance.step='0.1';clearance.dataset.clearance='';clearance.value=region.keep_clear?.clearance_mm??'';clearanceLabel.append(clearance);
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
  const volume=text('p','',spatial);volume.className='hint';volume.dataset.boxVolume='';
  const sizeFields=()=>[...box.querySelectorAll('[data-geometry="size_mm"]')];
  const sizeValues=()=>sizeFields().map(f=>f.value),sizeUndo=[],sizeRedo=[];
  let sizeBefore=sizeValues(),sizeEditing=false;
  const sizeActions=text('div','',spatial);sizeActions.className='nudge-controls';
  const undoSize=text('button','Undo dimension edit',sizeActions),redoSize=text('button','Redo dimension edit',sizeActions);
  for(const button of [undoSize,redoSize]){button.type='button';button.className='secondary';button.disabled=true;}
  const sizeStatus=text('p','Dimension undo keeps up to 20 edits per helper. Typing in one field is one edit; centre moves have separate history.',sizeActions);sizeStatus.setAttribute('role','status');
  const restoreSize=(from,to,button,reverse)=>{
    if(!from.length)return;const hadFocus=document.activeElement===button;
    cancelSurfacePlacement();to.push(sizeValues());const values=from.pop();
    sizeFields().forEach((f,i)=>f.value=values[i]);sizeBefore=sizeValues();sizeEditing=false;
    undoSize.disabled=!sizeUndo.length;redoSize.disabled=!sizeRedo.length;updateRegions();
    if(hadFocus&&button.disabled)reverse.focus({preventScroll:true});
    sizeStatus.textContent='Box dimensions restored. Centre and other helper settings are unchanged. Geometry checks have not been rerun.';
  };
  undoSize.onclick=()=>restoreSize(sizeUndo,sizeRedo,undoSize,redoSize);
  redoSize.onclick=()=>restoreSize(sizeRedo,sizeUndo,redoSize,undoSize);
  box.addEventListener('focusin',event=>{if(event.target.matches('[data-geometry="size_mm"]')){sizeBefore=sizeValues();sizeEditing=false;}});
  box.addEventListener('input',event=>{
    if(!event.target.matches('[data-geometry="size_mm"]'))return;
    if(!sizeEditing){sizeUndo.push(sizeBefore);if(sizeUndo.length>20)sizeUndo.shift();sizeEditing=true;}
    sizeRedo.length=0;undoSize.disabled=false;redoSize.disabled=true;
    sizeStatus.textContent='Dimensions edited. Undo dimension edit restores the values before this edit. Geometry checks have not been rerun.';
  });
  box.addEventListener('change',event=>{if(event.target.matches('[data-geometry="size_mm"]')){sizeBefore=sizeValues();sizeEditing=false;}});
  const nudge=text('div','',spatial);nudge.className='nudge-controls';
  const stepLabel=text('label','Move centre by',nudge),step=document.createElement('select');step.dataset.nudgeStep='';
  for(const value of [.1,.4,1,5]){const option=text('option',value+' mm',step);option.value=value;}step.value='1';stepLabel.append(step);
  const moves=text('div','',nudge);moves.className='nudge-buttons';
  const status=text('p','Moves use design axes, independent of the print pose. Undo and redo keep up to 20 moves per helper; typing a centre clears both histories. Clearance and bonding are not checked here.',nudge);status.setAttribute('role','status');status.dataset.nudgeStatus='';
  const centreMoves=[],redoMoves=[];
  const rememberCentreMove=before=>{centreMoves.push(before);if(centreMoves.length>20)centreMoves.shift();redoMoves.length=0;redo.disabled=true;undo.disabled=false;};
  const centres=()=>[...box.querySelectorAll('[data-geometry="center_mm"]')];
  const undo=text('button','Undo last centre move',nudge);undo.type='button';undo.className='secondary';undo.disabled=true;
  const redo=text('button','Redo centre move',nudge);redo.type='button';redo.className='secondary';redo.disabled=true;
  for(let axis=0;axis<3;axis++)for(const sign of [-1,1]){
    const move=text('button',`Move ${'XYZ'[axis]} ${sign<0?'−':'+'}`,moves);move.type='button';move.className='secondary';
    move.onclick=()=>{
      const fields=centres(),before=fields.map(f=>f.value);
      const invalid=before.findIndex(v=>v.trim()===''||!Number.isFinite(Number(v)));
      if(invalid!==-1){status.textContent='Complete all three centre coordinates before moving.';fields[invalid].focus();return;}
      const value=Number(before[axis])+sign*Number(step.value);
      if(!Number.isFinite(value)){status.textContent='Centre move is outside the numeric range.';return;}
      cancelSurfacePlacement();rememberCentreMove(before);fields[axis].value=Number(value.toFixed(6));undo.disabled=false;setActiveHelper(box);updateRegions();
      status.textContent=`Moved centre ${sign<0?'−':'+'}${step.value} mm along design ${'XYZ'[axis]}. Geometry checks have not been rerun.`;
    };
  }
  undo.onclick=()=>{if(!centreMoves.length)return;const hadFocus=document.activeElement===undo;cancelSurfacePlacement();redoMoves.push(centres().map(f=>f.value));redo.disabled=false;const before=centreMoves.pop();centres().forEach((f,i)=>f.value=before[i]);undo.disabled=!centreMoves.length;updateRegions();if(hadFocus&&undo.disabled)redo.focus({preventScroll:true});status.textContent=`Previous centre restored. ${centreMoves.length} earlier centre move(s) can still be undone. Geometry checks have not been rerun.`;};
  redo.onclick=()=>{if(!redoMoves.length)return;const hadFocus=document.activeElement===redo;cancelSurfacePlacement();centreMoves.push(centres().map(f=>f.value));const after=redoMoves.pop();centres().forEach((f,i)=>f.value=after[i]);redo.disabled=!redoMoves.length;undo.disabled=false;updateRegions();if(hadFocus&&redo.disabled)undo.focus({preventScroll:true});status.textContent=`Centre move restored. ${redoMoves.length} later centre move(s) can still be redone. Geometry checks have not been rerun.`;};
  box.addEventListener('input',event=>{if(event.target.matches('[data-geometry="center_mm"]')){cancelSurfacePlacement();centreMoves.length=0;redoMoves.length=0;undo.disabled=true;redo.disabled=true;}});
  const view=text('button','View this helper',spatial);view.type='button';view.className='secondary';view.dataset.viewHelper='';view.disabled=true;view.title='Load the matching mesh and enter a valid box to preview this helper.';
  view.onclick=()=>{cancelSurfacePlacement();setActiveHelper(box);viewer.focusRegion(box.dataset.id);document.querySelector('.preview').scrollTop=0;byId('part-view').scrollIntoView({block:'center'});byId('part-view').focus({preventScroll:true});};
  const place=text('button','Place centre on part',spatial);place.type='button';place.className='secondary';
  place.onclick=()=>{
    if(!mesh||!selected){byId('placement-status').textContent='Load a matching mesh and choose a pose first.';byId('part-view').scrollIntoView({block:'center'});return;}
    setActiveHelper(box);byId('return-helper').hidden=false;byId('cancel-placement').hidden=false;
    byId('placement-status').textContent='Click a surface to place the region centre. Orbit first if needed. Press Escape or Cancel placement to stop.';byId('part-view').style.cursor='crosshair';byId('part-view').scrollIntoView({block:'center'});
    viewer.onPick=point=>{if(!point){byId('placement-status').textContent='No surface at that point. Click the part.';return;}rememberCentreMove(centres().map(f=>f.value));for(let a=0;a<3;a++)box.querySelector(`[data-geometry="center_mm"][data-axis="${a}"]`).value=point[a].toFixed(3);cancelSurfacePlacement();byId('placement-status').textContent='Region centre placed on the surface; edit its size or move the centre inward as needed. Undo last centre move restores the previous coordinates.';updateRegions();};
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
  box.querySelector('[data-key="name"]').closest('label').after(toggleLabel,spatial);
  const editor=document.createElement('details');editor.className='helper-editor';editor.open=true;
  text('summary','Edit helper settings',editor);
  for(const child of [...box.children].slice(1))editor.append(child);
  box.append(editor);byId('helper-regions').append(box);updateRegions();return box;
}
function resetHandoff(){
 for(const id of ['handoff-command','evidence-command'])byId(id+'-selection').textContent='';
 byId('handoff-missing-boxes').replaceChildren();
 byId('handoff-command').textContent='fdmgen massing DRAFT.json --table TABLE.json --template PROFILE.3mf --out out/massing';
 byId('handoff-readiness').textContent='Export this draft to populate its filenames and geometry-input summary.';
 renderEvidenceHandoff(null);
}
const reviewContextPanel=byId('review-edit-context');
function clearReviewContext(){
 byId('planning-pose').before(reviewContextPanel);
 byId('review-edit-context').hidden=true;byId('review-edit-context-summary').textContent='';byId('review-edit-context-source').textContent='';
}
byId('dismiss-review-context').onclick=()=>{const field=reviewContextPanel.closest('.helper-region')?.querySelector('[data-key="name"]')||byId('walls');clearReviewContext();field.focus({preventScroll:true});field.scrollIntoView({block:'center'});};
function showReviewContext(context,helper){
 const check=context?.check;
 if(!helper||!check||check.metrics?.helper_id!==helper.dataset.id||!['FAIL','PASS','NOT_CHECKED'].includes(check.verdict)||typeof check.rule!=='string'||typeof check.level!=='string'||typeof check.message!=='string'||! /^[a-f0-9]{64}$/.test(context.report_sha256))return;
 byId('review-edit-context-summary').textContent=`${helper.querySelector('[data-key="name"]').value} [${helper.dataset.id}] · ${check.rule} · ${check.level} · ${check.verdict}: ${check.message}`;
 byId('review-edit-context-source').textContent=JSON.stringify(context,null,2);helper.querySelector('[data-key="name"]').closest('label').after(reviewContextPanel);reviewContextPanel.hidden=false;
}
function resetPlan(){
 byId('work-status').textContent='';
 clearReviewContext();
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
 renderPoseNotes();
 for(const button of byId('handoff-missing-boxes').children){
  button.disabled=byId('shell-only').checked||![...byId('helper-regions').children].some(box=>box.dataset.id===button.dataset.helperId);
 }

 const changed=draftCheckpoint!==null&&draftFormState()!==draftCheckpoint,unsavedNotes=unsavedPoseNoteIds();
 const label=byId('draft-edit-state');label.className=changed||unsavedNotes.length?'warning':'hint';
 label.textContent=draftCheckpointKind==='new'
  ?(changed?'Draft edited. Download it to keep these changes.':'No draft downloaded in this session.')
  :changed?`Changes since ${draftCheckpointKind==='snapshot'?'the work snapshot':draftCheckpointKind==='opened'?'reopening':'the last download'}. Export an updated draft before running checks.`
  :`No edits since ${draftCheckpointKind==='snapshot'?'the work snapshot (not an export-ready draft)':draftCheckpointKind==='opened'?'reopening this draft':'the last draft download'}.`;
 if(unsavedNotes.length)label.textContent+=` Notes for ${unsavedNotes.join(', ')} have unsaved changes. Download a work snapshot to keep all pose notes.`;
 const handoff=byId('handoff-snapshot');handoff.className=changed?'warning':'hint';
 handoff.textContent=draftCheckpointKind==='downloaded'
  ?changed?'The commands below describe the last downloaded draft. Current edits are not included; export an updated draft before running them.':'The commands below describe the last downloaded draft. Use the actual saved filenames on your worker.'
  :'No export from this draft is recorded in this session. Export it to populate the commands below, or substitute your saved file paths in the templates.';

}
function unsavedPoseNoteIds(){
 const notes=poseNotes();
 return [...new Set([...Object.keys(notes),...savedPoseNotes.keys()])].filter(id=>(notes[id]||'')!==(savedPoseNotes.get(id)||''));
}
function checkpointDraft(kind){
 draftCheckpointKind=kind;draftCheckpoint=draftFormState();
 if(kind==='new'||kind==='snapshot')savedPoseNotes.clear();
 if(kind==='snapshot')for(const [id,note] of Object.entries(poseNotes()))savedPoseNotes.set(id,note);
 else if(kind!=='new'&&selected)savedPoseNotes.set(selected.id,byId('rationale').value);
 updateDraftState();
}
function hasDraftEdits(){return draftCheckpoint!==null&&(draftFormState()!==draftCheckpoint||unsavedPoseNoteIds().length>0);}
function allowDraftReplacement(action){return !hasDraftEdits()||confirm(`Discard current draft edits and ${action}? Cancel to download your draft or save unfinished work first.`);}
window.addEventListener('beforeunload',event=>{if(hasDraftEdits()){event.preventDefault();event.returnValue='';}});
document.addEventListener('input',event=>{
 if(event.target.matches('#rationale,#walls,#skin,#shell-only,.helper-region input,.helper-region textarea'))updateDraftState();
});
function helperLabel(box){
 const boxes=[...byId('helper-regions').children],nameOf=b=>b.querySelector('[data-key="name"]').value.trim()||'Helper region',name=nameOf(box);
 return boxes.filter(b=>nameOf(b)===name).length>1?`${name} (helper ${boxes.indexOf(box)+1})`:name;
}
function invalidGeometryField(box){
 return [...box.querySelectorAll('[data-geometry]')].find(f=>f.value===''||!Number.isFinite(Number(f.value))||f.dataset.geometry==='size_mm'&&Number(f.value)<=0);
}
function updateInterfaceCoverage(box){
 const checks=[...box.querySelectorAll('[data-interface-id]')],count=checks.filter(f=>f.checked).length;
 box.querySelector('[data-select-interfaces]').disabled=!checks.length||count===checks.length;
 const status=box.querySelector('[data-interface-coverage]'),show=message=>{if(status.textContent!==message)status.textContent=message;};
 if(!checks.length){show('This table declares no interfaces to select. No KEEP-CLEAR checks can be requested here.');return;}
 if(!count){show(`0 of ${checks.length} interfaces selected. The exporter will produce no KEEP-CLEAR check for this helper. Select the interfaces it must keep clear.`);return;}
 const raw=box.querySelector('[data-clearance]').value,value=Number(raw);
 const clearance=raw===''?'Clearance is blank: the exporter still checks at 0 mm extra clearance. The helper must stay outside the modelled interface, with no extra gap. Enter a value to require a gap.':!Number.isFinite(value)||value<0?'Enter a finite, nonnegative clearance before exporting.':`Requested extra clearance: ${value} mm.`;
 show(`${count} of ${checks.length} interfaces selected for exporter KEEP-CLEAR checks. Unselected interfaces are not checked. ${clearance} Checks cover the modelled interface geometry; printed fit and assembly access remain separate.`);
}
function helperGeometrySummary(box){
 const prefix='Edit helper settings — ';
 if(!box.querySelector('[data-spatial]').checked)return prefix+'no box placed';
 if(invalidGeometryField(box))return prefix+'box incomplete: enter finite centres and positive sizes';
 const values=key=>[...box.querySelectorAll(`[data-geometry="${key}"]`)].map(f=>Number(f.value));
 return prefix+`${values('size_mm').join(' × ')} mm; centre (${values('center_mm').join(', ')}) design mm. Planning geometry only.`;
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
 for(const box of editors.values()){updateInterfaceCoverage(box);box.querySelector('.helper-editor > summary').textContent=helperGeometrySummary(box);}
 for(const box of editors.values())box.querySelector('[data-box-volume]').textContent=byId('shell-only').checked?'Helper omitted from this shell-only plan.':'Enter a valid box to show its unclipped volume.';
 if(!byId('shell-only').checked)for(const box of byId('helper-regions').children){const r=regionInput(box),z=box.querySelector('[data-print-z]');z.textContent='';if(!r.geometry)continue;
  try{Plan.geometry(r.geometry);
    const volume=r.geometry.size_mm.reduce((a,b)=>a*b,1);
    box.querySelector('[data-box-volume]').textContent=Number.isFinite(volume)&&volume>0
      ?`Unclipped box volume: ${volume>=1e9||volume<.001?volume.toExponential(3):volume.toLocaleString(undefined,{maximumSignificantDigits:6})} mm³. Not credited material or a print estimate; body clipping, overlaps and shell material are not deducted.`
      :'Box volume is outside the numeric display range.';
    r.active=box===activeHelper;r.previewName=helperLabel(box);valid.push(r);
    if(mesh&&meshBounds&&[0,1,2].some(k=>r.geometry.center_mm[k]+r.geometry.size_mm[k]/2<meshBounds.min[k]||r.geometry.center_mm[k]-r.geometry.size_mm[k]/2>meshBounds.max[k]))warn(`${r.name||'Region'}: box lies outside the part bounds and cannot bond to the body.`,[r.id]);
    if(r.geometry.size_mm.some(x=>x<.84))warn(`${r.name||'Region'}: an edge is below the 0.84 mm planning screen (2 × assumed 0.42 mm line width).`,[r.id],`[data-geometry="size_mm"][data-axis="${r.geometry.size_mm.findIndex(x=>x<.84)}"]`);
    if(selected){const corners=transformMesh(boxCorners(r.geometry),selected.R_design_to_print,selected.t_mm),zs=Array.from(corners).filter((_,i)=>i%3===2);z.textContent=`Print Z extent: ${Math.min(...zs).toFixed(3)}–${Math.max(...zs).toFixed(3)} mm. Layer snapping and body bonding remain unchecked.`;}
  }catch(e){
    const field=invalidGeometryField(box);
    warn(`${r.name||'Region'}: ${e.message}`,[r.id],field?`[data-geometry="${field.dataset.geometry}"][data-axis="${field.dataset.axis}"]`:'[data-geometry="center_mm"]');
  }
 }
 for(let i=0;i<valid.length;i++)for(let j=i+1;j<valid.length;j++){
  if(['center_mm','size_mm'].every(key=>valid[i].geometry[key].every((v,k)=>v===valid[j].geometry[key][k])))warn(`${valid[i].name||'Region'} / ${valid[j].name||'Region'}: identical planning boxes. Move, resize or remove the redundant copy as needed.`,[valid[i].id,valid[j].id]);
  if(Plan.boxSeparation(valid[i].geometry,valid[j].geometry).needs_review)warn(`${valid[i].name||'Region'} / ${valid[j].name||'Region'}: overlap or separation is below the nominal 0.84 mm screen. Review sliver modifiers.`,[valid[i].id,valid[j].id]);
 }
 for(const box of editors.values())box.querySelector('[data-view-helper]').disabled=!viewer.vertices||!valid.some(r=>r.id===box.dataset.id);
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
    const checked=Plan.restore(raw,analysis,fingerprint); // Reject before asking to discard edits.
    renderProposal(checked.input.proposal||null,document.createElement('section'));
    if(!allowDraftReplacement('open this saved draft')){byId('draft-status').textContent='Draft replacement cancelled. Current edits are unchanged.';event.target.value='';return;}
    restoreDraft(raw);
  }catch(error){if(openRequest!==draftRequest)return;byId('draft-status').textContent='Could not reopen draft: '+error.message;}
};
// Work snapshots preserve raw values; they deliberately do not use the backend draft schema.
function workFieldKey(field){
 if(field.dataset.key)return 'text:'+field.dataset.key;
 if(field.hasAttribute('data-interface-id'))return 'interface:'+field.dataset.interfaceId;
 if(field.hasAttribute('data-keep-out-id'))return 'keepout:'+field.dataset.keepOutId;
 if(field.hasAttribute('data-clearance'))return 'clearance';
 if(field.hasAttribute('data-spatial'))return 'spatial';
 return field.dataset.geometry+':'+field.dataset.axis;
}
function poseNotes(){
 const notes=new Map(decisions);if(selected)notes.set(selected.id,byId('rationale').value);
 return Object.fromEntries([...notes].filter(([,note])=>note!=='').sort(([a],[b])=>a.localeCompare(b)));
}
function renderPoseNotes(){
 const notes=poseNotes(),entries=Object.entries(notes),signature=JSON.stringify([selected?.id,notes]);
 for(const cell of document.querySelectorAll('[data-comparison-note]'))cell.textContent=notes[cell.dataset.comparisonNote]||'No note recorded.';
 if(signature===renderedPoseNotes)return;renderedPoseNotes=signature;
 byId('pose-notes-title').textContent=`Your pose notes (${entries.length})`;
 const list=byId('pose-notes-list');list.replaceChildren();
 if(!entries.length){text('p','No notes yet. Record why you would choose or reject a pose in the rationale field.',list);return;}
 for(const [id,note] of entries){
  const item=text('section','',list),button=text('button','Edit note for '+id,item);button.type='button';button.className='secondary';
  if(id===selected?.id)text('span',' Selected for planning',item).className='hint';
  const body=text('p',note,item);body.style.whiteSpace='pre-wrap';body.style.overflowWrap='anywhere';
  button.onclick=()=>{const candidate=analysis?.candidates.find(c=>c.id===id);if(!candidate)return;choose(candidate);byId('rationale').focus({preventScroll:true});byId('rationale').scrollIntoView({block:'center'});};
 }
}
function workSnapshot(){
 if(!analysis||!selected||!fingerprint)throw Error('Open an orientation table and choose a pose first.');
 return {schema:'fdmgen.work-snapshot.v0.1',orientation_table_sha256:fingerprint,pose:selected.id,
  walls:byId('walls').value,skin:byId('skin').value,rationale:byId('rationale').value,shell_only:byId('shell-only').checked,
  proposal:proposalOrigin,pose_notes:poseNotes(),
  helpers:[...byId('helper-regions').children].map(box=>({id:box.dataset.id,fields:Object.fromEntries(
   [...box.querySelectorAll('input,textarea')].map(f=>[workFieldKey(f),f.type==='checkbox'?f.checked:f.value]))}))};
}
function validateWorkSnapshot(raw){
 const fail=message=>{throw Error(message);};
 if(raw?.schema!=='fdmgen.work-snapshot.v0.1')fail('Unsupported work snapshot format.');
 if(!analysis||raw.orientation_table_sha256!==fingerprint)fail('Open the exact orientation table used by this snapshot first.');
 const candidate=analysis.candidates.find(c=>c.id===raw.pose);if(!candidate)fail('Snapshot pose is absent from this table.');
 const numeric=value=>{if(typeof value!=='string')return false;const field=document.createElement('input');field.type='number';field.value=value;return field.value===value&&(value===''||Number.isFinite(Number(value)));};
 if(!numeric(raw.walls)||!numeric(raw.skin)||typeof raw.rationale!=='string'||typeof raw.shell_only!=='boolean')fail('Invalid snapshot shell inputs or notes.');
 if(Object.hasOwn(raw,'pose_notes')){
  const notes=raw.pose_notes;
  if(!notes||typeof notes!=='object'||Array.isArray(notes)||Object.entries(notes).some(([id,note])=>typeof note!=='string'||!analysis.candidates.some(c=>c.id===id))||(notes[raw.pose]??'')!==raw.rationale)fail('Snapshot pose notes are invalid or disagree with the selected rationale.');
 }
 if(raw.proposal!==null&&(!raw.proposal||typeof raw.proposal!=='object'||Array.isArray(raw.proposal)||typeof raw.proposal.generator!=='string'||!raw.proposal.generator.trim()))fail('Invalid proposal metadata.');
 if(!Array.isArray(raw.helpers)||raw.helpers.length>1000)fail('Invalid snapshot helper list (maximum 1000).');
 const texts=['name','location','purpose','keep_clear'].map(k=>'text:'+k);
 const numbers=['clearance',...['center_mm','size_mm'].flatMap(k=>[0,1,2].map(a=>k+':'+a))];
 const checks=['spatial',...(analysis.interfaces||[]).map(x=>'interface:'+x.id),...(analysis.keep_outs||[]).map(x=>'keepout:'+x.id)];
 const keys=[...texts,...numbers,...checks],ids=new Set();
 for(const h of raw.helpers){
  if(!h||typeof h.id!=='string'||!h.id||ids.has(h.id))fail('Snapshot helper identifiers must be nonempty and unique.');ids.add(h.id);
  const f=h.fields;if(!f||typeof f!=='object'||Array.isArray(f)||Object.keys(f).length!==keys.length||keys.some(k=>!Object.hasOwn(f,k)))fail('Snapshot helper fields do not match this table.');
  if(texts.some(k=>typeof f[k]!=='string')||numbers.some(k=>!numeric(f[k]))||checks.some(k=>typeof f[k]!=='boolean'))fail('Invalid snapshot helper values.');
 }
 renderProposal(raw.proposal,document.createElement('section'));
 return candidate;
}
byId('save-work').onclick=()=>{
 try{const raw=workSnapshot();validateWorkSnapshot(raw);downloadFile(JSON.stringify(raw,null,2)+'\n','unfinished-work.json');
  resetHandoff();checkpointDraft('snapshot');byId('work-status').textContent='Work snapshot downloaded. Keep it with the exact source table. Complete the form and export a planning draft before running the exporter.';
 }catch(error){byId('work-status').textContent='Could not save work: '+error.message;}
};
byId('work-file').onchange=async event=>{
 const file=event.target.files[0];if(!file)return;const request=tableRequest,openRequest=++draftRequest;
 try{
  const raw=JSON.parse(await file.text());if(openRequest!==draftRequest)return;
  if(request!==tableRequest)throw Error('The analysis changed while opening the snapshot. Open it again.');
  const candidate=validateWorkSnapshot(raw);
  if(!allowDraftReplacement('reopen this work snapshot')){byId('work-status').textContent='Snapshot replacement cancelled. Current edits are unchanged.';return;}
  clearRemovalHistory();clearDraftError();clearReviewContext();cancelSurfacePlacement();
  proposalOrigin=raw.proposal;renderProposal();choose(candidate);
  decisions.clear();for(const [id,note] of Object.entries(raw.pose_notes||{}))decisions.set(id,note);
  byId('walls').value=raw.walls;byId('skin').value=raw.skin;byId('rationale').value=raw.rationale;decisions.set(candidate.id,raw.rationale);
  byId('shell-only').checked=raw.shell_only;byId('helper-panel').hidden=raw.shell_only;byId('helper-regions').replaceChildren();
  for(const helper of raw.helpers){const box=addHelper({id:helper.id,geometry:{center_mm:[0,1,2].map(a=>helper.fields['center_mm:'+a]),size_mm:[0,1,2].map(a=>helper.fields['size_mm:'+a])}});
   for(const f of box.querySelectorAll('input,textarea')){const value=helper.fields[workFieldKey(f)];if(f.type==='checkbox')f.checked=value;else f.value=value;}
   box.querySelector('legend').textContent=helper.fields['text:name'].trim()||'Helper region';box.querySelector('.spatial').hidden=!helper.fields.spatial;
  }
  resetHandoff();byId('draft-status').textContent='';byId('export-status').textContent='';updateRegions();checkpointDraft('snapshot');
  byId('work-status').textContent='Unfinished work restored. '+(Object.hasOwn(raw,'pose_notes')?'Comparison notes restored for all recorded poses. ':'Legacy snapshot: only the selected pose rationale was saved. ')+ 'Required fields may still be incomplete; export a planning draft to validate them. No checks were rerun.';
 }catch(error){if(openRequest===draftRequest)byId('work-status').textContent='Could not reopen work: '+error.message;}
 finally{event.target.value='';}
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
  if(box.querySelector('[data-spatial]').checked){const field=invalidGeometryField(box);if(field)return field;}
 }
 return null;
}
function clearDraftError(){
 byId('draft-field-error')?.remove();
 for(const f of document.querySelectorAll('[data-export-error]')){f.removeAttribute('aria-invalid');f.removeAttribute('aria-errormessage');delete f.dataset.exportError;}
}
document.addEventListener('input',event=>{if(event.target.hasAttribute('data-export-error'))clearDraftError();});
for(const id of ['handoff-command','evidence-command']){
 byId('select-'+id).onclick=()=>{
  const command=byId(id);command.focus({preventScroll:true});
  const range=document.createRange();range.selectNodeContents(command);
  const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
  byId(id+'-selection').textContent='Command selected. Use your system Copy action (Ctrl+C or ⌘C), then replace placeholder paths on the worker. Nothing has been run.';
 };
}
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
    for(const id of ['handoff-command','evidence-command'])byId(id+'-selection').textContent='';
    remember();const draft=Plan.create(analysis,fingerprint,selected,planInput());
    downloadFile(JSON.stringify(draft,null,2)+'\n',Plan.filename(draft));checkpointDraft('downloaded');
    byId('handoff-command').textContent=`fdmgen massing ${Plan.filename(draft)} --table ${sourceTableFilename()} --template PROFILE.3mf --out out/massing`;
    renderEvidenceHandoff(draft);
    byId('export-status').textContent='Draft exported. It includes the source fingerprint and outstanding verification steps.';
    const incomplete=draft.massing.helper_regions.filter(h=>!h.geometry);
    byId('handoff-readiness').textContent=incomplete.length?`Last exported draft: ${incomplete.length} helper(s) without a box: ${incomplete.map(h=>h.name).join(', ')}. Enable their spatial controls and set centre/size, then save again before running the exporter.`:'Last exported draft: geometry inputs needed for export are present. The command still checks source fingerprints and helper geometry.';
    byId('handoff-missing-boxes').replaceChildren();
    for(const helper of incomplete){
      const box=[...byId('helper-regions').children].find(box=>box.dataset.id===helper.id);
      if(!box)continue;
      const button=text('button',`Edit box for ${helperLabel(box)}`,byId('handoff-missing-boxes'));button.type='button';button.className='secondary';button.dataset.helperId=helper.id;
      button.onclick=()=>{if(!box.isConnected||byId('shell-only').checked)return;setActiveHelper(box);const field=box.querySelector('[data-spatial]');field.focus({preventScroll:true});field.scrollIntoView({block:'center'});};
    }
    byId('handoff').open=true;
  }catch(error){
    byId('export-status').textContent=error.message;
    const field=invalidDraftField();
    if(field){
      const helper=field.closest('.helper-region');if(helper)setActiveHelper(helper);
      const explanation=document.createElement('p');explanation.id='draft-field-error';explanation.className='warning';explanation.textContent=error.message;explanation.setAttribute('role','alert');
      (field.closest('.geometry-group')||field.closest('label')||field).after(explanation);
      if(field.matches('input,textarea')){field.dataset.exportError='';field.setAttribute('aria-invalid','true');field.setAttribute('aria-errormessage',explanation.id);}
      field.focus({preventScroll:true});field.scrollIntoView({block:'center'});
    }
  }
};

function restoreDraft(raw){
    const restored=Plan.restore(raw,analysis,fingerprint),input=restored.input;
    renderProposal(input.proposal||null,document.createElement('section'));
    byId('work-status').textContent='';
    clearRemovalHistory();
    clearDraftError();clearReviewContext();
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
  showReviewContext(pendingReview.review_context,target);
  clearReviewTransfer();
  const field=target?target.querySelector('[data-key="name"]'):byId('walls');
  if(target)setActiveHelper(target);
  field.focus({preventScroll:true});field.scrollIntoView({block:'center'});
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
 const planningSelect=byId('planning-helper');planningSelect.replaceChildren(...[...select.options].map(option=>option.cloneNode(true)));planningSelect.disabled=select.disabled;planningSelect.value=select.value;
 byId('collapse-other-helpers').disabled=shellOnly||!boxes.length;
 byId('collapse-other-helpers').textContent=activeHelper?'Show only selected helper':'Collapse all helpers';
 byId('expand-helpers').disabled=shellOnly||!boxes.length;
 byId('active-helper-status').textContent=shellOnly?'Shell-only draft: helper boxes are excluded.':activeHelper?`Editing ${helperLabel(activeHelper)}. ${activeHelper.querySelector('[data-spatial]').checked?'Its box has the solid blue outline; other boxes are dashed orange.':'Enable its spatial box to preview the region.'}`:'Focus a helper field to highlight its box.';
}
byId('collapse-other-helpers').onclick=()=>{for(const box of byId('helper-regions').children)box.querySelector('.helper-editor').open=box===activeHelper;};
byId('expand-helpers').onclick=()=>{for(const editor of document.querySelectorAll('.helper-editor'))editor.open=true;};
for(const selector of ['preview-helper','planning-helper'])byId(selector).onchange=()=>{
 const box=[...byId('helper-regions').children].find(b=>b.dataset.id===byId(selector).value);
 setActiveHelper(box||null);
 if(box){box.scrollIntoView({block:'center'});box.querySelector('[data-key="name"]').focus({preventScroll:true});}
};

function renderProposal(proposal=proposalOrigin,panel=byId('proposal-evidence')){
 panel.replaceChildren();panel.hidden=!proposal;
 if(!proposal)return;
 const p=proposal;
 if(p.status==='no_viable_helpers')text('p','No viable helpers were proposed. The empty helper list does not establish that shell-only is sufficient. Review the rejected clusters and revise the plan deliberately.',panel).className='warning';
 const history=text('details','',panel);history.dataset.proposalHistory='';
 text('summary','Original machine proposal — historical, not current verification',history);panel=history;
 text('p','Historical proposal provenance. Editing helpers, shell settings or the pose does not rerun the seed or its checks. Export and verify the current plan again.',panel).className='warning';
 text('p',p.label||'A proposal for review; not an optimum or a strength result.',panel);
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
