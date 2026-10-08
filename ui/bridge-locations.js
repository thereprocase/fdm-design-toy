/* Optional road witnesses; call only after the parent bridge receipt is paired. */
(function(root){
 'use strict';
 const Pose=typeof module==='object'?require('./plan.js'):Plan;
 const vec=v=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite);
 const close=(a,b,tol=.002)=>Math.abs(a-b)<=tol;
 const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
 function locations(r,draft){
  const m=r.result?.metrics;
  if(!m||!Object.hasOwn(m,'worst'))return [];
  const fail=message=>{throw Error('Bridge locations withheld: '+message);};
  Pose.validatePose(draft.orientation);
  const pose=draft.orientation,R=pose.R_design_to_print,t=pose.t_mm;
  if(r.schema!=='fdmgen/bridge-check@0.2'||r.result.rule!=='BRG-001'||r.result.level!=='T')fail('unsupported receipt.');
  if(r.pose?.id!==pose.id||JSON.stringify(r.pose.R_design_to_print)!==JSON.stringify(R)||JSON.stringify(r.pose.t_mm)!==JSON.stringify(t)||r.mesh?.sha256!==draft.source.mesh.sha256||r.table?.sha256!==draft.source.orientation_table_sha256)fail('saved geometry or pose differs.');
  const shift=r.placement?.shift_xy_mm;
  if(!Array.isArray(shift)||shift.length!==2||!shift.every(Number.isFinite)||!m.worst||typeof m.worst!=='object')fail('missing frame placement.');
  const out=[];
  for(const role of ['external','internal'])for(const model of ['strand','ceiling']){
   const key=model==='strand'?`max_span_${role}_mm`:`max_ceiling_span_${role}_mm`,maximum=m[key],w=m.worst[role]?.[model];
   if(!Number.isFinite(maximum)||maximum<0)fail('invalid maximum.');
   if(w===null){if(maximum!==0)fail('positive maximum has no witness.');continue;}
   if(!w||!Number.isInteger(w.road_index)||w.road_index<0||typeof w.role!=='string'||w.role.toLowerCase().includes('internal')!==(role==='internal')||!Number.isFinite(w.z_mm)||!Number.isFinite(w.value_mm)||w.value_mm<=0||!close(w.value_mm,maximum,.001))fail('road identity or maximum differs.');
   const keys=model==='strand'?['road_start','road_end','run_start','run_end']:['road_start','road_end','witness'];
   for(const k of keys){
    const plate=w.plate_mm?.[k],print=w.print_mm?.[k],design=w.design_mm?.[k];
    if(!vec(plate)||!vec(print)||!vec(design))fail('missing finite XYZ coordinates.');
    if(!close(plate[2],w.z_mm))fail('road height differs.');
    for(let i=0;i<3;i++)if(!close(plate[i]-(i<2?shift[i]:0),print[i])||!close(R[i].reduce((sum,v,j)=>sum+v*design[j],t[i]),print[i]))fail('coordinate frames disagree.');
   }
   const p=w.print_mm,a=p.road_start,b=p.road_end,L=distance(a,b);
   if(L<=0)fail('empty road.');
   for(const key of keys.slice(2)){
    const u=p[key].reduce((sum,v,i)=>sum+(v-a[i])*(b[i]-a[i]),0)/(L*L);
    if(u<-.002/L||u>1+.002/L||distance(p[key],a.map((v,i)=>v+u*(b[i]-a[i])))>.002)fail('witness is outside the road.');
   }
   if(model==='strand'&&!close(distance(p.run_start,p.run_end),w.value_mm))fail('unsupported run length differs from the span.');
   out.push({id:role+'-'+model,role,model,road_index:w.road_index,value_mm:w.value_mm,source:w});
  }
  return out;
 }
 const api={locations};if(typeof module==='object')module.exports=api;else root.BridgeLocations=api;
})(globalThis);
