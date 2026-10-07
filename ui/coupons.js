'use strict';
const el=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg';
let plate=null,plateHash=null,receipts=[],active=0,selected=null,generation=0,receiptRequest=0;
function add(tag,value,parent){const n=document.createElement(tag);n.textContent=value;parent.append(n);return n;}
const num=value=>Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:2}):'Not recorded';
function details(list,items){list.replaceChildren();for(const [k,v] of items){add('dt',k,list);add('dd',String(v??'Not recorded'),list);}}
function choose(id){selected=id;render();}
function render(){
 const r=receipts[active];el('coupon-workspace').hidden=!r;if(!r)return;
 const settings=r.gcode.settings,label=CouponEvidence.supportLabel(settings);
 el('receipt-note').textContent=label==='Support disabled'?'Support disabled: zero roads is not an unsupported-print result.':`${label} · threshold ${settings.support_threshold_angle??'not recorded'}° · slicer evidence (S tier)`;
 el('evidence-scope').textContent=[r.establishes,r.does_not_establish,`Unassigned support segments: ${r.unassigned_support_segments??'not recorded'}.`].filter(Boolean).join(' ');
 details(el('slicer-settings'),[['Slicer',`${r.gcode.generator??''} ${r.gcode.version??''}`],['Support',label],['Support threshold',`${settings.support_threshold_angle??'Not recorded'}°`],['Support type',settings.support_type],['Bridge-no-support setting',settings.bridge_no_support],['Layer height, mm',settings.layer_height],['Material profile',settings.filament_settings_id],['Print profile',settings.print_settings_id],['Printer',settings.printer_model]]);
 el('receipt-provenance').textContent=JSON.stringify({plate:r.plate,gcode:r.gcode,placement:r.placement},null,2);
 const result=r.rungs.find(x=>x.id===selected)||r.rungs[0];selected=result.id;const rung=plate.rungs.find(x=>x.id===selected);
 el('rung-title').textContent=`${rung.id} · ${rung.kind==='overhang'?rung.alpha_deg+'° overhang':rung.span_mm+' mm bridge'}`;
 details(el('rung-metrics'),[['Support segments',num(result.support_segments)],['Support length, mm',num(result.support_length_mm)],['Support volume, mm³',num(result.support_volume_mm3)],...(rung.kind==='bridge'?[['Bridge roads at first deck layer',num(result.bridge_roads_first_deck_layer)],['Longest bridge road, mm',num(result.longest_bridge_road_mm)]]:[])]);
 const map=el('rung-map');map.replaceChildren();const lo=[0,1].map(a=>Math.min(...plate.rungs.map(x=>x.bbox_mm[0][a]))),hi=[0,1].map(a=>Math.max(...plate.rungs.map(x=>x.bbox_mm[1][a])));
 map.setAttribute('viewBox',`${lo[0]-6} ${-hi[1]-6} ${hi[0]-lo[0]+12} ${hi[1]-lo[1]+12}`);
 for(const x of plate.rungs){const value=r.rungs.find(z=>z.id===x.id),g=document.createElementNS(ns,'g'),rect=document.createElementNS(ns,'rect'),title=document.createElementNS(ns,'title');
  g.setAttribute('role','button');g.setAttribute('tabindex','0');g.setAttribute('aria-label',x.id);g.setAttribute('aria-pressed',String(x.id===selected));g.onclick=()=>choose(x.id);g.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();choose(x.id);map.querySelector(`[aria-label="${CSS.escape(x.id)}"]`)?.focus();}};
  for(const [k,v] of Object.entries({x:x.bbox_mm[0][0],y:-x.bbox_mm[1][1],width:x.bbox_mm[1][0]-x.bbox_mm[0][0],height:x.bbox_mm[1][1]-x.bbox_mm[0][1],fill:value.support_segments>0?'#cc824b':'#afbeb0',stroke:x.id===selected?'#223d30':'#718872','stroke-width':x.id===selected?1.2:.25}))rect.setAttribute(k,v);
  title.textContent=`${x.id}: ${value.support_segments} support segments`;const label=document.createElementNS(ns,'text');label.setAttribute('x',(x.bbox_mm[0][0]+x.bbox_mm[1][0])/2);label.setAttribute('y',-(x.bbox_mm[0][1]+x.bbox_mm[1][1])/2);label.setAttribute('font-size','3.2');label.setAttribute('text-anchor','middle');label.setAttribute('dominant-baseline','central');label.setAttribute('fill','#183525');label.textContent=x.id;g.append(rect,title,label);map.append(g);
 }
 el('comparison-head').replaceChildren();const head=add('tr','',el('comparison-head'));add('th','Rung',head);
 for(const x of receipts){const th=add('th',CouponEvidence.supportLabel(x.gcode.settings),head);add('div',`${x.gcode.generator} ${x.gcode.version} · threshold ${x.gcode.settings.support_threshold_angle??'?'}° · layer ${x.gcode.settings.layer_height??'?'} mm`,th).className='receipt-subtitle';const extra=add('details','',th);add('summary','Full settings',extra);add('pre',JSON.stringify(x.gcode.settings,null,2),extra);}
 el('comparison-rows').replaceChildren();
 for(const x of plate.rungs){const row=add('tr','',el('comparison-rows')),button=add('button',x.id,add('td','',row));button.type='button';button.onclick=()=>choose(x.id);
  for(const receipt of receipts){const v=receipt.rungs.find(z=>z.id===x.id);add('td',`${num(v.support_segments)} support segments${x.kind==='bridge'?'; '+num(v.bridge_roads_first_deck_layer)+' bridge roads':''}`,row);}
 }
}
el('plate-file').onchange=async event=>{const file=event.target.files[0];if(!file)return;const token=++generation;plate=null;receipts=[];el('coupon-workspace').hidden=true;el('receipt-files').disabled=true;
 try{const raw=await file.arrayBuffer(),parsed=CouponEvidence.plate(JSON.parse(new TextDecoder().decode(raw))),hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),x=>x.toString(16).padStart(2,'0')).join('');if(token!==generation)return;plate=parsed;plateHash=hash;selected=null;el('receipt-files').disabled=false;el('coupon-status').textContent=`Loaded ${plate.rungs.length} rungs. Add matching receipts.`;}catch(e){if(token===generation)el('coupon-status').textContent=e.message;}
};
el('receipt-files').onchange=async event=>{const token=generation,request=++receiptRequest,files=Array.from(event.target.files);if(!files.length)return;
 try{const pending=[];for(const file of files){const r=JSON.parse(await file.text());if(token!==generation||request!==receiptRequest)return;pending.push(CouponEvidence.pair(plate,plateHash,r));}receipts=pending;active=0;el('receipt-choice').replaceChildren();receipts.forEach((r,i)=>{const o=add('option',`${i+1}. ${CouponEvidence.supportLabel(r.gcode.settings)} · ${r.gcode.settings.print_settings_id??r.gcode.version}`,el('receipt-choice'));o.value=i;});el('coupon-status').textContent=`Paired ${receipts.length} receipts to the exact plate fingerprint. G-code hashes are recorded provenance; G-code files were not loaded here.`;render();}catch(e){if(token!==generation||request!==receiptRequest)return;el('coupon-status').textContent=`Could not pair receipts: ${e.message}${receipts.length?' Previous valid results remain displayed.':''}`;}
};
el('receipt-choice').onchange=()=>{active=Number(el('receipt-choice').value);render();};
