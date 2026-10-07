const test=require('node:test'),assert=require('node:assert/strict'),Plan=require('./plan.js');
const hash='a'.repeat(64),candidate={id:'pose',columns:{F_L_max:{value:.4}}},analysis={schema:'fdmgen/orientation-table@0.1',problem:'test',mesh:{sha256:'b'.repeat(64)},candidates:[candidate]};
const input={walls:4,skin_mm:1.6,rationale:'Protect loaded interfaces',shell_only:false,helper_regions:[{id:'h1',name:'Seat rib',location:'Under rear seat',purpose:'Carry seat load into wall plate',keep_clear:'Rod bore and screw washer seats'}]};
test('structured planning draft round-trips without changing intent',()=>{
 const draft=Plan.create(analysis,hash,candidate,input), restored=Plan.restore(JSON.parse(JSON.stringify(draft)),analysis,hash);
 assert.deepEqual(Plan.create(analysis,hash,restored.candidate,restored.input),draft);
 assert.equal(draft.massing.sparse_infill_structural_credit,false);
 assert.equal(draft.massing.helper_regions[0].geometry_status,'not_created');
});
test('reopen rejects a different table and takes evidence from current table',()=>{
 const draft=Plan.create(analysis,hash,candidate,input);assert.throws(()=>Plan.restore(draft,analysis,'c'.repeat(64)),/different orientation table/);
 draft.orientation={...draft.orientation,columns:{F_L_max:{value:0}}};
 assert.equal(Plan.restore(draft,analysis,hash).candidate.columns.F_L_max.value,.4);
});
test('shell-only baseline is explicit and does not export stale helper intent',()=>{
 const draft=Plan.create(analysis,hash,candidate,{...input,shell_only:true});assert.deepEqual(draft.massing.helper_regions,[]);assert.equal(draft.massing.shell_only,true);
});
test('incomplete helper or inconsistent credit settings fail',()=>{
 assert.throws(()=>Plan.create(analysis,hash,candidate,{...input,helper_regions:[{...input.helper_regions[0],keep_clear:''}]}),/constraints/);
 const draft=Plan.create(analysis,hash,candidate,input);draft.massing.sparse_infill_structural_credit=true;assert.throws(()=>Plan.restore(draft,analysis,hash),/no sparse-infill/);
});
test('legacy notes are retained for explicit completion',()=>{
 const draft=Plan.create(analysis,hash,candidate,input);draft.schema='fdmgen.massing-plan.v0.1';draft.massing.helper_intent='Existing rib notes';
 const result=Plan.restore(draft,analysis,hash);assert.equal(result.migrated,true);assert.equal(result.input.helper_regions[0].purpose,'Existing rib notes');assert.equal(result.input.helper_regions[0].location,'');
});
