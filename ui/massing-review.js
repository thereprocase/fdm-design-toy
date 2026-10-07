'use strict';
const el=id=>document.getElementById(id);
let saved=null,digest=null,generation=0,receiptGeneration=0,matchedReport=null,sliceGeneration=0,matchedSlice=null,mechanicsGeneration=0;
function add(tag,value,parent){const n=document.createElement(tag);n.textContent=value;parent.append(n);return n;}
el('review-draft').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;const request=++generation;++receiptGeneration;
 // Clear old results immediately, so they cannot be mistaken for this revision.
 clearSlice();matchedReport=null;saved=null;digest=null;el('review-workspace').hidden=true;el('review-receipt').disabled=true;el('review-receipt').value='';
 try{const raw=await file.arrayBuffer(),d=MassingReview.draft(JSON.parse(new TextDecoder().decode(raw))),h=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),b=>b.toString(16).padStart(2,'0')).join('');if(request!==generation)return;saved=d;digest=h;el('review-receipt').disabled=false;el('review-status').textContent='Draft loaded. Open its matching export receipt.';}catch(err){if(request===generation)el('review-status').textContent=err.message;}
};
el('review-receipt').onchange=async e=>{
 const file=e.target.files[0];if(!file||!saved)return;const request=++receiptGeneration,current=generation;
 try{const r=MassingReview.pair(saved,digest,JSON.parse(await file.text()));if(current!==generation||request!==receiptGeneration)return;render(r);el('review-status').textContent='Receipt fingerprint matched this saved draft.';}catch(err){if(current===generation&&request===receiptGeneration)el('review-status').textContent=err.message+' Previous matched results, if any, remain below.';}
};
function render(r){
 clearSlice();matchedReport=r;el('review-slice').disabled=false;
 el('review-workspace').hidden=false;el('review-title').textContent=`${r.plan.problem} · ${r.plan.candidate_id}`;
 el('review-context').textContent=r.capability_context_matches_template?'Template fingerprint matches the capability context. This does not validate every changed value or combination.':'Template differs from the measured capability context. Helper settings are unverified for this profile.';
 if(r.warning)el('review-context').textContent+=' '+r.warning;
 el('review-scope').textContent=`${r.establishes||''} Does not establish: ${r.does_not_establish||'printed performance or strength.'}`;
 const failed=r.checks.filter(c=>c.verdict==='FAIL').length,unchecked=r.checks.filter(c=>c.verdict==='NOT_CHECKED').length;
 el('review-count').textContent=r.checks.length?`${failed} failed checks; ${unchecked} not checked. Passing checks apply only to the stated method and evidence level.`:'No helper checks reported; this is not a checked result.';
 el('review-checks').replaceChildren();
 const names=new Map(saved.massing.helper_regions.map(h=>[h.id,h.name]));
 for(const c of r.checks){const row=add('article','',el('review-checks'));add('h3',`${c.rule} · ${c.level} · ${c.verdict}${c.provisional?' · provisional':''}`,row);let message=c.message;for(const [id,name]of names)message=message.split(id).join(`${name} [${id}]`);add('p',message,row);if(names.has(c.metrics?.helper_id))editButton(c.metrics.helper_id,names.get(c.metrics.helper_id),row);const fixes=add('ul','',row);for(const fix of c.fixes)add('li',fix,fixes);if(c.establishes)add('p',c.establishes,row);if(c.does_not_establish)add('p','Does not establish: '+c.does_not_establish,row);const details=add('details','',row);add('summary','Measurements',details);add('pre',JSON.stringify(c.metrics||{},null,2),details);}
 el('review-helpers').replaceChildren();
 for(const h of r.helpers){const planned=saved.massing.helper_regions.find(p=>p.id===h.id),row=add('article','',el('review-helpers'));add('h3',planned.name,row);editButton(h.id,planned.name,row);add('p',`Helper ID: ${h.id}`,row);add('p',planned.purpose||'',row);add('pre',JSON.stringify({design_box:planned.geometry,exported_settings:h.settings,print_bbox_mm:h.print_bbox_mm},null,2),row);}
 if(!r.helpers.length)add('p','Shell-only draft; no helpers.',el('review-helpers'));
 el('review-setting-evidence').textContent=r.settings_evidence?JSON.stringify(r.settings_evidence,null,2):'Per-value setting evidence was not recorded in this receipt.';
 el('review-settings').textContent=JSON.stringify(r.object_settings,null,2);el('review-skin').textContent=r.skin_note||'';el('review-provenance').textContent=JSON.stringify(r,null,2);
}

function clearSlice(){clearMechanics();matchedSlice=null;++sliceGeneration;el('review-slice').value='';el('review-slice').disabled=true;el('slice-results').hidden=true;el('slice-status').textContent='No slice evidence loaded.';}
el('review-slice').onchange=async e=>{
 const file=e.target.files[0];if(!file||!matchedReport)return;const request=++sliceGeneration,report=matchedReport;
 try{const receipt=MassingReview.slice(report,JSON.parse(await file.text()));if(request!==sliceGeneration||report!==matchedReport)return;renderSlice(receipt);el('slice-status').textContent='Slice receipt matches the exported project and saved plan.';}
 catch(error){if(request===sliceGeneration)el('slice-status').textContent=error.message+' Previous matched slice results, if any, remain below.';}
};
function renderSlice(r){
 clearMechanics();matchedSlice=r;el('review-mechanics').disabled=false;
 const baseline=r.baseline!==null,mismatch=MassingReview.contextMismatch(r),number=x=>x.toLocaleString(undefined,{maximumFractionDigits:3});
 el('slice-results').hidden=false;
 el('slice-baseline').textContent=baseline?'Compared with a shell-only slice. Differences describe solid infill in each helper box; overlapping boxes may count the same roads.':'No shell-only baseline supplied. Absolute fill includes existing body material; helper contribution is not established.';
 if(mismatch.length)el('slice-baseline').textContent='Baseline settings differ: '+mismatch.join(', ')+'. Reported differences cannot be attributed to helpers alone; re-slice with matching settings.';
 el('slice-settings').textContent=JSON.stringify({project:r.slicer||'Not recorded',baseline:r.baseline_slicer||'Not recorded'},null,2);
 el('slice-thresholds').textContent=`Producer thresholds: ${number(r.min_fill_fraction*100)}% of box volume and ${number(r.min_added_mm3)} mm³. These are slicer screening thresholds, not strength limits.`;
 el('slice-scope').textContent=(baseline&&!mismatch.length?(r.establishes||''):'Helper contribution is not established by this comparison.')+' Does not establish: '+(r.does_not_establish||'shell bonding or strength.');
 el('slice-helpers').replaceChildren();
 for(const h of r.helpers){const name=saved.massing.helper_regions.find(p=>p.id===h.id).name,row=add('article','',el('slice-helpers'));add('h3',`${name} · T ${h.verdict}${!baseline?' (absolute-fill screen)':mismatch.length?' (context mismatch)':''}`,row);editButton(h.id,name,row);
  const values=add('dl','',row);
  for(const [label,value] of [['Project solid infill in box',number(h.solid_infill_in_box_mm3)+' mm³'],['Shell-only solid infill in box',baseline?number(h.baseline_solid_infill_mm3)+' mm³':'Not checked'],[mismatch.length?'Uncontrolled solid-infill difference':'Added solid infill',baseline?number(h.added_solid_mm3)+' mm³':'Not attributable without baseline'],['Added fill / box volume',baseline?number(h.added_fill_fraction*100)+'%':'Not attributable without baseline']]){add('dt',label,values);add('dd',value,values);}
  if(baseline&&!mismatch.length)add('p',h.message.replace(h.id,name),row);
 }
 el('slice-credit').textContent=`Whole-slice credited material: ${number(r.credited_mm3)} mm³. This is not a sum of helper contributions or a strength result.`;
 el('slice-source-note').textContent='Project/plan pairing checked; G-code contents and matching baseline settings are not verified by this page. Inspect recorded provenance below; older receipts may omit G-code fingerprints and slicer settings.';
 el('slice-provenance').textContent=JSON.stringify(r,null,2);
}

function editButton(helperId,name,parent){
 const button=add('button',`Edit ${name}`,parent);button.type='button';button.className='secondary';
 button.onclick=()=>{
  try{sessionStorage.setItem('fdmgen-review-edit',JSON.stringify({draft:saved,helper_id:helperId}));location.href='index.html#review-edit';}
  catch(error){el('review-status').textContent='This browser cannot transfer the draft between pages. Return to the workspace, load its original table, and reopen the saved draft to edit '+name+'.';}
 };
}

function clearMechanics(){
 ++mechanicsGeneration;el('review-mechanics').value='';el('review-mechanics').disabled=true;
 el('mechanics-results').hidden=true;el('mechanics-status').textContent='Load paired slice evidence before mechanics.';
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
 const comparable=MassingReview.mechanicsComparable(r),num=x=>x.toLocaleString(undefined,{maximumFractionDigits:3});
 el('mechanics-results').hidden=false;
 el('mechanics-policy').textContent=`FE pilot · provisional. Domain policy: ${r.domain_policy}; density threshold ${r.threshold}. ${r.domain_policy==='largest-face-component sensitivity'?'Fragments were explicitly removed. This is not the unmodified raster result.':'Original thresholded domains; inspect connectivity failures below.'}`;
 el('mechanics-comparison').textContent=comparable?`Project compliance change versus shell-only: ${num(100*(r.solves.project.compliance_N_mm/r.solves.baseline.compliance_N_mm-1))}%. Applies only to this domain and load policy; not a strength rating.`:'No supported compliance comparison: an audit, conservation or convergence check is missing or failed.';
 el('mechanics-model').textContent=`Load method: ${r.method}. ${r.context_note||''} Material constants are not recorded in this pilot receipt; consult its reproducible benchmark. Linear model outputs do not establish physical movement.`;
 const grid=r.inputs.baseline.provenance.grid;
 el('mechanics-resolution').textContent=`Solver cell size: ${grid.h_mm.map(num).join(' × ')} mm; grid ${grid.shape.join(' × ')} cells. Bead sampling refines deposition inside this grid, not the FE mesh.`;
 el('mechanics-sampling').textContent=[['baseline','Shell-only'],['project','Project']].map(([key,label])=>{
  const sampling=r.inputs[key].provenance.sampling;
  const step=sampling?.step_mm;
  return `${label} bead sampling step: ${typeof step==='number'&&Number.isFinite(step)&&step>0?num(step)+' mm':'not recorded'}.`;
 }).join(' ');
 el('mechanics-rows').replaceChildren();el('mechanics-audits').replaceChildren();
 for(const [name,label] of [['full_solid','Full-body context'],['baseline','Shell-only'],['project','Seeded project']]){
  const a=r.audits[name],s=r.solves?.[name],row=add('tr','',el('mechanics-rows'));
  const valid=a.status==='ready'&&s?.status==='solved'&&s.true_relative_residual<=1e-8;
  for(const value of [label,`${a.status} / ${s?.status||'not solved'}`,valid?num(s.compliance_N_mm):'Not established',valid?num(s.max_displacement_mm):'Not established'])add('td',value,row);
  const detail=add('article','',el('mechanics-audits'));add('h3',label,detail);
  add('p',`${a.cells} cells; ${a.face_components} face-connected components; ${a.missing_loaded_dofs} missing loaded DOFs.`,detail);
  for(const reason of a.reasons)add('p',String(reason),detail);
  const f=r.fragment_removal?.[name];if(f)add('p',`Removed ${f.removed_cells} cells (${num(f.removed_volume_mm3)} mm³ of grid-cell volume); ${f.removed_fixed_dofs} fixed DOFs and ${num(f.removed_original_load_l1_N)} N summed absolute original nodal force lost exclusively with removed nodes.`,detail);
  if(s?.status==='solved')add('p',`True relative residual: ${s.true_relative_residual.toExponential(3)}.`,detail);
 }
 el('mechanics-scope').textContent=`${r.establishes||''} Does not establish: ${(r.does_not_establish||[]).join('; ')}.`;
 el('mechanics-provenance').textContent=JSON.stringify(r,null,2);
}
