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
test('spatial box intent preserves the design frame across draft round-trip',()=>{
 const geometry={type:'box',frame:'design',center_mm:[90,12,3],size_mm:[10,8,6]};
 const draft=Plan.create(analysis,hash,candidate,{...input,helper_regions:[{...input.helper_regions[0],geometry}]});
 const restored=Plan.restore(draft,analysis,hash);
 assert.deepEqual(restored.input.helper_regions[0].geometry,geometry);
 assert.equal(restored.input.helper_regions[0].geometry_status,'sketch');
 assert.throws(()=>Plan.geometry({...geometry,size_mm:[0,8,6]}),/positive/);
 assert.throws(()=>Plan.geometry({...geometry,frame:'print'}),/design frame/);
});
test('keep-clear interface references are validated by the current table',()=>{
 const withInterfaces={...analysis,interfaces:[{id:'seat'}]};
 const helper={...input.helper_regions[0],keep_clear:{interface_ids:['seat'],clearance_mm:.5,note:'Maintain assembly clearance'}};
 const draft=Plan.create(withInterfaces,hash,candidate,{...input,helper_regions:[helper]});
 assert.deepEqual(draft.massing.helper_regions[0].keep_clear.interface_ids,['seat']);
 assert.throws(()=>Plan.restore(draft,analysis,hash),/Unknown interface: seat/);
});
test('nominal overlap-or-gap screen flags touching/sliver boxes only',()=>{
 const box=x=>({type:'box',frame:'design',center_mm:[x,0,0],size_mm:[2,2,2]});
 assert.equal(Plan.boxSeparation(box(0),box(3)).needs_review,false); // 1 mm gap
 assert.equal(Plan.boxSeparation(box(0),box(2.5)).needs_review,true); // .5 mm gap
 assert.equal(Plan.boxSeparation(box(0),box(2)).needs_review,true); // only touching
 assert.equal(Plan.boxSeparation(box(0),box(1.5)).needs_review,true); // .5 mm overlap
 assert.equal(Plan.boxSeparation(box(0),box(1)).needs_review,false); // 1 mm overlap
});
