/* Planning intent only: no helper geometry, structural credit or qualification inferred. */
'use strict';
const Plan = (() => {
  const schema='fdmgen.massing-plan.v0.3';
  const requireText=(value,label)=>{if(typeof value!=='string'||!value.trim())throw Error(`${label} is required.`);return value.trim();};
  function shell(walls,skin) {
    if(!Number.isInteger(walls)||walls<1||walls>20)throw Error('Choose 1–20 perimeter walls.');
    if(!Number.isFinite(skin)||skin<.1||skin>20)throw Error('Choose a skin thickness from 0.1 to 20 mm.');
  }
  function geometry(value) {
    if(value==null)return null;
    if(value.type!=='box'||value.frame!=='design')throw Error('Helper regions must be boxes in the design frame.');
    for(const key of ['center_mm','size_mm'])if(!Array.isArray(value[key])||value[key].length!==3||!value[key].every(Number.isFinite))throw Error('Region centre and size need three finite millimetre values.');
    if(value.size_mm.some(x=>x<=0))throw Error('Region sizes must be positive.');
    return {type:'box',frame:'design',center_mm:[...value.center_mm],size_mm:[...value.size_mm]};
  }
  function boxSeparation(a,b,minimum=.84) {
    geometry(a);geometry(b);
    const overlap=[0,1,2].map(k=>Math.min(a.center_mm[k]+a.size_mm[k]/2,b.center_mm[k]+b.size_mm[k]/2)-Math.max(a.center_mm[k]-a.size_mm[k]/2,b.center_mm[k]-b.size_mm[k]/2));
    const gap=Math.hypot(...overlap.map(x=>Math.max(0,-x)));
    return {gap_mm:gap,overlap_mm:overlap,needs_review:gap===0?Math.min(...overlap)<minimum:gap<minimum};
  }
  function keepClear(value,interfaces=[],keepOuts=[]) {
    const v=typeof value==='string'?{note:value}:value;
    if(!v||!Array.isArray(v.interface_ids||[])||!Array.isArray(v.keep_out_ids||[]))throw Error('Invalid keep-clear references.');
    const allowed=new Set(interfaces.map(i=>i.id));
    for(const id of v.interface_ids||[])if(!allowed.has(id))throw Error(`Unknown interface: ${id}`);
    const allowedKeepOuts=new Set(keepOuts.map(k=>k.id));
    for(const id of v.keep_out_ids||[])if(!allowedKeepOuts.has(id))throw Error(`Unknown keep-out: ${id}`);
    if(v.clearance_mm!=null&&(!Number.isFinite(v.clearance_mm)||v.clearance_mm<0))throw Error('Clearance must be nonnegative millimetres.');
    return {interface_ids:[...new Set(v.interface_ids||[])],keep_out_ids:[...new Set(v.keep_out_ids||[])],clearance_mm:v.clearance_mm??null,note:requireText(v.note,'Interface constraints')};
  }
  function regions(values,shellOnly,interfaces=[],keepOuts=[]) {
    if(shellOnly)return [];
    if(!Array.isArray(values)||!values.length)throw Error('Add a helper region or choose shell only.');
    const ids=new Set();
    return values.map((r,i)=>{
      const id=typeof r.id==='string'&&r.id?r.id:`helper-${i+1}`;
      if(ids.has(id))throw Error('Helper identifiers must be unique.');ids.add(id);
      return {id,name:requireText(r.name,`Helper ${i+1} name`),location:requireText(r.location,`Helper ${i+1} location`),purpose:requireText(r.purpose,`Helper ${i+1} load purpose`),keep_clear:keepClear(r.keep_clear,interfaces,keepOuts),geometry:geometry(r.geometry),geometry_status:r.geometry?'sketch':'not_created'};
    });
  }
  function proposal(value) {
    if(value==null)return null;
    if(typeof value!=='object'||Array.isArray(value)||typeof value.generator!=='string'||!value.generator.trim())throw Error('Proposal provenance needs a generator.');
    // Preserve producer fields as historical data, never as current verification.
    return JSON.parse(JSON.stringify(value));
  }
  function create(analysis,hash,candidate,input) {
    if(!analysis?.candidates?.some(c=>c.id===candidate?.id))throw Error('Select a pose from the loaded analysis.');
    if(!/^[a-f0-9]{64}$/.test(hash||''))throw Error('The source table needs a valid fingerprint.');
    shell(input.walls,input.skin_mm);
    const rationale=requireText(input.rationale,'Choice rationale');
    const helperRegions=regions(input.helper_regions,input.shell_only===true,analysis.interfaces||[],analysis.keep_outs||[]);
    const current=analysis.candidates.find(c=>c.id===candidate.id);
    return {schema,status:'draft_requires_verification',...(input.proposal?{proposal:proposal(input.proposal),proposal_use:'historical_provenance_requires_recheck'}:{}),source:{orientation_table_sha256:hash,orientation_schema:analysis.schema,problem:analysis.problem,mesh:analysis.mesh},
      orientation:{...current,designer_decision:{choice:'selected_for_planning',candidate_id:current.id,table_sha256:hash,rank_at_decision:current.rank??null,decided_by_role:'designer',rationale}},
      massing:{body:'fixed',walls:input.walls,skin_mm:input.skin_mm,helper_infill_percent:100,sparse_infill_structural_credit:false,shell_only:input.shell_only===true,helper_regions:helperRegions},
      outstanding_checks:['Create and validate helper geometry where requested','Verify interfaces and helper bonding','Slice and check credited material and printability','Verify load cases and material evidence; physical testing remains separate']};
  }
  function restore(draft,analysis,hash) {
    if(!['fdmgen.massing-plan.v0.1','fdmgen.massing-plan.v0.2',schema].includes(draft?.schema))throw Error('Unsupported planning draft format.');
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
    else helperRegions=regions(helperRegions,m.shell_only===true,analysis.interfaces||[],analysis.keep_outs||[]);
    return {candidate,input:{walls:m.walls,skin_mm:m.skin_mm,rationale:requireText(draft.orientation?.designer_decision?.rationale,'Choice rationale'),shell_only:m.shell_only===true,helper_regions:helperRegions,...(draft.proposal?{proposal:proposal(draft.proposal)}:{})},migrated};
  }
  function filename(draft) {
    const slug=(value,fallback)=>typeof value==='string'
      ?value.toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,64).replace(/^-+|-+$/g,'')||fallback:fallback;
    const problem=draft?.source?.problem;
    return `${slug(typeof problem==='string'?problem:problem?.id,'part')}-${slug(draft?.orientation?.id,'pose')}-massing-plan.json`;
  }
  function evidenceHandoff(draft,tableName) {
    const safe=value=>typeof value==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/.test(value);
    const problem=draft?.source?.problem,pose=draft?.orientation?.id;
    const known=safe(problem)&&safe(pose),stem=known?`${problem}-${pose}-massing`:'PART-POSE-massing';
    const table=/^orientation-table-[a-f0-9]{12}\.json$/.test(tableName)?tableName:'TABLE.json';
    return {project:`out/massing/${stem}.3mf`,baseline:`out/massing/${stem}-shell-only.3mf`,
      command:`fdmgen evidence out/massing/${stem}.json project.gcode shell-only.gcode --table ${table} --pose ${safe(pose)?pose:'POSE_ID'} --out out/evidence`,
      placeholders:!known};
  }
  return {schema,create,restore,geometry,boxSeparation,filename,evidenceHandoff};
})();
if(typeof module!=='undefined')module.exports=Plan;
