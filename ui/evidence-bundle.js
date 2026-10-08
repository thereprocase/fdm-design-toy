/* Hash-pinned local evidence imports. No file paths are fetched or executed. */
(function(root){
 'use strict';
 const Review=typeof module==='object'?require('./massing-review-model.js'):MassingReview;
 const webcrypto=typeof module==='object'?require('node:crypto').webcrypto:root.crypto;
 const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
 const same=(a,b)=>JSON.stringify(a,sorter)===JSON.stringify(b,sorter);
 function sorter(_,v){return v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v;}
 async function digest(bytes){return Array.from(new Uint8Array(await webcrypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');}
 const slots=['massing-evidence/project','shell-check/project','shell-check/shell-only','bridge-check/project','bridge-check/shell-only'];
 const verdicts=['PASS','FAIL','NOT_CHECKED'];
 function bridge(r,shell){
  if(r.schema!=='fdmgen/bridge-check@0.2')throw Error('Unsupported bundled bridge receipt.');
  for(const k of ['pose','table','mesh'])if(!same(r[k],shell[k]))throw Error('Bridge '+k+' differs from its shell receipt.');
  for(const k of ['gcode_sha256','generator','version','printer_model','print_settings_id','filament_settings_id','layer_height','wall_loops','sparse_infill_density','filament_shrink','enable_support','extruder_offset_mm'])if(r.gcode?.[k]===undefined||!same(r.gcode[k],shell.gcode[k]))throw Error('Bridge slice context differs: '+k);
  const p=r.placement;
  if(!p||!same(p.shift_xy_mm,shell.placement.shift_xy_mm)||!Number.isFinite(p.tol_mm)||p.tol_mm<=0||!Number.isFinite(p.min_inside)||p.min_inside<=0||p.min_inside>1||typeof p.verified!=='string'||!Array.isArray(p.bands)||p.bands.length<3)throw Error('Bridge pose evidence is incomplete.');
  const heights=new Set();
  for(const b of p.bands){if(!Number.isFinite(b.z_mm)||b.z_mm<0||heights.has(b.z_mm)||!Number.isFinite(b.inside_fraction)||b.inside_fraction<p.min_inside||b.inside_fraction>1||!Number.isInteger(b.points)||b.points<=0)throw Error('Invalid bridge pose band.');heights.add(b.z_mm);}
  const c=r.result,m=c?.metrics;
  if(c?.rule!=='BRG-001'||c.level!=='T'||!verdicts.includes(c.verdict)||typeof c.provisional!=='boolean'||typeof c.does_not_establish!=='string')throw Error('Invalid bundled bridge result.');
  for(const k of ['max_span_external_mm','max_span_internal_mm','max_cantilever_mm'])if(!Number.isFinite(m?.[k])||m[k]<0)throw Error('Invalid bridge measurement: '+k);
  for(const k of ['max_ceiling_span_external_mm','max_ceiling_span_internal_mm'])if(k in m&&(!Number.isFinite(m[k])||m[k]<0))throw Error('Invalid ceiling measurement: '+k);
  for(const k of ['bridge_roads','external_roads','internal_roads'])if(!Number.isInteger(m?.[k])||m[k]<0)throw Error('Invalid bridge coverage.');
  for(const k of ['cell_mm','max_span_external_mm','max_span_internal_mm'])if(!Number.isFinite(r.method?.[k])||r.method[k]<=0)throw Error('Invalid bridge method.');
  for(const k of ['fdmgen/catalog/checks/toolpath.py','fdmgen/gcode/occupancy.py','fdmgen/gcode/reader.py'])if(!hash(r.source_sha256?.[k]))throw Error('Missing bridge source hash.');
  return r;
 }
 async function load(files,{report,draft,reportHash}){
  if(!hash(reportHash))throw Error('Reload the export report before importing a bundle.');
  const entries=new Map();
  for(const f of files){if(entries.has(f.name))throw Error('Duplicate selected filename: '+f.name);const bytes=await f.arrayBuffer();entries.set(f.name,{value:JSON.parse(new TextDecoder().decode(bytes)),sha:await digest(bytes)});}
  const manifests=[...entries.values()].filter(e=>e.value.schema==='fdmgen/evidence-bundle@0.1');
  if(manifests.length!==1)throw Error('Select one evidence-bundle manifest and its five receipt files.');
  const manifest=manifests[0].value;
  if(manifest.inputs?.report_sha256!==reportHash)throw Error('Bundle belongs to a different export report. Select the bundle generated from this report, or run fdmgen evidence with the current report and its matching inputs.');
  if(manifest.inputs?.table_sha256!==report.plan.table_sha256)throw Error('Bundle belongs to a different orientation table. Use the exact table bytes pinned by this export report.');
  if(manifest.pose!==report.plan.candidate_id)throw Error('Bundle belongs to a different pose. Select the bundle generated for this export report and pose.');
  if(!Array.isArray(manifest.receipts)||manifest.receipts.length!==5)throw Error('Bundle needs all five receipt entries.');
  const receipts=new Map(),paths=new Set();
  for(const e of manifest.receipts){
   const slot=e.check+'/'+e.slice_kind;
   if(!slots.includes(slot)||receipts.has(slot))throw Error('Unknown or duplicate bundle receipt role.');
   if(typeof e.path!=='string'||!e.path||/[\\/:]/.test(e.path)||e.path==='.'||e.path==='..'||paths.has(e.path))throw Error('Select a bundle with unique receipt filenames in one directory.');
   paths.add(e.path);const file=entries.get(e.path);
   if(!file)throw Error('Missing bundle receipt: '+e.path);
   if(!hash(e.sha256)||file.sha!==e.sha256)throw Error('Receipt fingerprint differs: '+e.path);
   if(file.value.schema!==e.schema||!verdicts.includes(e.verdict))throw Error('Receipt schema or verdict differs: '+e.path);
   receipts.set(slot,file.value);
  }
  const slice=Review.slice(report,receipts.get('massing-evidence/project'));
  for(const [kind,context]of [['project',slice.slicer],['shell-only',slice.baseline_slicer]])if(!hash(manifest.inputs.gcode_sha256?.[kind])||manifest.inputs.gcode_sha256[kind]!==context?.gcode_sha256)throw Error('Bundle G-code differs from slice evidence.');
  const project=Review.shell(report,slice,receipts.get('shell-check/project'),draft);
  const baseline=Review.shell(report,slice,receipts.get('shell-check/shell-only'),draft,'baseline');
  for(const s of [project,baseline])if(s._receipt?.schema!=='fdmgen/shell-check@0.3'||s.placement.bands.length<3)throw Error('Bundled shell checks need version 0.3 and at least three pose-check heights.');
  const bridges={project:bridge(receipts.get('bridge-check/project'),project._receipt),baseline:bridge(receipts.get('bridge-check/shell-only'),baseline._receipt)};
  for(const e of manifest.receipts){const r=receipts.get(e.check+'/'+e.slice_kind),vs=r.helpers?.map(h=>h.verdict);const v=e.check==='massing-evidence'?(vs.includes('FAIL')?'FAIL':vs.length&&vs.every(v=>v==='PASS')?'PASS':'NOT_CHECKED'):r.result.verdict;if(v!==e.verdict)throw Error('Manifest verdict differs from receipt: '+e.path);}
  return {manifest,slice,project,baseline,bridges};
 }
 const api={load,digest};if(typeof module==='object')module.exports=api;else root.EvidenceBundle=api;
})(globalThis);
