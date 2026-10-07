'use strict';
const CouponEvidence=(()=>{
 function plate(value){
  if(value?.schema!=='fdmgen/coupon-plate@0.1'||value.frame!=='print'||value.units!=='mm'||!Array.isArray(value.rungs)||!value.rungs.length)throw Error('Expected a print-frame coupon plate in millimetres.');
  const ids=new Set();
  for(const r of value.rungs){if(typeof r.id!=='string'||ids.has(r.id)||!['overhang','bridge'].includes(r.kind))throw Error('Plate rung IDs must be unique with a known kind.');ids.add(r.id);if(!Number.isFinite(r.kind==='overhang'?r.alpha_deg:r.span_mm))throw Error(`Missing rung dimension: ${r.id}`);
   if(!Array.isArray(r.bbox_mm)||r.bbox_mm.length!==2||r.bbox_mm.some(p=>!Array.isArray(p)||p.length!==3||!p.every(Number.isFinite))||r.bbox_mm[0].some((x,i)=>x>=r.bbox_mm[1][i]))throw Error(`Invalid bounding box: ${r.id}`);
  }return value;
 }
 function pair(p,hash,r){
  plate(p);
  if(r?.schema!=='fdmgen/slice-evidence@0.1'||r.tier!=='S')throw Error('Expected an S-tier slice-evidence receipt.');
  if(!/^[a-f0-9]{64}$/.test(hash)||r.plate?.sha256!==hash||r.plate?.schema!==p.schema)throw Error('Receipt does not match this plate fingerprint.');
  if(!r.gcode?.settings||typeof r.gcode.settings!=='object'||Array.isArray(r.gcode.settings)||!Array.isArray(r.rungs))throw Error('Receipt must include slicer settings and rung results.');
  if(!/^[a-f0-9]{64}$/.test(r.gcode.sha256||''))throw Error('Receipt needs a recorded G-code fingerprint.');
  const expected=new Map(p.rungs.map(x=>[x.id,x.kind])),seen=new Set();
  for(const x of r.rungs){if(seen.has(x.id)||expected.get(x.id)!==x.kind)throw Error(`Unexpected or duplicate rung: ${x.id}`);seen.add(x.id);const source=p.rungs.find(y=>y.id===x.id),dimension=x.kind==='overhang'?'alpha_deg':'span_mm';if(!Number.isFinite(x[dimension])||Math.abs(x[dimension]-source[dimension])>1e-8)throw Error(`Rung dimensions differ: ${x.id}`);if(!Number.isInteger(x.support_segments))throw Error(`Invalid segment count: ${x.id}`);
   for(const k of ['support_segments','support_length_mm','support_volume_mm3'])if(!Number.isFinite(x[k])||x[k]<0)throw Error(`Invalid ${k} for ${x.id}`);
  }
  if(seen.size!==expected.size)throw Error('Receipt is missing plate rungs.');
  return r;
 }
 function supportLabel(settings){const v=String(settings.enable_support??'').toLowerCase();return ['1','true'].includes(v)?'Support enabled':['0','false'].includes(v)?'Support disabled':'Support setting not recorded';}
 return {plate,pair,supportLabel};
})();
if(typeof module!=='undefined')module.exports=CouponEvidence;
