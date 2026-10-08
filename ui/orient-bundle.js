/* Validate local orientation evidence files before any workspace state changes. */
(function(root){
 'use strict';
 const crypto=typeof module==='object'?require('node:crypto').webcrypto:root.crypto;
 const hash=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
 const same=(a,b)=>JSON.stringify(a,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v)===JSON.stringify(b,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
 const finite=n=>Number.isFinite(n)&&n>=0;
 const vector=(v,n)=>Array.isArray(v)&&v.length===n&&v.every(Number.isFinite);
 const name=s=>typeof s==='string'&&s.length>0&&!/[\\/:]/.test(s)&&s!=='.'&&s!=='..';
 const verdicts=['PASS','FAIL','NOT_CHECKED'];
 async function digest(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');}
 function placement(p){
  if(!p||!vector(p.shift_xy_mm,2)||!Number.isFinite(p.tol_mm)||p.tol_mm<=0||!Number.isFinite(p.min_inside)||p.min_inside<=0||p.min_inside>1||typeof p.verified!=='string'||!Array.isArray(p.bands)||p.bands.length<3)throw Error('Receipt needs pose consistency checks at three or more heights.');
  const heights=new Set();
  for(const b of p.bands){
   if(!finite(b.z_mm)||heights.has(b.z_mm)||!Number.isFinite(b.inside_fraction)||b.inside_fraction<p.min_inside||b.inside_fraction>1||!Number.isInteger(b.points)||b.points<=0)throw Error('Invalid or repeated pose-check height.');
   heights.add(b.z_mm);
  }
 }
 function column(c,r,e,key,value,unit,verdict){
  const col=c.columns?.[key];
  if(!col||col.value!==value||col.unit!==unit||col.rule!==r.result.rule||col.level!=='T'||col.verdict!==verdict||col.provisional!==r.result.provisional)throw Error('Enriched table measurement differs from receipt: '+c.id+'/'+key);
  if(col.receipt?.sha256!==e.sha256||col.receipt.slice_kind!==e.slice_kind||col.receipt.gcode_sha256!==e.gcode_sha256||!same(col.receipt.source_sha256,r.source_sha256))throw Error('Enriched table receipt binding differs: '+c.id+'/'+key);
  return col;
 }
 async function load(files){
  const entries=new Map();
  for(const f of files){
   if(!name(f.name)||entries.has(f.name))throw Error('Duplicate or unsupported selected filename: '+f.name);
   if(f.size>20*1024*1024)throw Error('Orientation evidence supports JSON files up to 20 MB each.');
   const bytes=await f.arrayBuffer();let value;
   try{value=JSON.parse(new TextDecoder().decode(bytes));}catch{throw Error('Invalid JSON in selected file: '+f.name);}
   if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Expected a JSON object in '+f.name);
   entries.set(f.name,{bytes,value,sha:await digest(bytes)});
  }
  const manifests=[...entries.values()].filter(e=>e.value.schema==='fdmgen/orient-evidence@0.1');
  if(manifests.length!==1)throw Error('Select one orient-evidence manifest, its enriched table and all listed receipt files together.');
  const manifest=manifests[0].value,tableRef=manifest.enriched_table;
  if(!hash(manifest.table?.input_sha256)||!hash(manifest.table?.root_sha256)||!name(tableRef?.path)||!hash(tableRef.sha256))throw Error('Manifest table identities are incomplete.');
  if(!Array.isArray(manifest.slices)||!manifest.slices.length||!Array.isArray(manifest.receipts)||manifest.receipts.length!==2*manifest.slices.length)throw Error('Each pose needs one slice and two check receipts.');
  const slices=new Map();
  for(const s of manifest.slices){
   if(typeof s.pose!=='string'||!s.pose||slices.has(s.pose)||!['project','shell-only'].includes(s.slice_kind)||!hash(s.gcode_sha256))throw Error('Unknown slice kind, invalid hash or duplicate pose.');
   slices.set(s.pose,s);
  }
  const paths=new Set([tableRef.path]),roles=new Set();
  for(const e of manifest.receipts){
   const s=slices.get(e.pose),role=e.pose+'/'+e.check;
   if(!s||!['shell-check','bridge-check'].includes(e.check)||roles.has(role)||s.slice_kind!==e.slice_kind||s.gcode_sha256!==e.gcode_sha256)throw Error('Receipt role does not match a unique declared pose and slice.');
   if(!name(e.path)||paths.has(e.path)||!hash(e.sha256))throw Error('Receipts need unique filenames and valid fingerprints.');
   roles.add(role);paths.add(e.path);
  }
  const missing=[...paths].filter(p=>!entries.has(p));
  if(missing.length)throw Error('Missing orientation evidence files: '+missing.join(', ')+'. Select the complete set together.');
  const tableFile=entries.get(tableRef.path),table=tableFile.value;
  if(tableFile.sha!==tableRef.sha256)throw Error('Enriched table fingerprint differs.');
  if(!hash(table.mesh?.sha256)||table.enriched?.from_table_sha256!==manifest.table.root_sha256||!Array.isArray(table.candidates))throw Error('Enriched table root or mesh identity is invalid.');
  const candidates=new Map();
  for(const c of table.candidates){if(typeof c.id!=='string'||candidates.has(c.id)||!Array.isArray(c.R_design_to_print)||c.R_design_to_print.length!==3||!c.R_design_to_print.every(row=>vector(row,3))||!vector(c.t_mm,3))throw Error('Enriched table has duplicate or invalid poses.');candidates.set(c.id,c);}
  const receipts=[];
  for(const e of manifest.receipts){
   const file=entries.get(e.path),r=file.value,c=candidates.get(e.pose),rule=e.check==='shell-check'?'SHELL-001':'BRG-001';
   const schema=e.check==='shell-check'?'fdmgen/shell-check@0.3':'fdmgen/bridge-check@0.2';
   if(file.sha!==e.sha256)throw Error('Receipt fingerprint differs: '+e.path);
   if(e.schema!==schema||r.schema!==schema||!c||r.pose?.id!==e.pose||!same(r.pose.R_design_to_print,c.R_design_to_print)||!same(r.pose.t_mm,c.t_mm))throw Error('Receipt schema or pose differs: '+e.path);
   if(r.gcode?.gcode_sha256!==e.gcode_sha256||r.table?.sha256!==manifest.table.root_sha256||r.mesh?.sha256!==table.mesh.sha256)throw Error('Receipt G-code, root table or mesh differs: '+e.path);
   if(r.result?.rule!==rule||r.result.level!=='T'||!verdicts.includes(r.result.verdict)||r.result.verdict!==e.verdict||typeof r.result.provisional!=='boolean')throw Error('Receipt rule or verdict differs: '+e.path);
   if(!r.source_sha256||!Object.keys(r.source_sha256).length||!Object.values(r.source_sha256).every(hash))throw Error('Receipt source fingerprints are missing or invalid.');
   placement(r.placement);
   const m=r.result.metrics;
   if(e.check==='shell-check'){
    if(!finite(m?.thin_fraction)||m.thin_fraction>1||!Number.isInteger(m.samples)||m.samples<=0||!Number.isInteger(m.unmeasured)||m.unmeasured<0||!Number.isInteger(r.method?.surface_samples)||m.samples+m.unmeasured!==r.method.surface_samples||!finite(r.grid?.clipped_outside_grid_mm3))throw Error('Invalid shell sample accounting.');
    const col=column(c,r,e,'t_shell_thin_fraction',m.thin_fraction,'fraction',e.verdict);
    if(!same(col.coverage,{samples_requested:r.method.surface_samples,measured:m.samples,unmeasured:m.unmeasured,clipped_outside_grid_mm3:r.grid.clipped_outside_grid_mm3})||!same(col.pose_evidence,{verified:r.placement.verified,bands:r.placement.bands}))throw Error('Enriched shell coverage or pose evidence differs.');
   }else{
    for(const side of ['external','internal']){
     const key='max_span_'+side+'_mm',value=m?.[key],limit=r.method?.[key];
     if(!finite(value)||!Number.isFinite(limit)||limit<=0)throw Error('Invalid bridge span or limit.');
     const col=column(c,r,e,'t_bridge_span_'+side+'_mm',value,'mm',value>limit?'FAIL':'PASS');
     if(col.limit_mm!==limit||col.receipt.overall_verdict!==e.verdict)throw Error('Enriched bridge limit or overall verdict differs.');
     const ceiling=m['max_ceiling_span_'+side+'_mm'];
     if(col.ceiling_span_mm!==ceiling||(ceiling!==undefined&&!finite(ceiling)))throw Error('Enriched bridge ceiling span differs.');
     const coverage=Object.fromEntries(['bridge_roads','external_roads','internal_roads','max_cantilever_mm','bridge_layers_z_mm'].map(k=>[k,m[k]]));coverage.cell_mm=r.method.cell_mm;
     if(!same(col.coverage,coverage))throw Error('Enriched bridge coverage differs.');
    }
   }
   receipts.push({entry:e,receipt:r});
  }
  return {manifest,manifestHash:manifests[0].sha,table,tableBytes:tableFile.bytes,tableHash:tableFile.sha,receipts};
 }
 const api={load,digest};if(typeof module==='object')module.exports=api;else root.OrientBundle=api;
})(globalThis);
