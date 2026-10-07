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
 return {draft,pair};
})();
if(typeof module!=='undefined')module.exports=MassingReview;
