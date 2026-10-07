/* Planning intent only: no helper geometry, structural credit or qualification inferred. */
'use strict';
const Plan = (() => {
  const schema='fdmgen.massing-plan.v0.2';
  const requireText=(value,label)=>{if(typeof value!=='string'||!value.trim())throw Error(`${label} is required.`);return value.trim();};
  function shell(walls,skin) {
    if(!Number.isInteger(walls)||walls<1||walls>20)throw Error('Choose 1–20 perimeter walls.');
    if(!Number.isFinite(skin)||skin<.1||skin>20)throw Error('Choose a skin thickness from 0.1 to 20 mm.');
  }
  function regions(values,shellOnly) {
    if(shellOnly)return [];
    if(!Array.isArray(values)||!values.length)throw Error('Add a helper region or choose shell only.');
    const ids=new Set();
    return values.map((r,i)=>{
      const id=typeof r.id==='string'&&r.id?r.id:`helper-${i+1}`;
      if(ids.has(id))throw Error('Helper identifiers must be unique.');ids.add(id);
      return {id,name:requireText(r.name,`Helper ${i+1} name`),location:requireText(r.location,`Helper ${i+1} location`),purpose:requireText(r.purpose,`Helper ${i+1} load purpose`),keep_clear:requireText(r.keep_clear,`Helper ${i+1} interface constraints`),geometry_status:'not_created'};
    });
  }
  function create(analysis,hash,candidate,input) {
    if(!analysis?.candidates?.some(c=>c.id===candidate?.id))throw Error('Select a pose from the loaded analysis.');
    if(!/^[a-f0-9]{64}$/.test(hash||''))throw Error('The source table needs a valid fingerprint.');
    shell(input.walls,input.skin_mm);
    const rationale=requireText(input.rationale,'Choice rationale');
    const helperRegions=regions(input.helper_regions,input.shell_only===true);
    const current=analysis.candidates.find(c=>c.id===candidate.id);
    return {schema,status:'draft_requires_verification',source:{orientation_table_sha256:hash,orientation_schema:analysis.schema,problem:analysis.problem,mesh:analysis.mesh},
      orientation:{...current,designer_decision:{choice:'selected_for_planning',rationale}},
      massing:{body:'fixed',walls:input.walls,skin_mm:input.skin_mm,helper_infill_percent:100,sparse_infill_structural_credit:false,shell_only:input.shell_only===true,helper_regions:helperRegions},
      outstanding_checks:['Create and validate helper geometry where requested','Verify interfaces and helper bonding','Slice and check credited material and printability','Verify load cases and material evidence; physical testing remains separate']};
  }
  function restore(draft,analysis,hash) {
    if(!['fdmgen.massing-plan.v0.1',schema].includes(draft?.schema))throw Error('Unsupported planning draft format.');
    if(!analysis)throw Error('Load the source orientation table before opening its draft.');
    if(draft.source?.orientation_table_sha256!==hash)throw Error('This draft belongs to a different orientation table. Load its original table first.');
    const candidate=analysis.candidates.find(c=>c.id===draft.orientation?.id);
    if(!candidate)throw Error('The selected pose is missing from this table.');
    const m=draft.massing;
    if(!m || m.body!=='fixed'||m.helper_infill_percent!==100||m.sparse_infill_structural_credit!==false)throw Error('This workspace requires a fixed body, 100% helpers and no sparse-infill structural credit.');
    shell(m.walls,m.skin_mm);
    let helperRegions=m.helper_regions;
    const migrated=draft.schema==='fdmgen.massing-plan.v0.1';
    if(migrated)helperRegions=[{id:'helper-1',name:'Imported helper intent',location:'',purpose:requireText(m.helper_intent,'Legacy helper intent'),keep_clear:'',geometry_status:'not_created'}];
    else helperRegions=regions(helperRegions,m.shell_only===true);
    return {candidate,input:{walls:m.walls,skin_mm:m.skin_mm,rationale:requireText(draft.orientation?.designer_decision?.rationale,'Choice rationale'),shell_only:m.shell_only===true,helper_regions:helperRegions},migrated};
  }
  return {schema,create,restore};
})();
if(typeof module!=='undefined')module.exports=Plan;
