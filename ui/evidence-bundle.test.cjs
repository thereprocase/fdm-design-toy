const test=require('node:test'),assert=require('node:assert/strict'),Bundle=require('./evidence-bundle.js'),fixture=require('./evidence-bundle-fixture.cjs');
const inputs=f=>[{name:'evidence-bundle.json',buffer:Buffer.from(JSON.stringify(f.manifest))},...f.files].map(({name,buffer})=>({name,arrayBuffer:async()=>buffer}));
test('bundle atomically verifies five roles and matches the loaded export',async()=>{
 const f=fixture(),b=await Bundle.load(inputs(f),f.context);assert.equal(b.project.result.metrics.thin_fraction,.0022);assert.equal(b.bridges.baseline.result.metrics.max_span_internal_mm,122.1);
});
test('bundle refuses missing, duplicate, corrupt and cross-export files',async()=>{
 for(const mutate of [f=>f.files.pop(),f=>f.files.push(f.files[0]),f=>f.files[0].buffer=Buffer.from('{}'),f=>f.manifest.inputs.report_sha256='0'.repeat(64),f=>f.manifest.receipts[0].path='../outside.json',f=>f.manifest.receipts[1].slice_kind='project-other']){
  const f=fixture();mutate(f);await assert.rejects(Bundle.load(inputs(f),f.context));
 }
});
test('hash agreement alone cannot substitute wrong pose, slice or verdict',async()=>{
 for(const mutate of [r=>r.pose.t_mm[0]++,r=>r.gcode.gcode_sha256='0'.repeat(64),r=>r.placement.bands=[],r=>r.result.metrics.max_span_external_mm=-1]){
  const f=fixture(),r=JSON.parse(f.files[3].buffer);mutate(r);f.files[3].buffer=Buffer.from(JSON.stringify(r));f.manifest.receipts[3].sha256=fixture.sha(f.files[3].buffer);await assert.rejects(Bundle.load(inputs(f),f.context));
 }
 const f=fixture();f.manifest.receipts[3].verdict='PASS';await assert.rejects(Bundle.load(inputs(f),f.context),/verdict differs/);
});
