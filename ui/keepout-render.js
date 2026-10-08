/* Optional, table-pinned design-frame geometry. This is visualization, not a clearance check. */
'use strict';
const KeepoutRender=(()=>{
 const vector=(v,n=3)=>Array.isArray(v)&&v.length===n&&v.every(Number.isFinite);
 const bounds=(lo,hi)=>vector(lo)&&vector(hi)&&lo.every((x,i)=>x<hi[i]);
 const hash=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
 function validate(g,table,tableHash){
  const fail=message=>{throw Error(message);};
  if(g?.schema!=='fdmgen/keepout-render@0.1')fail('Expected keepout-render@0.1 geometry.');
  if(!hash(tableHash)||g.table?.sha256!==tableHash)fail('Keep-out geometry belongs to different table bytes.');
  if(!hash(g.mesh?.sha256)||g.mesh.sha256!==table?.mesh?.sha256)fail('Keep-out geometry mesh fingerprint does not match the table.');
  if(g.units!=='mm'||g.frame!=='design')fail('Keep-out geometry must declare design-frame millimetres.');
  const t=g.installed_to_design;
  if(!Array.isArray(t?.R)||t.R.length!==3||!t.R.every((row,i)=>vector(row)&&row.every((x,j)=>x===(i===j?1:0)))||!vector(t.t_mm)||t.t_mm.some(x=>x!==0)||typeof t.source!=='string'||!t.source||g.problem?.frames?.design!=='installed'||!hash(g.problem?.sha256))fail('This preview requires the recorded installed-to-design identity and problem provenance.');
  if(!Array.isArray(g.clip?.bbox_mm)||g.clip.bbox_mm.length!==2||!bounds(...g.clip.bbox_mm)||!Number.isFinite(g.clip.margin_mm)||g.clip.margin_mm<0||typeof g.scope!=='string'||!g.scope)fail('Keep-out geometry needs finite render clipping bounds and scope.');
  if(!Array.isArray(g.items))fail('Keep-out geometry needs an items list.');
  const declared=new Map((table.keep_outs||[]).map(x=>[x.id,x])),seen=new Set();
  for(const item of g.items){
   const declaration=declared.get(item?.id);
   if(!declaration||seen.has(item.id)||item.type!==declaration.type||item.rule!==declaration.rule)fail('Keep-out items must match unique table declarations and rule text.');
   seen.add(item.id);
   if(item.rendered===false){if(typeof item.reason!=='string'||!item.reason)fail('An undrawn keep-out needs a reason.');continue;}
   if(item.rendered!==true||!Array.isArray(item.unbounded)||!item.unbounded.every(x=>['min_x','min_y','min_z','max_x','max_y','max_z'].includes(x)))fail('Keep-out render status or unbounded axes are invalid.');
   if(item.type==='box'){
    if(!bounds(item.min_mm,item.max_mm)||!item.original||JSON.stringify(item.original.min_mm)!==JSON.stringify(declaration.min_mm)||JSON.stringify(item.original.max_mm)!==JSON.stringify(declaration.max_mm))fail('Keep-out box bounds or original declaration are invalid.');
   }else if(item.type==='flange_sweep'){
    if(item.axis!=='Z'||!Number.isFinite(item.z_min_mm)||!Number.isFinite(item.z_max_mm)||item.z_min_mm>=item.z_max_mm||!Array.isArray(item.discs)||!item.discs.length||item.discs.length>1000||!item.discs.every(d=>vector(d.centre_xy_mm,2)&&Number.isFinite(d.radius_mm)&&d.radius_mm>0)||!item.method||item.coverage?.discs!==item.discs.length||typeof item.coverage.note!=='string')fail('Keep-out sweep needs finite discs, Z bounds and sampling coverage.');
   }else fail('Unsupported rendered keep-out type.');
  }
  if(seen.size!==declared.size)fail('Keep-out geometry omits table declarations.');
  return g;
 }
 function segments(item){
  if(!item.rendered)return [];
  const lines=[];
  if(item.type==='box'){
   const p=Array.from({length:8},(_,i)=>item.min_mm.map((v,a)=>(i>>a)&1?item.max_mm[a]:v));
   for(let i=0;i<8;i++)for(let a=0;a<3;a++){const j=i^(1<<a);if(j>i)lines.push([p[i],p[j]]);}
  }else{
   for(const d of item.discs){
    const point=(k,z)=>[d.centre_xy_mm[0]+d.radius_mm*Math.cos(k*Math.PI/32),d.centre_xy_mm[1]+d.radius_mm*Math.sin(k*Math.PI/32),z];
    for(const z of [item.z_min_mm,item.z_max_mm])for(let k=0;k<64;k++)lines.push([point(k,z),point(k+1,z)]);
    for(let k=0;k<64;k+=16)lines.push([point(k,item.z_min_mm),point(k,item.z_max_mm)]);
   }
  }
  return lines;
 }
 return {validate,segments};
})();
if(typeof module!=='undefined')module.exports=KeepoutRender;
