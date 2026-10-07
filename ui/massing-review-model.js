'use strict';
const MassingReview = (() => {
 const hash = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
 function draft(d) {
  if(d?.schema!=='fdmgen.massing-plan.v0.3'||!hash(d.source?.orientation_table_sha256)||!hash(d.source?.mesh?.sha256)||typeof d.orientation?.id!=='string')throw Error('Open a current planning draft with source fingerprints.');
  const m=d.massing;
  if(!m||!Array.isArray(m.helper_regions)||typeof m.shell_only!=='boolean'||(m.shell_only&&m.helper_regions.length))throw Error('Invalid draft helper list.');
  const ids=new Set();for(const h of m.helper_regions){if(typeof h.id!=='string'||ids.has(h.id)||typeof h.name!=='string')throw Error('Helper names and unique identifiers are required.');ids.add(h.id);}
  return d;
 }
 function pair(d, digest, r) {
  draft(d);
  if(r?.schema!=='fdmgen/massing-export@0.1')throw Error('Expected a massing-export receipt.');
  if(!hash(digest)||r.plan?.draft_sha256!==digest)throw Error('Receipt does not match the exact saved draft.');
  if(r.plan.table_sha256!==d.source.orientation_table_sha256||r.plan.mesh_sha256!==d.source.mesh.sha256||r.plan.candidate_id!==d.orientation.id||r.plan.problem!==d.source.problem)throw Error('Receipt source or pose differs from the draft.');
  if(!hash(r.project_3mf_sha256)||!hash(r.template_3mf_sha256)||typeof r.capability_context_matches_template!=='boolean')throw Error('Receipt is missing project or template provenance.');
  if(!Array.isArray(r.helpers)||!Array.isArray(r.checks))throw Error('Receipt needs helpers and checks.');
  const expected=new Set(d.massing.helper_regions.map(h=>h.id)),seen=new Set();
  for(const h of r.helpers){if(!expected.has(h.id)||seen.has(h.id))throw Error('Receipt contains unknown or duplicate helpers.');seen.add(h.id);}
  if(seen.size!==expected.size)throw Error('Receipt is missing helpers.');
  for(const c of r.checks)if(typeof c.rule!=='string'||typeof c.message!=='string'||!['V','M','T','P','FE'].includes(c.level)||!['PASS','FAIL','NOT_CHECKED'].includes(c.verdict)||typeof c.provisional!=='boolean'||!Array.isArray(c.fixes)||!c.fixes.every(f=>typeof f==='string'))throw Error('Invalid check result in receipt.');
  return r;
 }
 function slice(report, evidence) {
  if(evidence?.schema!=='fdmgen/massing-slice-evidence@0.1'||evidence.tier!=='S'||evidence.level!=='T')throw Error('Expected an S-tier, T-level massing slice receipt.');
  if(evidence.project_3mf_sha256!==report.project_3mf_sha256)throw Error('Slice receipt belongs to a different exported project.');
  for(const key of ['draft_sha256','table_sha256','mesh_sha256','problem','candidate_id'])if(evidence.plan?.[key]!==report.plan[key])throw Error('Slice receipt plan provenance differs from the export.');
  if(![null,'shell-only slice'].includes(evidence.baseline))throw Error('Unknown baseline kind.');
  const finite=(x,label,nonnegative=false)=>{if(!Number.isFinite(x)||(nonnegative&&x<0))throw Error(`Invalid slice measurement: ${label}`);};
  for(const key of ['credited_mm3','min_fill_fraction','min_added_mm3'])finite(evidence[key],key,true);
  if(!Array.isArray(evidence.placement_shift_xy_mm)||evidence.placement_shift_xy_mm.length!==2||!evidence.placement_shift_xy_mm.every(Number.isFinite))throw Error('Invalid slice placement shift.');
  if(!Array.isArray(evidence.helpers))throw Error('Slice receipt needs helper measurements.');
  const expected=new Set(report.helpers.map(h=>h.id)),seen=new Set();
  for(const h of evidence.helpers){
   if(!expected.has(h.id)||seen.has(h.id))throw Error('Unknown or duplicate sliced helper.');seen.add(h.id);
   if(!['PASS','FAIL','NOT_CHECKED'].includes(h.verdict)||typeof h.message!=='string')throw Error('Invalid sliced helper verdict.');
   for(const key of ['solid_infill_in_box_mm3','box_volume_mm3'])finite(h[key],key,true);
   for(const key of ['added_solid_mm3','added_fill_fraction'])finite(h[key],key);
   if(evidence.baseline===null){if(h.baseline_solid_infill_mm3!==null)throw Error('Baseline volume supplied without a baseline slice.');}
   else finite(h.baseline_solid_infill_mm3,'baseline volume',true);
  }
  if(seen.size!==expected.size)throw Error('Slice receipt is missing helpers.');
  return evidence;
 }
 function contextMismatch(r){
  const mismatch=new Set(Array.isArray(r.baseline_context_mismatch)?r.baseline_context_mismatch:[]);
  if(r.baseline&&r.slicer&&r.baseline_slicer)for(const key of ['generator','version','printer_model','print_settings_id','filament_settings_id','layer_height','wall_loops','sparse_infill_density','filament_shrink','enable_support'])if(r.slicer[key]!==r.baseline_slicer[key])mismatch.add(key);
  return [...mismatch];
 }
 function shell(report,sliced,r,planningDraft,kind='project'){
  slice(report,sliced);
  if(!['project','baseline'].includes(kind)||kind==='baseline'&&sliced.baseline!=='shell-only slice')throw Error('Shell check needs the requested slice baseline.');
  const context=kind==='baseline'?sliced.baseline_slicer:sliced.slicer;
  if(r&&Object.prototype.hasOwnProperty.call(r,'_receipt'))throw Error('Reserved shell view field in input.');
  if(r?.schema==='fdmgen/shell-check@0.2'){
   const vec=v=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite);
   if(!planningDraft||!vec(r.pose?.t_mm)||!Array.isArray(r.pose?.R_design_to_print)||r.pose.R_design_to_print.length!==3||!r.pose.R_design_to_print.every(vec))throw Error('Shell-check needs the saved pose transform.');
   for(const key of ['R_design_to_print','t_mm'])if(JSON.stringify(r.pose[key])!==JSON.stringify(planningDraft.orientation[key]))throw Error('Shell-check transform differs from the saved draft.');
   if(!hash(r.table?.sha256)||!hash(r.mesh?.sha256)||!vec(r.grid?.origin_mm)||r.grid.frame!=='print (plate) frame of the pose')throw Error('Missing shell geometry provenance.');
   for(const key of ['generator','version','printer_model','print_settings_id','filament_settings_id','layer_height','wall_loops','sparse_infill_density','filament_shrink','enable_support'])if(r.gcode?.[key]===undefined||r.gcode[key]===null||r.gcode[key]===''||r.gcode[key]!==context?.[key])throw Error('Shell-check slicer settings are missing or differ: '+key);
   const method=r.method;
   if(!method||method.deposit?.roads!=='credited'||typeof method.deposit.caps!=='boolean'||!Number.isFinite(method.deposit.step_frac)||method.deposit.step_frac<=0||method.deposit.step_frac>1||!Number.isInteger(method.seed)||!Number.isInteger(method.surface_samples)||method.surface_samples!==r.result?.metrics?.samples+r.result?.metrics?.unmeasured||!Number.isFinite(method.thin_fraction_limit)||method.thin_fraction_limit<0||method.thin_fraction_limit>1)throw Error('Invalid shell method provenance.');
   for(const key of ['min_beads','bead_spacing_mm','layer_mm','entry_mm'])if(method[key]!==r.result?.metrics?.[key])throw Error('Shell method differs from result: '+key);
   for(const key of ['fdmgen/catalog/checks/shell.py','fdmgen/gcode/occupancy.py','fdmgen/gcode/reader.py'])if(!hash(r.source_sha256?.[key]))throw Error('Missing shell producer source hash.');
   r={...r,_receipt:r,schema:'fdmgen/shell-check@0.1',gcode_sha256:r.gcode?.gcode_sha256,pose:r.pose.id,
      table_sha256:r.table.sha256,mesh_sha256:r.mesh.sha256,cell_mm:r.grid.cell_mm,grid_shape:r.grid.shape,clipped_outside_grid_mm3:r.grid.clipped_outside_grid_mm3};
  }
  if(r?.schema!=='fdmgen/shell-check@0.1')throw Error('Expected a shell-check receipt.');
  if(!hash(r.gcode_sha256)||r.gcode_sha256!==context?.gcode_sha256)throw Error('Shell-check G-code differs from the loaded '+kind+' slice.');
  if(r.pose!==report.plan.candidate_id)throw Error('Shell-check pose differs from the export.');
  for(const key of ['table_sha256','mesh_sha256'])if(r[key]!==undefined&&(!hash(r[key])||r[key]!==report.plan[key]))throw Error('Shell-check '+key+' differs from the export.');
  const c=r.result,m=c?.metrics;
  if(c?.rule!=='SHELL-001'||c.level!=='T'||!['PASS','FAIL','NOT_CHECKED'].includes(c.verdict)||typeof c.provisional!=='boolean'||typeof c.message!=='string'||typeof c.does_not_establish!=='string')throw Error('Invalid SHELL-001 result or scope.');
  const positive=v=>Number.isFinite(v)&&v>0,nonnegative=v=>Number.isFinite(v)&&v>=0,fraction=v=>nonnegative(v)&&v<=1,count=v=>Number.isInteger(v)&&v>=0;
  if(!positive(r.cell_mm)||!Array.isArray(r.grid_shape)||r.grid_shape.length!==3||!r.grid_shape.every(v=>count(v)&&v>0)||!nonnegative(r.clipped_outside_grid_mm3))throw Error('Invalid shell raster geometry.');
  if(!m||!count(m.samples)||m.samples===0||!count(m.unmeasured)||!fraction(m.thin_fraction)||!nonnegative(m.thin_area_mm2_est)||!Array.isArray(m.bands))throw Error('Invalid shell sample accounting.');
  for(const key of ['min_beads','bead_spacing_mm','layer_mm','entry_mm'])if(!positive(m[key]))throw Error('Invalid shell method input: '+key);
  if(!fraction(m.threshold))throw Error('Invalid shell threshold.');
  for(const b of m.bands){
   if(!Array.isArray(b.slope_deg)||b.slope_deg.length!==2||!b.slope_deg.every(v=>nonnegative(v)&&v<=90)||b.slope_deg[0]>=b.slope_deg[1]||!count(b.samples)||!fraction(b.thin_fraction)||!['median_mm','p05_mm','required_mm'].every(k=>nonnegative(b[k])))throw Error('Invalid shell slope band.');
  }
  if(m.bands.reduce((n,b)=>n+b.samples,0)!==m.samples)throw Error('Shell band counts differ from measured samples.');
  return r;
 }
 function shellComparison(project,baseline,sliced){
  const reasons=[];
  const p=project?._receipt,b=baseline?._receipt;
  if(!p||!b)return {comparable:false,reasons:['Both shell checks need current geometry and method provenance.']};
  if(contextMismatch(sliced).length)reasons.push('Project and baseline slicer settings differ.');
  const stable=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
  for(const [label,x,y] of [['table',p.table.sha256,b.table.sha256],['mesh',p.mesh.sha256,b.mesh.sha256],['pose',p.pose,b.pose],['method',p.method,b.method],['producer source',p.source_sha256,b.source_sha256]])if(stable(x)!==stable(y))reasons.push('Shell '+label+' differs.');
  for(const key of ['frame','origin_mm','cell_mm','shape'])if(stable(p.grid[key])!==stable(b.grid[key]))reasons.push('Shell grid '+key+' differs.');
  if(p.grid.clipped_outside_grid_mm3!==0||b.grid.clipped_outside_grid_mm3!==0)reasons.push('Shell raster clips deposited volume.');
  if(project.result.metrics.unmeasured||baseline.result.metrics.unmeasured)reasons.push('Unmeasured surface samples prevent this comparison.');
  return {comparable:reasons.length===0,reasons};
 }
 function mechanics(report, sliced, r){
  slice(report,sliced);
  if(r?.schema!=='fdmgen/seat-load-transfer-pilot@0.1')throw Error('Expected a seat-load-transfer mechanics pilot receipt.');
  if(typeof r.method!=='string'||typeof r.establishes!=='string'||!Array.isArray(r.does_not_establish)||!r.does_not_establish.every(x=>typeof x==='string'))throw Error('Mechanics receipt needs method and evidence scope.');
  if(sliced.baseline!=='shell-only slice'||contextMismatch(sliced).length)throw Error('Mechanics comparison needs a matching-context shell-only slice baseline.');
  for(const context of [sliced.slicer,sliced.baseline_slicer])for(const key of ['generator','version','printer_model','print_settings_id','filament_settings_id','layer_height','wall_loops','sparse_infill_density','filament_shrink','enable_support'])if(context?.[key]===undefined||context[key]===null||context[key]==='')throw Error('Mechanics comparison needs complete recorded slicer context.');
  const project=r.inputs?.project?.provenance,baseline=r.inputs?.baseline?.provenance;
  if(project?.project_3mf_sha256!==report.project_3mf_sha256)throw Error('Mechanics receipt belongs to a different exported project.');
  for(const key of ['draft_sha256','table_sha256','mesh_sha256','problem','candidate_id'])if(project.plan?.[key]!==report.plan[key])throw Error('Mechanics receipt plan differs from the export.');
  for(const [name,p,context] of [['project',project,sliced.slicer],['baseline',baseline,sliced.baseline_slicer]]){
   if(!hash(p?.gcode_sha256)||p.gcode_sha256!==context?.gcode_sha256)throw Error(`Mechanics ${name} G-code differs from the loaded slice.`);
   if(!hash(r.inputs[name].npz_sha256)||!hash(r.reference_sha256)||p.grid_receipt_sha256!==r.reference_sha256)throw Error('Missing or inconsistent mechanics grid provenance.');
   const vec3=v=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite);
   if(!vec3(p.grid?.shape)||!p.grid.shape.every(v=>Number.isInteger(v)&&v>0)||!vec3(p.grid?.h_mm)||!p.grid.h_mm.every(v=>v>0)||!vec3(p.grid?.origin_print_mm))throw Error('Mechanics receipt needs the complete grid.');
   if(p.table_sha256!==report.plan.table_sha256||p.pose!==report.plan.candidate_id)throw Error('Mechanics grid table or pose differs.');
  }
  for(const key of ['grid','installed_to_print','pose_R_design_to_print','pose_t_mm'])if(JSON.stringify(project[key])!==JSON.stringify(baseline[key]))throw Error('Mechanics grids or transforms differ.');
  if(!['largest-face-component sensitivity','unmodified threshold masks'].includes(r.domain_policy))throw Error('Unknown mechanics domain policy.');
  if(!Number.isFinite(r.threshold)||r.threshold<=0||r.threshold>1||!hash(r.transferred_load_sha256))throw Error('Invalid mechanics threshold or load provenance.');
  const nonnegative=(v,label)=>{if(!Number.isFinite(v)||v<0)throw Error('Invalid mechanics measurement: '+label);};
  if(!r.seats||!Object.keys(r.seats).length)throw Error('Mechanics receipt is missing seat conservation checks.');
  for(const seat of Object.values(r.seats))for(const key of ['force_error_N','moment_error_N_mm','weight_min','weight_max'])nonnegative(seat[key],key);
  for(const name of ['full_solid','baseline','project']){
   const a=r.audits?.[name];if(!a||!['ready','blocked'].includes(a.status)||!Array.isArray(a.reasons))throw Error('Mechanics receipt needs domain audits.');
   for(const key of ['cells','face_components','missing_loaded_dofs','loaded_fixed_dofs','restrained_rigid_modes'])nonnegative(a[key],key);
   const solve=r.solves?.[name];if(solve?.status==='solved')for(const key of ['compliance_N_mm','max_displacement_mm','true_relative_residual'])nonnegative(solve[key],key);
   if(r.domain_policy==='largest-face-component sensitivity'){
    const removal=r.fragment_removal?.[name];if(!removal)throw Error('Mechanics receipt must record removed fragments.');
    for(const key of ['removed_cells','removed_volume_mm3','removed_original_load_l1_N','removed_fixed_dofs'])nonnegative(removal[key],key);
   }
  }
  return r;
 }
 function mechanicsComparable(r){
  return ['full_solid','baseline','project'].every(name=>{
   const a=r.audits[name],s=r.solves?.[name];
   return a.status==='ready'&&a.reasons.length===0&&a.face_components===1&&a.missing_loaded_dofs===0&&a.loaded_fixed_dofs===0&&a.restrained_rigid_modes===6&&s?.status==='solved'&&s.true_relative_residual<=1e-8&&s.compliance_N_mm>0;
  })&&Object.values(r.seats).every(s=>s.force_error_N<=1e-9&&s.moment_error_N_mm<=1e-7);
 }
 return {draft,pair,slice,contextMismatch,shell,shellComparison,mechanics,mechanicsComparable};
})();
if(typeof module!=='undefined')module.exports=MassingReview;
