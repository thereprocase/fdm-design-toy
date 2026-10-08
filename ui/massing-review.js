'use strict';
const el=id=>document.getElementById(id);
let bundleGeneration=0,matchedReportHash=null;
let saved=null,digest=null,generation=0,receiptGeneration=0,matchedReport=null,sliceGeneration=0,matchedSlice=null,mechanicsGeneration=0,shellGeneration=0,shellBaselineGeneration=0,matchedShell=null,matchedShellBaseline=null;
function add(tag,value,parent){const n=document.createElement(tag);n.textContent=value;parent.append(n);return n;}
el('review-draft').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;const request=++generation;++receiptGeneration;
 // Clear old results immediately, so they cannot be mistaken for this revision.
 clearSlice();matchedReportHash=null;el('review-bundle').disabled=true;matchedReport=null;saved=null;digest=null;el('review-workspace').hidden=true;el('review-receipt').disabled=true;el('review-receipt').value='';
 try{const raw=await file.arrayBuffer(),d=MassingReview.draft(JSON.parse(new TextDecoder().decode(raw))),h=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),b=>b.toString(16).padStart(2,'0')).join('');if(request!==generation)return;saved=d;digest=h;el('review-receipt').disabled=false;el('review-status').textContent='Draft loaded. Open its matching export receipt.';}catch(err){if(request===generation)el('review-status').textContent=err.message;}
};
el('review-receipt').onchange=async e=>{
 const file=e.target.files[0];if(!file||!saved)return;const request=++receiptGeneration,current=generation;
 try{const raw=await file.arrayBuffer(),reportHash=await EvidenceBundle.digest(raw),r=MassingReview.pair(saved,digest,JSON.parse(new TextDecoder().decode(raw)));if(current!==generation||request!==receiptGeneration)return;render(r,reportHash);matchedReportHash=reportHash;el('review-status').textContent='Receipt fingerprint matched this saved draft.';}catch(err){if(current===generation&&request===receiptGeneration)el('review-status').textContent=err.message+' Previous matched results, if any, remain below.';}
};
function helperName(id){
 const helpers=saved.massing.helper_regions,h=helpers.find(h=>h.id===id);
 return helpers.filter(other=>other.name.trim()===h.name.trim()).length>1?`${h.name} [${h.id}]`:h.name;
}
function render(r,reportHash){
 clearSlice();matchedReport=r;el('review-bundle').disabled=false;el('review-slice').disabled=false;
 el('review-workspace').hidden=false;el('review-title').textContent=`${r.plan.problem} · ${r.plan.candidate_id}`;
 const hashes=el('review-input-hashes');hashes.replaceChildren();
 for(const [label,value] of [['Saved draft — calculated',digest],['Export report — calculated',reportHash],['Orientation table — recorded',r.plan.table_sha256],['Template 3MF — recorded',r.template_3mf_sha256],['Project 3MF — recorded',r.project_3mf_sha256]]){add('dt',label,hashes);add('code',value,add('dd','',hashes));}
 el('review-context').textContent=r.capability_context_matches_template?'Template fingerprint matches the capability context. This does not validate every changed value or combination.':'Template differs from the measured capability context. Helper settings are unverified for this profile.';
 if(r.warning)el('review-context').textContent+=' '+r.warning;
 el('review-scope').textContent=`${r.establishes||''} Does not establish: ${r.does_not_establish||'printed performance or strength.'}`;
 const failed=r.checks.filter(c=>c.verdict==='FAIL').length,unchecked=r.checks.filter(c=>c.verdict==='NOT_CHECKED').length;
 el('review-count').textContent=r.checks.length?`${failed} failed checks; ${unchecked} not checked. Passing checks apply only to the stated method and evidence level.`:'No helper checks reported; this is not a checked result.';
 el('check-filter').value='attention';renderChecks();
 el('review-helpers').replaceChildren();
 for(const h of r.helpers){const planned=saved.massing.helper_regions.find(p=>p.id===h.id),row=add('article','',el('review-helpers'));add('h3',helperName(h.id),row);editButton(h.id,helperName(h.id),row);add('p',`Helper ID: ${h.id}`,row);add('p',planned.purpose||'',row);const details=add('details','',row);add('summary','Design box, print bounds and exported settings',details);add('pre',JSON.stringify({design_box:planned.geometry,exported_settings:h.settings,print_bbox_mm:h.print_bbox_mm},null,2),details);}
 if(!r.helpers.length)add('p','Shell-only draft; no helpers.',el('review-helpers'));
 el('review-setting-evidence').textContent=r.settings_evidence?JSON.stringify(r.settings_evidence,null,2):'Per-value setting evidence was not recorded in this receipt.';
 el('review-settings').textContent=JSON.stringify(r.object_settings,null,2);el('review-skin').textContent=r.skin_note||'';el('review-provenance').textContent=JSON.stringify(r,null,2);
}

el('check-filter').onchange=()=>renderChecks();
function renderChecks(){
 if(!matchedReport)return;
 const checks=matchedReport.checks,filter=el('check-filter').value;
 const visible=checks.filter(c=>filter==='all'||(filter==='attention'?c.verdict!=='PASS':c.verdict===filter));
 const passed=checks.filter(c=>c.verdict==='PASS').length;
 el('check-filter-status').textContent=`Showing ${visible.length} of ${checks.length} recorded export checks.`+(filter==='attention'?` ${passed} passed checks are available under All checks or Passed checks.`:'')+(!visible.length?' No checks in this view. This does not qualify the part.':'');
 el('review-checks').replaceChildren();
 const names=new Map(saved.massing.helper_regions.map(h=>[h.id,h.name]));
 for(const c of visible){const row=add('article','',el('review-checks'));add('h3',`${c.rule} · ${c.level} · ${c.verdict}${c.provisional?' · provisional':''}`,row);let message=c.message;for(const [id,name]of names)message=message.split(id).join(`${name} [${id}]`);add('p',message,row);if(names.has(c.metrics?.helper_id))editButton(c.metrics.helper_id,names.get(c.metrics.helper_id),row);const fixes=add('ul','',row);for(const fix of c.fixes)add('li',fix,fixes);if(c.establishes)add('p',c.establishes,row);if(c.does_not_establish)add('p','Does not establish: '+c.does_not_establish,row);const details=add('details','',row);add('summary','Measurements',details);add('pre',JSON.stringify(c.metrics||{},null,2),details);}
}

function clearSlice(){clearBundle();clearShell();clearMechanics();matchedSlice=null;++sliceGeneration;el('review-slice').value='';el('review-slice').disabled=true;showReviewSection('slice-results',!(true));el('slice-status').textContent='No slice evidence loaded.';}
el('review-slice').onchange=async e=>{
 const file=e.target.files[0];if(!file||!matchedReport)return;const request=++sliceGeneration,report=matchedReport;
 try{const receipt=MassingReview.slice(report,JSON.parse(await file.text()));if(request!==sliceGeneration||report!==matchedReport)return;renderSlice(receipt);el('slice-status').textContent='Slice receipt matches the exported project and saved plan.';}
 catch(error){if(request===sliceGeneration)el('slice-status').textContent=error.message+' Previous matched slice results, if any, remain below.';}
};
function renderSlice(r){
 clearBundle();clearShell();clearMechanics();matchedSlice=r;el('review-shell').disabled=false;el('review-shell-baseline').disabled=r.baseline!=='shell-only slice';el('review-mechanics').disabled=false;
 const baseline=r.baseline!==null,mismatch=MassingReview.contextMismatch(r),number=x=>x.toLocaleString(undefined,{maximumFractionDigits:3});
 showReviewSection('slice-results',!(false));
 el('slice-baseline').textContent=baseline?'Compared with a shell-only slice. Differences describe solid infill in each helper box; overlapping boxes may count the same roads.':'No shell-only baseline supplied. Absolute fill includes existing body material; helper contribution is not established.';
 if(mismatch.length)el('slice-baseline').textContent='Baseline settings differ: '+mismatch.join(', ')+'. Reported differences cannot be attributed to helpers alone; re-slice with matching settings.';
 el('slice-settings').textContent=JSON.stringify({project:r.slicer||'Not recorded',baseline:r.baseline_slicer||'Not recorded'},null,2);
 el('slice-thresholds').textContent=`Producer thresholds: ${number(r.min_fill_fraction*100)}% of box volume and ${number(r.min_added_mm3)} mm³. These are slicer screening thresholds, not strength limits.`;
 el('slice-scope').textContent=(baseline&&!mismatch.length?(r.establishes||''):'Helper contribution is not established by this comparison.')+' Does not establish: '+(r.does_not_establish||'shell bonding or strength.');
 el('slice-helpers').replaceChildren();
 for(const h of r.helpers){const name=helperName(h.id),row=add('article','',el('slice-helpers'));add('h3',`${name} · T ${h.verdict}${!baseline?' (absolute-fill screen)':mismatch.length?' (context mismatch)':''}`,row);editButton(h.id,name,row);
  const values=add('dl','',row);
  for(const [label,value] of [['Project solid infill in box',number(h.solid_infill_in_box_mm3)+' mm³'],['Shell-only solid infill in box',baseline?number(h.baseline_solid_infill_mm3)+' mm³':'Not checked'],[mismatch.length?'Uncontrolled solid-infill difference':'Added solid infill',baseline?number(h.added_solid_mm3)+' mm³':'Not attributable without baseline'],['Added fill / box volume',baseline?number(h.added_fill_fraction*100)+'%':'Not attributable without baseline']]){add('dt',label,values);add('dd',value,values);}
  if(baseline&&!mismatch.length)add('p',h.message.replace(h.id,name),row);
 }
 el('slice-credit').textContent=`Whole-slice credited material: ${number(r.credited_mm3)} mm³. This is not a sum of helper contributions or a strength result.`;
 el('slice-source-note').textContent='Project/plan pairing checked; G-code contents and matching baseline settings are not verified by this page. Inspect recorded provenance below; older receipts may omit G-code fingerprints and slicer settings.';
 el('slice-provenance').textContent=JSON.stringify(r,null,2);
}

function editButton(helperId,name,parent){
 name=helperName(helperId);
 const button=add('button',`Edit ${name}`,parent);button.type='button';button.className='secondary';
 button.onclick=()=>transferDraft(helperId,name);
}
el('revise-draft').onclick=()=>transferDraft(null,'the shell and helper plan');
function transferDraft(helperId,name){
 if(!saved||!matchedReport)return;
  try{sessionStorage.setItem('fdmgen-review-edit',JSON.stringify({draft:saved,helper_id:helperId}));location.href='index.html#review-edit';}
  catch(error){el('review-status').textContent='This browser cannot transfer the draft between pages. Return to the workspace, load its original table, and reopen the saved draft to edit '+name+'.';}
}

function clearMechanics(){
 ++mechanicsGeneration;el('review-mechanics').value='';el('review-mechanics').disabled=true;
 showReviewSection('mechanics-results',!(true));el('mechanics-status').textContent='Load paired slice evidence before mechanics.';
}
el('review-mechanics').onchange=async e=>{
 const file=e.target.files[0];if(!file||!matchedReport||!matchedSlice)return;
 const request=++mechanicsGeneration,report=matchedReport,slice=matchedSlice;
 try{
  const r=MassingReview.mechanics(report,slice,JSON.parse(await file.text()));
  if(request!==mechanicsGeneration||report!==matchedReport||slice!==matchedSlice)return;
  renderMechanics(r);el('mechanics-status').textContent='Mechanics receipt matches this project and both recorded G-code hashes.';
 }catch(error){if(request===mechanicsGeneration)el('mechanics-status').textContent=error.message+' Previous matched mechanics results, if any, remain below.';}
};
function renderMechanics(r){
 const source=r,weighted=r.schema==='fdmgen/density-weighted-mechanics-pilot@0.1';
 const reasons=MassingReview.mechanicsReasons(r),comparable=reasons.length===0,num=x=>x.toLocaleString(undefined,{maximumFractionDigits:3});
 // Presentation mapping only: keep the original weighted receipt intact below.
 if(weighted)r={...r,inputs:r.cases,audits:Object.fromEntries(Object.entries(r.cases).map(([k,c])=>[k,c.audit])),solves:Object.fromEntries(Object.entries(r.cases).map(([k,c])=>[k,c.solve])),fragment_removal:Object.fromEntries(Object.entries(r.cases).map(([k,c])=>[k,{...c.fragment_removal,removed_volume_mm3:c.fragment_removal.removed_grid_volume_mm3}]))};

 showReviewSection('mechanics-results',!(false));
 el('mechanics-policy').textContent=weighted?`FE pilot · provisional. Density-weighted stiffness, no binary threshold. Domain policy: ${r.domain_policy}. The full-body context may remove fragments; see each audit. This is not equivalent to the thresholded load-transfer pilot.`:`FE pilot · provisional. Domain policy: ${r.domain_policy}; density threshold ${r.threshold}. ${r.domain_policy==='largest-face-component sensitivity'?'Fragments were explicitly removed. This is not the unmodified raster result.':'Original thresholded domains; inspect connectivity failures below.'}`;
 el('mechanics-comparison').textContent=comparable?`Project compliance change versus shell-only: ${num(100*(r.solves.project.compliance_N_mm/r.solves.baseline.compliance_N_mm-1))}%. Applies only to this domain and load policy; not a strength rating.`:`No supported compliance comparison: ${reasons[0]}`;
 if(weighted)el('mechanics-comparison').textContent+=' This density-law sensitivity does not establish equivalence to the thresholded and load-transferred pilot.';
 el('mechanics-model').textContent=weighted?`Load policy: ${r.load_policy}. Load SHA-256: ${r.load_sha256}. Material: E0 ${num(r.material.E0_MPa)} MPa, nu ${num(r.material.nu)}; ${r.material.law}, power ${num(r.material.power)}, stiffness floor ${r.material.stiffness_floor}. ${r.material.evidence}. This law is uncalibrated; linear model outputs do not establish physical movement.`:`Load method: ${r.method}. ${r.context_note||''} Material constants are not recorded in this pilot receipt; consult its reproducible benchmark. Linear model outputs do not establish physical movement.`;
 const grid=r.inputs.baseline.provenance.grid;
 el('mechanics-resolution').textContent=`Solver cell size: ${grid.h_mm.map(num).join(' × ')} mm; grid ${grid.shape.join(' × ')} cells. Bead sampling refines deposition inside this grid, not the FE mesh.`;
 el('mechanics-sampling').textContent=[['baseline','Shell-only'],['project','Project']].map(([key,label])=>{
  const sampling=r.inputs[key].provenance.sampling;
  const step=sampling?.step_mm;
  return `${label} bead sampling step: ${typeof step==='number'&&Number.isFinite(step)&&step>0?num(step)+' mm':'not recorded'}.`;
 }).join(' ');
 el('mechanics-sampling').textContent+=' '+[['baseline','Shell-only'],['project','Project']].map(([key,label])=>{
  const caps=r.inputs[key].provenance.sampling?.caps;
  return `${label} road-end/turn caps: ${caps===true?'enabled':caps===false?'disabled':'not recorded'}.`;
 }).join(' ')+' Raster-model changes can alter thresholded domains and transferred loads; equal sampling steps do not establish equivalent mechanics.';
 el('mechanics-sampling').textContent+=' '+[['baseline','Shell-only'],['project','Project']].map(([key,label])=>{const sampling=r.inputs[key].provenance.sampling;return `${label} sampling fraction: ${sampling?.step_frac??'not recorded'}; original recorded fraction: ${sampling?.recorded_step_frac??'not recorded'}. ${sampling?.purpose||''}`;}).join(' ');
 el('mechanics-sampling-provenance').textContent=JSON.stringify(Object.fromEntries(['baseline','project'].map(key=>[key,r.inputs[key].provenance.sampling??'Not recorded'])),null,2);
 el('mechanics-rows').replaceChildren();el('mechanics-audits').replaceChildren();
 if(reasons.length){const blocked=add('article','',el('mechanics-audits'));blocked.dataset.mechanicsReasons='';add('h3','Why this comparison is withheld',blocked);const list=add('ul','',blocked);for(const reason of reasons)add('li',reason,list);}
 for(const [name,label] of [['full_solid','Full-body context'],['baseline','Shell-only'],['project','Seeded project']]){
  const a=r.audits[name],s=r.solves?.[name],row=add('tr','',el('mechanics-rows'));
  const valid=MassingReview.mechanicsCaseReasons(source,name).length===0;
  for(const value of [label,`${a.status} / ${s?.status||'not solved'}${valid?'':'; checks not established'}`,valid?num(s.compliance_N_mm):'Not established',valid?num(s.max_displacement_mm):'Not established'])add('td',value,row);
  const detail=add('article','',el('mechanics-audits'));add('h3',label,detail);
  add('p',`${a.cells} cells; ${a.face_components} face-connected components; ${a.missing_loaded_dofs} missing loaded DOFs.`,detail);
  for(const reason of a.reasons)add('p',String(reason),detail);
  if(weighted){const c=source.cases[name];add('p',`Raw domain: ${c.raw_audit.status}; ${c.raw_audit.face_components} face components. ${c.raw_audit.reasons.join('; ')} Cells outside full-body envelope: ${c.cells_outside_full_body}. Minimum positive stiffness fraction: ${c.positive_stiffness_fraction_min.toExponential(3)}.`,detail);}
  const f=r.fragment_removal?.[name];if(f)add('p',`Removed ${f.removed_cells} cells (${num(f.removed_volume_mm3)} mm³ of grid-cell volume); ${f.removed_fixed_dofs} fixed DOFs and ${num(f.removed_original_load_l1_N)} N summed absolute original nodal force lost exclusively with removed nodes.`,detail);
  if(s?.status==='solved')add('p',`True relative residual: ${s.true_relative_residual.toExponential(3)}.`,detail);
 }
 el('mechanics-scope').textContent=`${r.establishes||''} Does not establish: ${(r.does_not_establish||[]).join('; ')}.`;
 el('mechanics-provenance').textContent=JSON.stringify(source,null,2);
}

function clearShell(){
 ++shellBaselineGeneration;matchedShell=null;matchedShellBaseline=null;el('review-shell-baseline').value='';el('review-shell-baseline').disabled=true;showReviewSection('shell-comparison',!(true));el('shell-baseline-status').textContent='No baseline shell check loaded.';
 ++shellGeneration;el('review-shell').value='';el('review-shell').disabled=true;showReviewSection('shell-results',!(true));
 el('shell-status').textContent='Load the project slice evidence before its shell check.';
}
el('review-shell').onchange=async e=>{
 const file=e.target.files[0];if(!file||!matchedReport||!matchedSlice)return;
 const request=++shellGeneration,report=matchedReport,sliced=matchedSlice;
 try{
  const r=MassingReview.shell(report,sliced,JSON.parse(await file.text()),saved);
  if(request!==shellGeneration||report!==matchedReport||sliced!==matchedSlice)return;
  clearBundle();renderShell(r);
 }catch(error){if(request===shellGeneration)el('shell-status').textContent=error.message+' Previous matched shell results, if any, remain below.';}
};

function renderShell(r){
  const m=r.result.metrics,num=x=>x.toLocaleString(undefined,{maximumFractionDigits:3});
  showReviewSection('shell-results',!(false));
  el('shell-status').textContent='Shell receipt matches the loaded project G-code hash and pose.';
  el('shell-pairing').textContent=r.table_sha256&&r.mesh_sha256?'Recorded table and mesh hashes also match the export. The browser does not rerun the checker.':'Table and mesh hashes are not both recorded: geometry pairing is not established. Only G-code and pose are matched.';
  const placement=r._receipt?.schema==='fdmgen/shell-check@0.3'?r.placement:null;
  el('shell-pairing').textContent+=placement?` Recorded road-containment check at ${placement.bands.length} heights; tolerance ${num(placement.tol_mm)} mm, minimum inside fraction ${num(placement.min_inside)}. ${placement.bands.length<3?'Fewer than three heights: pose consistency is not established.':'This supports consistency with the claimed pose, not unique pose identity or full geometry verification.'}`:' Slice-to-body section checks are not recorded in this receipt.';
  el('shell-summary').textContent=`Recorded T ${r.result.verdict}${r.result.provisional?' · provisional':''}. ${num(100*m.thin_fraction)}% of ${m.samples} measured samples are thin; ${m.unmeasured} unmeasured. Estimated thin area: ${num(m.thin_area_mm2_est)} mm².`;
  el('shell-message').textContent=r.result.message;
  el('shell-method').textContent=`Raster cell ${num(r.cell_mm)} mm; ${m.min_beads} beads; spacing ${num(m.bead_spacing_mm)} mm; layer ${num(m.layer_mm)} mm; threshold ${m.threshold}; entry allowance ${num(m.entry_mm)} mm; clipped ${num(r.clipped_outside_grid_mm3)} mm³. ${r.method?'Additional method fields are in the complete receipt.':'Caps model, producer source, sampling seed and thin-fraction limit are not structurally recorded in this legacy receipt.'}`;
  el('shell-bands').replaceChildren();for(const b of m.bands){const row=add('tr','',el('shell-bands'));for(const value of [b.slope_deg.join('–'),b.samples,num(100*b.thin_fraction),num(b.median_mm),num(b.p05_mm),num(b.required_mm)])add('td',value,row);}
  el('shell-scope').textContent='Producer limitation: '+r.result.does_not_establish;
  el('shell-provenance').textContent=JSON.stringify(r._receipt||r,null,2);matchedShell=r;renderShellComparison();
}

function renderShellComparison(){
 showReviewSection('shell-comparison',!(!matchedShellBaseline));
 if(!matchedShellBaseline)return;
 const b=matchedShellBaseline.result.metrics,p=matchedShell?.result.metrics,num=x=>x.toLocaleString(undefined,{maximumFractionDigits:3});
 el('shell-comparison-summary').textContent=`Baseline: ${num(100*b.thin_fraction)}% thin among ${b.samples} measured samples (${b.unmeasured} unmeasured).`+(p?` Project: ${num(100*p.thin_fraction)}% among ${p.samples} (${p.unmeasured} unmeasured).`:' Load the project shell check to compare.');
 const comparison=MassingReview.shellComparison(matchedShell,matchedShellBaseline,matchedSlice);
 el('shell-comparison-status').textContent=comparison.comparable?`Matched sampled-screen comparison: project minus baseline ${num(100*(p.thin_fraction-b.thin_fraction))} percentage points. This does not establish unchanged thickness everywhere.`:'Comparison not established: '+comparison.reasons.join(' ');
 el('shell-baseline-provenance').textContent=JSON.stringify(matchedShellBaseline._receipt||matchedShellBaseline,null,2);
}
el('review-shell-baseline').onchange=async e=>{
 const file=e.target.files[0];if(!file||!matchedReport||!matchedSlice)return;
 const request=++shellBaselineGeneration,report=matchedReport,sliced=matchedSlice;
 try{
  const r=MassingReview.shell(report,sliced,JSON.parse(await file.text()),saved,'baseline');
  if(request!==shellBaselineGeneration||report!==matchedReport||sliced!==matchedSlice)return;
  clearBundle();matchedShellBaseline=r;el('shell-baseline-status').textContent='Baseline shell check matches the recorded shell-only G-code and pose.';renderShellComparison();
 }catch(error){if(request===shellBaselineGeneration)el('shell-baseline-status').textContent=error.message+' Previous matched baseline, if any, remains below.';}
};

function clearBundle(){
 ++bundleGeneration;el('review-bundle').value='';showReviewSection('bundle-results',!(true));
 el('bundle-status').textContent='No evidence bundle loaded. Select its manifest and all five receipt files together.';
}
el('review-bundle').onchange=async e=>{
 const files=[...e.target.files];if(!files.length||!matchedReport)return;
 const request=++bundleGeneration,report=matchedReport,draft=saved;
 try{
  const bundle=await EvidenceBundle.load(files,{report,draft,reportHash:matchedReportHash});
  if(request!==bundleGeneration||report!==matchedReport||draft!==saved)return;
  // Validate the whole set first; a rejected selection never partly replaces the review.
  renderSlice(bundle.slice);renderShell(bundle.project);matchedShellBaseline=bundle.baseline;renderShellComparison();
  el('slice-status').textContent='Bundle slice receipt matches the exported project and saved plan.';
  el('shell-baseline-status').textContent='Bundle baseline shell check matches the shell-only G-code and pose.';
  showReviewSection('bundle-results',!(false));el('bundle-status').textContent='All five receipt fingerprints verified; bundle matched this export.';
  el('bundle-summary').textContent='Loaded helper evidence, project shell check and baseline shell check together. Both bridge receipts are shown below.';

  const withheld=el('bundle-withheld');withheld.replaceChildren();withheld.hidden=true;
  for(const check of ['shell-check','bridge-check']){
   const pair=bundle.manifest.paired?.[check];
   if(!pair||!Object.hasOwn(pair,'withheld'))continue;
   const reasons=Array.isArray(pair.withheld)&&pair.withheld.length&&pair.withheld.every(x=>typeof x==='string'&&x.trim())
    ?pair.withheld:['Producer supplied no readable withholding reasons; inspect the complete manifest.'];
   if(withheld.hidden){el('bundle-summary').textContent+=` Producer withheld ${check} comparison: ${reasons[0]}`;withheld.hidden=false;}
   add('h3',`Producer withheld ${check} comparison`,withheld);
   const list=add('ul','',withheld);for(const reason of reasons)add('li',reason,list);
   if(check==='shell-check')el('shell-comparison-status').textContent=`Producer withheld this bundled comparison: ${reasons[0]} See the full reason list in the bundle section.`;
  }
  if(!withheld.hidden)add('p','These are the producer-reported reasons from the manifest. Receipt validation remains separate; no withheld numeric delta is promoted here.',withheld).className='hint';
  el('bundle-bridges').replaceChildren();
  for(const [kind,r]of Object.entries(bundle.bridges)){
   const row=add('article','',el('bundle-bridges')),m=r.result.metrics,num=v=>v.toLocaleString(undefined,{maximumFractionDigits:3});
   add('h3',`${kind==='project'?'Project':'Shell-only baseline'} bridges · T ${r.result.verdict}${r.result.provisional?' · provisional':''}`,row);
   if(r.result.verdict==='FAIL'){
    const note=add('p','This tool provides no verified helper-edit remedy for this bridge failure. The recorded FAIL uses the strand model. Changing helper boxes does not establish a fix; revised geometry needs fresh slicing and checks.',row);note.className='warning';note.dataset.bridgeRemedy='';
    for(const [label,url]of [['Bracket bridge-model investigation (#9)', 'https://github.com/thereprocase/fdm-design-toy/issues/9'], ['Bridge coupon work (#12)', 'https://github.com/thereprocase/fdm-design-toy/issues/12'], ['Owner decisions: bracket infill and coupon printing (#17)', 'https://github.com/thereprocase/fdm-design-toy/issues/17#issuecomment-6049963530']]){note.append(document.createTextNode(' '));const link=add('a',label,note);link.href=url;link.target='_blank';link.rel='noopener';}
   }
   add('p',`Strand maxima — external: ${num(m.max_span_external_mm)} mm (limit ${num(r.method.max_span_external_mm)} mm); internal: ${num(m.max_span_internal_mm)} mm (limit ${num(r.method.max_span_internal_mm)} mm). ${m.external_roads} external and ${m.internal_roads} internal roads evaluated.`,row);
   add('p','The recorded verdict uses strand spans along individual roads between their anchors.',row);
   const ceiling=key=>Number.isFinite(m[key])?num(m[key])+' mm':'not recorded';
   add('p',`Ceiling model maxima: external ${ceiling('max_ceiling_span_external_mm')}; internal ${ceiling('max_ceiling_span_internal_mm')}. This is twice the distance to the nearest support below, not the strand length. Each value is a separate maximum over the evaluated roads of that type; the maxima need not occur on the same road. A smaller ceiling span does not override the recorded strand verdict; physical behaviour needs testing.`,row);
   add('p',`Raster cell ${num(r.method.cell_mm)} mm; maximum cantilever ${num(m.max_cantilever_mm)} mm, reported without a cantilever verdict.`,row);
   if(m.bridge_roads===0)add('p','No bridge roads evaluated; zero span is not a measured bridge success.',row);
   add('p',r.result.does_not_establish,row);
   const details=add('details','',row);add('summary','Complete bridge receipt',details);add('pre',JSON.stringify(r,null,2),details);
  }
  el('bundle-provenance').textContent=JSON.stringify(bundle.manifest,null,2);
 }catch(error){if(request===bundleGeneration)el('bundle-status').textContent=error.message+' Previous matched evidence, if any, remains below.';}
};

function refreshReviewNav(){
 for(const button of document.querySelectorAll('#review-nav button')){
  const missing=el(button.dataset.reviewTarget).hidden;
  button.disabled=missing;button.textContent=button.dataset.label+(missing?' · not loaded':'');
 }
}
function showReviewSection(id,visible){el(id).hidden=!visible;refreshReviewNav();}
for(const button of document.querySelectorAll('#review-nav button'))button.onclick=()=>{
 const section=el(button.dataset.reviewTarget);if(section.hidden)return;
 const heading=section.querySelector('h2');heading.tabIndex=-1;heading.scrollIntoView({block:'start'});heading.focus({preventScroll:true});
};
refreshReviewNav();
