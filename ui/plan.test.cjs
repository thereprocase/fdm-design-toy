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
test('declared keep-out references round-trip and unknown ids are rejected',()=>{
 const table={...analysis,keep_outs:[{id:'moulding'},{id:'slide'}]};
 const helper={...input.helper_regions[0],keep_clear:{note:'Retain assembly access',interface_ids:[],keep_out_ids:['moulding','slide']}};
 const draft=Plan.create(table,hash,candidate,{...input,helper_regions:[helper]});
 assert.deepEqual(Plan.restore(draft,table,hash).input.helper_regions[0].keep_clear.keep_out_ids,['moulding','slide']);
 assert.throws(()=>Plan.restore(draft,analysis,hash),/Unknown keep-out/);
});

test('proposal provenance survives edited drafts as independent historical data',()=>{
 const proposal={generator:'fdmgen.massing.seed',status:'helpers_proposed',stress:{sha256:'c'.repeat(64)},accepted:[{id:'h1',F_L_max:.1}],future:{keep:'additive field'}};
 const draft=Plan.create(analysis,hash,candidate,{...input,proposal});
 const restored=Plan.restore(draft,analysis,hash);
 restored.input.helper_regions[0].name='Revised helper';restored.input.walls=6;
 const edited=Plan.create(analysis,hash,candidate,restored.input);
 assert.deepEqual(edited.proposal,proposal);assert.equal(edited.proposal_use,'historical_provenance_requires_recheck');
 assert.equal(edited.massing.walls,6);assert.equal(edited.massing.helper_regions[0].name,'Revised helper');
 edited.proposal.accepted[0].F_L_max=7;assert.equal(draft.proposal.accepted[0].F_L_max,.1);
 assert.equal(Plan.create(analysis,hash,candidate,input).proposal,undefined);
 assert.throws(()=>Plan.restore({...draft,proposal:[]},analysis,hash),/generator/);
});

test('download filenames identify part and pose without changing the draft',()=>{
 const draft=Plan.create(analysis,hash,candidate,input),before=JSON.stringify(draft);
 assert.equal(Plan.filename(draft),'test-pose-massing-plan.json');
 assert.equal(JSON.stringify(draft),before);
 assert.equal(Plan.filename({source:{problem:{id:'Spool Rack G2'}},orientation:{id:'facet-00'}}),'spool-rack-g2-facet-00-massing-plan.json');
 assert.equal(Plan.filename({source:{problem:'../../My: Part'},orientation:{id:'../Pose / 2'}}),'my-part-pose-2-massing-plan.json');
 assert.equal(Plan.filename(null),'part-pose-massing-plan.json');
 assert.equal(Plan.filename({source:{problem:42},orientation:{id:'...'}}),'part-pose-massing-plan.json');
 const long=Plan.filename({source:{problem:'x'.repeat(1000)},orientation:{id:'y'.repeat(1000)}});
 assert.equal(long,`${'x'.repeat(64)}-${'y'.repeat(64)}-massing-plan.json`);
});
