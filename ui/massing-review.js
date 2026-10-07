'use strict';
const el=id=>document.getElementById(id);
let saved=null,digest=null,generation=0,receiptGeneration=0;
function add(tag,value,parent){const n=document.createElement(tag);n.textContent=value;parent.append(n);return n;}
el('review-draft').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;const request=++generation;++receiptGeneration;
 // Clear old results immediately, so they cannot be mistaken for this revision.
 saved=null;digest=null;el('review-workspace').hidden=true;el('review-receipt').disabled=true;el('review-receipt').value='';
 try{const raw=await file.arrayBuffer(),d=MassingReview.draft(JSON.parse(new TextDecoder().decode(raw))),h=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),b=>b.toString(16).padStart(2,'0')).join('');if(request!==generation)return;saved=d;digest=h;el('review-receipt').disabled=false;el('review-status').textContent='Draft loaded. Open its matching export receipt.';}catch(err){if(request===generation)el('review-status').textContent=err.message;}
};
el('review-receipt').onchange=async e=>{
 const file=e.target.files[0];if(!file||!saved)return;const request=++receiptGeneration,current=generation;
 try{const r=MassingReview.pair(saved,digest,JSON.parse(await file.text()));if(current!==generation||request!==receiptGeneration)return;render(r);el('review-status').textContent='Receipt fingerprint matched this saved draft.';}catch(err){if(current===generation&&request===receiptGeneration)el('review-status').textContent=err.message+' Previous matched results, if any, remain below.';}
};
function render(r){
 el('review-workspace').hidden=false;el('review-title').textContent=`${r.plan.problem} · ${r.plan.candidate_id}`;
 el('review-context').textContent=r.capability_context_matches_template?'Template fingerprint matches the capability context. This does not validate every changed value or combination.':'Template differs from the measured capability context. Helper settings are unverified for this profile.';
 if(r.warning)el('review-context').textContent+=' '+r.warning;
 el('review-scope').textContent=`${r.establishes||''} Does not establish: ${r.does_not_establish||'printed performance or strength.'}`;
 const failed=r.checks.filter(c=>c.verdict==='FAIL').length,unchecked=r.checks.filter(c=>c.verdict==='NOT_CHECKED').length;
 el('review-count').textContent=r.checks.length?`${failed} failed checks; ${unchecked} not checked. Passing checks apply only to the stated method and evidence level.`:'No helper checks reported; this is not a checked result.';
 el('review-checks').replaceChildren();
 const names=new Map(saved.massing.helper_regions.map(h=>[h.id,h.name]));
 for(const c of r.checks){const row=add('article','',el('review-checks'));add('h3',`${c.rule} · ${c.level} · ${c.verdict}${c.provisional?' · provisional':''}`,row);let message=c.message;for(const [id,name]of names)message=message.split(id).join(`${name} [${id}]`);add('p',message,row);const fixes=add('ul','',row);for(const fix of c.fixes)add('li',fix,fixes);if(c.establishes)add('p',c.establishes,row);if(c.does_not_establish)add('p','Does not establish: '+c.does_not_establish,row);const details=add('details','',row);add('summary','Measurements',details);add('pre',JSON.stringify(c.metrics||{},null,2),details);}
 el('review-helpers').replaceChildren();
 for(const h of r.helpers){const planned=saved.massing.helper_regions.find(p=>p.id===h.id),row=add('article','',el('review-helpers'));add('h3',planned.name,row);add('p',`Helper ID: ${h.id}`,row);add('p',planned.purpose||'',row);add('pre',JSON.stringify({design_box:planned.geometry,exported_settings:h.settings,print_bbox_mm:h.print_bbox_mm},null,2),row);}
 if(!r.helpers.length)add('p','Shell-only draft; no helpers.',el('review-helpers'));
 el('review-setting-evidence').textContent=r.settings_evidence?JSON.stringify(r.settings_evidence,null,2):'Per-value setting evidence was not recorded in this receipt.';
 el('review-settings').textContent=JSON.stringify(r.object_settings,null,2);el('review-skin').textContent=r.skin_note||'';el('review-provenance').textContent=JSON.stringify(r,null,2);
}
