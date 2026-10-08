/* Table-pinned KEEP-CLEAR model geometry for viewing, never a clearance verdict. */
'use strict';
const InterfaceRender=(()=>{
 const vector=(v,n=3)=>Array.isArray(v)&&v.length===n&&v.every(Number.isFinite);
 const hash=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
 const planes={X:{indices:[1,2],key:'center_yz_mm'},Y:{indices:[0,2],key:'center_xz_mm'},Z:{indices:[0,1],key:'center_xy_mm'}};
 function validate(g,table,tableHash){
  const fail=message=>{throw Error(message);};
  if(g?.schema!=='fdmgen/interface-render@0.1')fail('Expected interface-render@0.1 geometry.');
  if(!hash(tableHash)||g.table?.sha256!==tableHash)fail('Interface geometry belongs to different table bytes.');
  if(!hash(g.mesh?.sha256)||g.mesh.sha256!==table?.mesh?.sha256)fail('Interface geometry mesh fingerprint does not match the table.');
  if(g.units!=='mm'||g.frame!=='design')fail('Interface geometry must declare design-frame millimetres.');
  const t=g.installed_to_design;
  if(!Array.isArray(t?.R)||t.R.length!==3||!t.R.every((row,i)=>vector(row)&&row.every((x,j)=>x===(i===j?1:0)))||!vector(t.t_mm)||t.t_mm.some(x=>x!==0)||typeof t.source!=='string'||!t.source||g.problem?.frames?.design!=='installed'||!hash(g.problem?.sha256))fail('Interface preview requires the recorded installed-to-design identity and problem provenance.');
  const bbox=g.clip?.bbox_mm;
  if(!Array.isArray(bbox)||bbox.length!==2||!bbox.every(v=>vector(v))||!bbox[0].every((x,i)=>x<bbox[1][i])||!Number.isFinite(g.clip.margin_mm)||g.clip.margin_mm<0||typeof g.clip.basis!=='string'||!g.clip.basis||typeof g.scope!=='string'||!g.scope)fail('Interface geometry needs finite drawing bounds and scope.');
  if(!Array.isArray(g.items))fail('Interface geometry needs an items list.');
  const declarations=new Map((table.interfaces||[]).map(x=>[x.id,x])),seen=new Set();
  for(const item of g.items){
   const d=declarations.get(item?.id);
   if(!d||seen.has(item.id)||item.type!==d.type)fail('Interface items must match unique table declarations.');
   seen.add(item.id);
   if(item.rendered===false){if(typeof item.reason!=='string'||!item.reason)fail('An undrawn interface needs a reason.');continue;}
   const plane=planes[item.axis],axis='XYZ'.indexOf(item.axis);
   if(item.rendered!==true||!plane||item.axis!==String(d.axis||'').toUpperCase()||(item.role??null)!==(d.role??null)||(item.support??null)!==(d.support??null))fail('Interface axis or declaration metadata does not match the table.');
   let radius,source;
   if(d.type==='rod_seat'&&Array.isArray(d.seat_radius_mm)&&d.seat_radius_mm.length&&d.seat_radius_mm.every(x=>Number.isFinite(x)&&x>0)){radius=Math.max(...d.seat_radius_mm);source={seat_radius_mm:d.seat_radius_mm};}
   else if(d.type==='screw_clearance'&&Number.isFinite(d.d_mm)&&d.d_mm>0){radius=d.d_mm/2;source={d_mm:d.d_mm};}
   else fail('Unsupported or invalid rendered interface radius.');
   if(!Number.isFinite(item.base_radius_mm)||item.base_radius_mm!==radius||typeof item.model!=='string'||!item.model||JSON.stringify(item.source_fields)!==JSON.stringify(source))fail('Interface radius or source fields do not match the table.');
   if(item.centre_plane?.key!==plane.key||!vector(item.centre_plane.value,2)||!vector(d[plane.key],2)||!item.centre_plane.value.every((v,k)=>v===d[plane.key][k]))fail('Interface centre does not match the table.');
   if(!vector(item.axis_start_mm)||!vector(item.axis_end_mm)||item.axis_start_mm[axis]!==bbox[0][axis]||item.axis_end_mm[axis]!==bbox[1][axis]||!plane.indices.every((k,j)=>item.axis_start_mm[k]===d[plane.key][j]&&item.axis_end_mm[k]===d[plane.key][j]))fail('Interface axis endpoints do not match the centre and drawing clip.');
   if(JSON.stringify(item.unbounded)!==JSON.stringify([`min_${item.axis.toLowerCase()}`,`max_${item.axis.toLowerCase()}`]))fail('Interface drawing must state its unbounded axis.');
  }
  if(seen.size!==declarations.size)fail('Interface geometry omits table declarations.');
  return g;
 }
 function segments(item){
  if(!item.rendered)return [];
  const plane=planes[item.axis],lines=[];
  const point=(k,end)=>{const p=[...end],angle=k*Math.PI/32;p[plane.indices[0]]+=item.base_radius_mm*Math.cos(angle);p[plane.indices[1]]+=item.base_radius_mm*Math.sin(angle);return p;};
  for(const end of [item.axis_start_mm,item.axis_end_mm])for(let k=0;k<64;k++)lines.push([point(k,end),point(k+1,end)]);
  for(let k=0;k<64;k+=16)lines.push([point(k,item.axis_start_mm),point(k,item.axis_end_mm)]);
  return lines;
 }
 return {validate,segments};
})();
if(typeof module!=='undefined')module.exports=InterfaceRender;
