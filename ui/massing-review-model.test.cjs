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

const seedReport=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/seed-export-report.json'))),seedSlice=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/seed-slice-evidence.json'))),mechanics=JSON.parse(fs.readFileSync(path.join(__dirname,'../bench/receipts/occupancy-connected-sensitivity-r1.json')));
test('mechanics pairs exact project, plan, both Gcodes and grid provenance',()=>{
 assert.equal(Review.mechanics(seedReport,seedSlice,mechanics),mechanics);assert.equal(Review.mechanicsComparable(mechanics),false);
 for(const mutate of [r=>r.inputs.project.provenance.project_3mf_sha256='a'.repeat(64),r=>r.inputs.baseline.provenance.gcode_sha256='a'.repeat(64),r=>r.inputs.project.provenance.plan.draft_sha256='a'.repeat(64),r=>r.inputs.baseline.provenance.grid.shape=[1,2,3],r=>r.solves.project.compliance_N_mm=NaN,r=>delete r.fragment_removal.project,r=>r.does_not_establish='bad scope']){
  const r=structuredClone(mechanics);mutate(r);assert.throws(()=>Review.mechanics(seedReport,seedSlice,r));
 }
 const missing=structuredClone(seedSlice);delete missing.slicer.layer_height;delete missing.baseline_slicer.layer_height;assert.throws(()=>Review.mechanics(seedReport,missing,mechanics),/complete recorded/);
 const mismatch=structuredClone(seedSlice);mismatch.baseline_slicer.layer_height='0.3';assert.throws(()=>Review.mechanics(seedReport,mismatch,mechanics),/matching-context/);
});
test('mechanics does not turn missing convergence, load conservation or audits into benefit',()=>{
 for(const mutate of [r=>delete r.solves,r=>r.solves.project.true_relative_residual=.1,r=>r.audits.project.status='blocked',r=>r.audits.project.missing_loaded_dofs=1,r=>r.seats.rear_seat.moment_error_N_mm=1]){
  const r=structuredClone(mechanics);mutate(r);assert.equal(Review.mechanicsComparable(Review.mechanics(seedReport,seedSlice,r)),false);
 }
 const raw=JSON.parse(fs.readFileSync(path.join(__dirname,'../bench/receipts/occupancy-seat-transfer-r1.json')));
 assert.equal(Review.mechanicsComparable(Review.mechanics(seedReport,seedSlice,raw)),false);
});

test('shell receipts pair exact slice and pose and validate sampling evidence',()=>{
 const r=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/seed-project-shell-check.json')));
 assert.equal(Review.shell(seedReport,seedSlice,r),r);
 for(const mutate of [r=>r.pose='wrong',r=>r.cell_mm=0,r=>r.result.metrics.thin_fraction=2,r=>r.result.metrics.samples=0,r=>r.result.level='M',r=>r.mesh_sha256='c'.repeat(64)]){
  const bad=structuredClone(r);mutate(bad);assert.throws(()=>Review.shell(seedReport,seedSlice,bad));
 }
});

test('current shell receipts require geometry, method, source and transform provenance',()=>{
 const old=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/seed-project-shell-check.json'))),m=old.result.metrics;
 const draft=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/seed-draft.json')));
 // Synthetic transport fixture, not a relabelled measurement or published receipt.
 const modern={schema:'fdmgen/shell-check@0.2',result:old.result,gcode:seedSlice.slicer,
  pose:{id:old.pose,R_design_to_print:draft.orientation.R_design_to_print,t_mm:draft.orientation.t_mm},
  table:{sha256:seedReport.plan.table_sha256},mesh:{sha256:seedReport.plan.mesh_sha256},
  grid:{frame:'print (plate) frame of the pose',origin_mm:[0,0,0],cell_mm:old.cell_mm,shape:old.grid_shape,clipped_outside_grid_mm3:0},
  method:{deposit:{roads:'credited',caps:true,step_frac:.5},seed:0,surface_samples:m.samples+m.unmeasured,thin_fraction_limit:.01,min_beads:m.min_beads,bead_spacing_mm:m.bead_spacing_mm,layer_mm:m.layer_mm,entry_mm:m.entry_mm},
  source_sha256:Object.fromEntries(['catalog/checks/shell.py','gcode/occupancy.py','gcode/reader.py'].map(k=>['fdmgen/'+k,'a'.repeat(64)]))};
 assert.equal(Review.shell(seedReport,seedSlice,modern,draft)._receipt,modern);
 for(const mutate of [r=>r.pose.t_mm[0]+=1,r=>r.table.sha256='b'.repeat(64),r=>r.method.deposit.step_frac=0,r=>r.method.surface_samples=1,r=>delete r.source_sha256['fdmgen/gcode/reader.py'],r=>r.gcode.layer_height='wrong',r=>delete r.gcode.generator]){
  const bad=structuredClone(modern);mutate(bad);assert.throws(()=>Review.shell(seedReport,seedSlice,bad,draft));
 }
});

test('paired shell fractions require common current methods and geometry',()=>{
 const read=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/seed-'+name+'.json')));
 const draft=read('draft'),project=read('project-shell-check-current'),baseline=read('baseline-shell-check-current');
 const p=Review.shell(seedReport,seedSlice,project,draft),b=Review.shell(seedReport,seedSlice,baseline,draft,'baseline');
 assert(Review.shellComparison(p,b,seedSlice).comparable);
 assert.throws(()=>Review.shell(seedReport,seedSlice,project,draft,'baseline'),/G-code differs/);
 assert(!Review.shellComparison(Review.shell(seedReport,seedSlice,read('project-shell-check')),b,seedSlice).comparable);
 for(const mutate of [r=>r.method.seed=1,r=>r.grid.origin_mm[0]+=1,r=>r.source_sha256['fdmgen/gcode/reader.py']='c'.repeat(64)]){
  const bad=structuredClone(baseline);mutate(bad);
  assert(!Review.shellComparison(p,Review.shell(seedReport,seedSlice,bad,draft,'baseline'),seedSlice).comparable);
 }
 const mismatch=structuredClone(seedSlice);mismatch.baseline_context_mismatch=['wall_loops'];
 assert(!Review.shellComparison(p,b,mismatch).comparable);
});

test('shell 0.3 validates section evidence and gates comparisons on checked heights',()=>{
 const read=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/seed-'+name+'.json')));
 const draft=read('draft'),project=read('project-shell-check-current'),baseline=read('baseline-shell-check-current');
 const placement={shift_xy_mm:[0,0],tol_mm:.5,min_inside:.99,verified:'Synthetic contract test',bands:[2,6,10].map(z_mm=>({z_mm,inside_fraction:1,points:100}))};
 for(const r of [project,baseline]){r.schema='fdmgen/shell-check@0.3';r.placement=structuredClone(placement);}
 const p=Review.shell(seedReport,seedSlice,project,draft),b=Review.shell(seedReport,seedSlice,baseline,draft,'baseline');
 assert(Review.shellComparison(p,b,seedSlice).comparable);
 for(const mutate of [r=>delete r.placement,r=>r.placement.bands[0].inside_fraction=.2,r=>r.placement.bands[0].points=0,r=>r.placement.bands[1].z_mm=2,r=>r.placement.shift_xy_mm=[0]]){
  const bad=structuredClone(project);mutate(bad);assert.throws(()=>Review.shell(seedReport,seedSlice,bad,draft),/placement/);
 }
 const short=structuredClone(project);short.placement.bands=[];
 assert(!Review.shellComparison(Review.shell(seedReport,seedSlice,short,draft),b,seedSlice).comparable);
 assert(!Review.shellComparison(p,Review.shell(seedReport,seedSlice,read('baseline-shell-check-current'),draft,'baseline'),seedSlice).comparable);
 const policy=structuredClone(baseline);policy.placement.tol_mm=1;
 assert(!Review.shellComparison(p,Review.shell(seedReport,seedSlice,policy,draft,'baseline'),seedSlice).comparable);
});

test('weighted mechanics pairs real p1/p3 receipts without changing their schema',()=>{
 const read=p=>JSON.parse(fs.readFileSync(path.join(__dirname,p))),rep=read('fixtures/seed-export-report.json'),slice=read('fixtures/seed-slice-evidence.json');
 for(const power of [1,3]){
  const r=read(`../bench/receipts/occupancy-density-p${power}-sf16-r1.json`),before=JSON.stringify(r);
  assert.equal(Review.mechanics(rep,slice,r),r);assert(Review.mechanicsComparable(r));assert.equal(JSON.stringify(r),before);
  for(const mutate of [x=>x.material.stiffness_floor=.001,x=>x.material.power=0,x=>x.load_sha256=null,x=>x.cases.baseline.provenance.gcode_sha256='0'.repeat(64),x=>x.grid.shape[0]++,x=>x.cases.project.fragment_removal=null]){
   const bad=structuredClone(r);mutate(bad);assert.throws(()=>Review.mechanics(rep,slice,bad));
  }
  for(const mutate of [x=>x.cases.project.audit.missing_load_l1_N=1,x=>x.cases.project.fragment_removal.removed_fixed_dofs=1,x=>x.cases.project.solve.true_relative_residual=.01,x=>x.cases.project.audit.reasons=['blocked'],x=>x.cases.project.solve.cg_status=1]){
   const bad=structuredClone(r);mutate(bad);Review.mechanics(rep,slice,bad);assert.equal(Review.mechanicsComparable(bad),false);
  }
 }
});

test('mechanics withholding names load, solver and seat conservation failures',()=>{
 const read=p=>JSON.parse(fs.readFileSync(path.join(__dirname,p)));
 const weighted=read('../bench/receipts/occupancy-density-p1-sf16-r1.json');
 assert.deepEqual(Review.mechanicsReasons(weighted),[]);
 weighted.cases.project.audit.missing_load_l1_N=1;
 weighted.cases.baseline.solve.true_relative_residual=.01;
 const reasons=Review.mechanicsReasons(weighted);
 assert(reasons.some(x=>x.includes('Project: 1 N')));assert(reasons.some(x=>x.includes('Shell-only: true relative residual')));
 const binary=read('../bench/receipts/occupancy-connected-sensitivity-r1.json');
 const restraintReasons=Review.mechanicsReasons(binary);
 assert.equal(restraintReasons.length,2);assert(restraintReasons.every(x=>x.includes("93 original fixed DOFs are absent")));
 const name=Object.keys(binary.seats)[0];binary.seats[name].moment_error_N_mm=1;
 assert.deepEqual(Review.mechanicsReasons(binary),[...restraintReasons,`${name}: seat moment error exceeds 1e-7 N mm.`]);
});

test('weighted comparison requires matching sampling methods but distinct source files are allowed',()=>{
 const read=()=>JSON.parse(fs.readFileSync(path.join(__dirname,'../bench/receipts/occupancy-density-p1-sf16-r1.json')));
 assert.deepEqual(Review.mechanicsReasons(read()),[]);
 for(const mutate of [r=>r.cases.project.provenance.sampling.step_frac='1/3',r=>r.cases.project.provenance.sampling.caps=true,r=>delete r.cases.project.provenance.sampling,r=>r.cases.project.provenance.sampling.generator='other producer']){
  const r=read();mutate(r);assert.equal(Review.mechanicsComparable(r),false);assert(Review.mechanicsReasons(r).some(x=>/sampling/i.test(x)));
 }
 const reordered=read(),s=reordered.cases.project.provenance.sampling;
 reordered.cases.project.provenance.sampling=Object.fromEntries(Object.entries(s).reverse());assert(Review.mechanicsComparable(reordered));
});

test('individual mechanics rows follow their domain gates independently of pair sampling',()=>{
 const r=JSON.parse(fs.readFileSync(path.join(__dirname,'../bench/receipts/occupancy-density-p1-sf16-r1.json')));
 r.cases.project.audit.missing_load_l1_N=1;
 assert(Review.mechanicsCaseReasons(r,'project').length>0);assert.deepEqual(Review.mechanicsCaseReasons(r,'baseline'),[]);
 r.cases.project.audit.missing_load_l1_N=0;r.cases.project.provenance.sampling.step_frac='1/3';
 assert.equal(Review.mechanicsComparable(r),false);assert.deepEqual(Review.mechanicsCaseReasons(r,'project'),[]);
 r.cases.project.solve.cg_status=1;assert(Review.mechanicsCaseReasons(r,'project').some(x=>x.includes('successful convergence')));
});

 test('restraint retention cannot be replaced by rigid rank or a legacy ready label',()=>{
 const read=()=>JSON.parse(fs.readFileSync(path.join(__dirname,'../bench/receipts/occupancy-density-p1-sf16-r1.json')));
 assert(Review.mechanicsComparable(read()));
 for(const mutate of [a=>a.retained_fixed_dofs--,a=>delete a.original_fixed_dofs,a=>a.retained_fixed_dofs++,a=>a.missing_fixed_dofs=1,a=>a.retained_fixed_dofs=1.5]){
  const r=read();mutate(r.cases.project.audit);
  assert.equal(Review.mechanicsComparable(r),false);
  assert(Review.mechanicsCaseReasons(r,'project').some(x=>/fixed DOF|restraint retention/.test(x)));
 }
 const r=read();r.cases.project.audit.missing_fixed_dofs=0;assert(Review.mechanicsComparable(r));
 });
