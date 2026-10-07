const {test}=require('node:test'),assert=require('node:assert/strict'),Review=require('./massing-review-model.js');
function pair(){const draft={schema:'fdmgen.massing-plan.v0.3',source:{orientation_table_sha256:'a'.repeat(64),mesh:{sha256:'b'.repeat(64)},problem:'part'},orientation:{id:'flat'},massing:{shell_only:false,helper_regions:[{id:'rib',name:'Seat rib'}]}};const receipt={schema:'fdmgen/massing-export@0.1',plan:{draft_sha256:'c'.repeat(64),table_sha256:'a'.repeat(64),mesh_sha256:'b'.repeat(64),problem:'part',candidate_id:'flat'},project_3mf_sha256:'d'.repeat(64),template_3mf_sha256:'e'.repeat(64),capability_context_matches_template:false,helpers:[{id:'rib'}],checks:[{rule:'MOD-001',level:'M',verdict:'FAIL',provisional:true,message:'Too thin',fixes:['Widen']} ]};return {draft,receipt};}
test('exact draft, source, helper and check pairing; mismatch context remains reviewable',()=>{const {draft,receipt}=pair();assert.equal(Review.pair(draft,'c'.repeat(64),receipt),receipt);for(const mutate of [r=>r.plan.draft_sha256='f'.repeat(64),r=>r.plan.candidate_id='other',r=>r.plan.mesh_sha256='f'.repeat(64),r=>r.helpers=[],r=>r.helpers.push({id:'rib'}),r=>r.checks[0].verdict='qualified']){const r=structuredClone(receipt);mutate(r);assert.throws(()=>Review.pair(draft,'c'.repeat(64),r));}});
test('shell-only receipts have no helpers, and unknown checks are retained',()=>{const {draft,receipt}=pair();draft.massing={shell_only:true,helper_regions:[]};receipt.helpers=[];receipt.checks[0].verdict='NOT_CHECKED';assert.equal(Review.pair(draft,'c'.repeat(64),receipt).checks[0].verdict,'NOT_CHECKED');});
const fs=require('node:fs'),path=require('node:path');
const report=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/massing/sample-export-report.json'))),evidence=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/massing/sample-slice-evidence.json')));
test('real slice pairs to project, plan and complete helper set',()=>{assert.equal(Review.slice(report,evidence),evidence);for(const mutate of [r=>r.project_3mf_sha256='a'.repeat(64),r=>r.plan.candidate_id='other',r=>r.helpers.pop(),r=>r.helpers.push(r.helpers[0]),r=>r.helpers[0].added_solid_mm3=NaN,r=>r.helpers[0].solid_infill_in_box_mm3=-1]){const r=structuredClone(evidence);mutate(r);assert.throws(()=>Review.slice(report,r));}});
test('baseline-free evidence stays identifiable and negative deltas remain measurable',()=>{const r=structuredClone(evidence);r.helpers[0].added_solid_mm3=-5;r.helpers[0].added_fill_fraction=-.1;assert.equal(Review.slice(report,r),r);r.baseline=null;assert.throws(()=>Review.slice(report,r));for(const h of r.helpers)h.baseline_solid_infill_mm3=null;assert.equal(Review.slice(report,r).baseline,null);});

test('baseline mismatch is independently checked from settings when recorded',()=>{const r=structuredClone(evidence);r.baseline_context_mismatch=[];r.slicer={layer_height:'0.2',enable_support:'0'};r.baseline_slicer={layer_height:'0.3',enable_support:'1'};assert.deepEqual(Review.contextMismatch(r),['layer_height','enable_support']);});

test('revised browser draft pairs to its exact table and geometry report',()=>{
 const {createHash}=require('node:crypto'),sha=bytes=>createHash('sha256').update(bytes).digest('hex');
 const raw=fs.readFileSync(path.join(__dirname,'fixtures/revised-draft.json')),draft=JSON.parse(raw);
 const revised=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/revised-export-report.json')));
 const table=fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json'));
 assert.equal(draft.source.orientation_table_sha256,sha(table));
 assert.equal(Review.pair(draft,sha(raw),revised),revised);
 assert.equal(revised.checks.length,4);assert(revised.checks.every(c=>c.verdict==='PASS'&&c.provisional));
 // A revised helper cannot inherit the archived draft's slice evidence.
 assert.throws(()=>Review.slice(revised,evidence));
});

test('revised slice matches its project and baseline context, not the old project',()=>{
 const revised=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/revised-export-report.json')));
 const sliced=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/revised-slice-evidence.json')));
 assert.equal(Review.slice(revised,sliced),sliced);assert.deepEqual(Review.contextMismatch(sliced),[]);
 assert.equal(sliced.baseline,'shell-only slice');assert.equal(sliced.helpers[0].verdict,'PASS');
 assert(Math.abs(sliced.helpers[0].solid_infill_in_box_mm3-sliced.helpers[0].baseline_solid_infill_mm3-sliced.helpers[0].added_solid_mm3)<.002);
 assert.throws(()=>Review.slice(report,sliced));
});
