const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const B=require('./orient-bundle.js');
const H=c=>c.repeat(64),encode=v=>Buffer.from(JSON.stringify(v));
const file=(name,bytes)=>({name,size:bytes.length,arrayBuffer:async()=>bytes});
// Explicit synthetic contract fixture: independent known shell and bridge measurements.
async function fixture(){
 const pose={id:'pose-a',R_design_to_print:[[1,0,0],[0,1,0],[0,0,1]],t_mm:[10,20,0]};
 const placement={shift_xy_mm:[0,0],tol_mm:.5,min_inside:.99,verified:'one-way containment, not proof of identity',bands:[1,2,3].map(z_mm=>({z_mm,inside_fraction:1,points:10}))};
 const common={pose,placement,table:{sha256:H('a')},mesh:{sha256:H('b')},gcode:{gcode_sha256:H('c')},source_sha256:{'checker.py':H('d')}};
 const shell={...structuredClone(common),schema:'fdmgen/shell-check@0.3',method:{surface_samples:100},grid:{clipped_outside_grid_mm3:0},result:{rule:'SHELL-001',level:'T',verdict:'PASS',provisional:true,metrics:{thin_fraction:.02,samples:90,unmeasured:10}}};
 const bridge={...structuredClone(common),schema:'fdmgen/bridge-check@0.2',method:{max_span_external_mm:10,max_span_internal_mm:18,cell_mm:.1},result:{rule:'BRG-001',level:'T',verdict:'FAIL',provisional:true,metrics:{max_span_external_mm:4,max_span_internal_mm:20,max_ceiling_span_external_mm:2,max_ceiling_span_internal_mm:12,bridge_roads:10,external_roads:4,internal_roads:6,max_cantilever_mm:1,bridge_layers_z_mm:[1,2]}}};
 const entries=[];
 for(const [check,r] of [['shell-check',shell],['bridge-check',bridge]])entries.push({check,pose:pose.id,slice_kind:'shell-only',gcode_sha256:H('c'),path:check+'.json',schema:r.schema,sha256:await B.digest(encode(r)),verdict:r.result.verdict});
 const provenance=e=>({sha256:e.sha256,slice_kind:e.slice_kind,gcode_sha256:e.gcode_sha256,source_sha256:common.source_sha256});
 const table={mesh:{sha256:H('b')},enriched:{from_table_sha256:H('a')},candidates:[{...pose,columns:{
  t_shell_thin_fraction:{value:.02,unit:'fraction',rule:'SHELL-001',level:'T',verdict:'PASS',provisional:true,receipt:provenance(entries[0]),coverage:{samples_requested:100,measured:90,unmeasured:10,clipped_outside_grid_mm3:0},pose_evidence:{verified:placement.verified,bands:placement.bands}},
  t_bridge_span_external_mm:{value:4,ceiling_span_mm:2,limit_mm:10,unit:'mm',rule:'BRG-001',level:'T',verdict:'PASS',provisional:true,receipt:{...provenance(entries[1]),overall_verdict:'FAIL'},coverage:{bridge_roads:10,external_roads:4,internal_roads:6,max_cantilever_mm:1,bridge_layers_z_mm:[1,2],cell_mm:.1}},
  t_bridge_span_internal_mm:{value:20,ceiling_span_mm:12,limit_mm:18,unit:'mm',rule:'BRG-001',level:'T',verdict:'FAIL',provisional:true,receipt:{...provenance(entries[1]),overall_verdict:'FAIL'},coverage:{bridge_roads:10,external_roads:4,internal_roads:6,max_cantilever_mm:1,bridge_layers_z_mm:[1,2],cell_mm:.1}}
 }}]};
 const manifest={schema:'fdmgen/orient-evidence@0.1',table:{input_sha256:H('a'),root_sha256:H('a')},slices:[{pose:pose.id,slice_kind:'shell-only',gcode_sha256:H('c')}],receipts:entries,enriched_table:{path:'table.json',sha256:await B.digest(encode(table))}};
 return {manifest,table,shell,bridge};
}
const files=f=>[file('manifest.json',encode(f.manifest)),file('table.json',encode(f.table)),file('shell-check.json',encode(f.shell)),file('bridge-check.json',encode(f.bridge))];
async function rehash(f){
 for(const [i,r] of [[0,f.shell],[1,f.bridge]]){
  f.manifest.receipts[i].sha256=await B.digest(encode(r));
  for(const c of Object.values(f.table.candidates[0].columns))if(c.rule===r.result.rule)c.receipt.sha256=f.manifest.receipts[i].sha256;
 }
 f.manifest.enriched_table.sha256=await B.digest(encode(f.table));
}
test('orientation bundle validates exact bytes and distinct per-column bridge verdicts',async()=>{
 const f=await fixture(),r=await B.load(files(f));
 assert.deepEqual(r.table,f.table);assert.equal(r.receipts.length,2);assert.deepEqual(Buffer.from(r.tableBytes),encode(f.table));
 assert.equal(r.table.candidates[0].columns.t_bridge_span_external_mm.verdict,'PASS');
 assert.equal(r.receipts[1].entry.verdict,'FAIL');
});
test('missing, duplicate, malformed and modified files are refused before use',async()=>{
 const f=await fixture(),good=files(f);
 await assert.rejects(B.load(good.slice(0,2)),/Missing.*shell-check.json.*bridge-check.json/);
 await assert.rejects(B.load([...good,good[0]]),/Duplicate/);
 await assert.rejects(B.load([file('broken.json',Buffer.from('{'))]),/Invalid JSON.*broken.json/);
 const modified=files(f);modified[2]=file('shell-check.json',Buffer.concat([encode(f.shell),Buffer.from(' ')]));
 await assert.rejects(B.load(modified),/fingerprint differs/);
});
test('rehashing does not bypass pose, slice, root, measurement or coverage binding',async()=>{
 for(const mutate of [
  f=>f.shell.pose.id='pose-b',f=>f.bridge.gcode.gcode_sha256=H('e'),f=>f.shell.table.sha256=H('e'),f=>f.shell.mesh.sha256=H('e'),
  f=>f.shell.placement.bands.pop(),f=>f.shell.placement.bands[1].z_mm=1,
  f=>f.manifest.receipts[0].slice_kind='project',f=>f.manifest.receipts[0].verdict='FAIL',
  f=>f.table.candidates[0].columns.t_shell_thin_fraction.value=.03,
  f=>f.table.candidates[0].columns.t_shell_thin_fraction.coverage.unmeasured=0,
  f=>f.table.candidates[0].columns.t_bridge_span_external_mm.verdict='FAIL',
  f=>f.table.candidates[0].columns.t_bridge_span_internal_mm.ceiling_span_mm=13,
  f=>f.table.candidates[0].columns.t_bridge_span_external_mm.coverage.bridge_roads=11,
  f=>f.table.candidates[0].columns.t_shell_thin_fraction.receipt.gcode_sha256=H('e')
 ]){const f=await fixture();mutate(f);await rehash(f);await assert.rejects(B.load(files(f)));}
});
test('duplicate poses and reused or traversing receipt names are refused',async()=>{
 for(const mutate of [f=>{f.manifest.slices.push({...f.manifest.slices[0],slice_kind:'project'});f.manifest.receipts.push(...f.manifest.receipts);},f=>f.manifest.receipts[1].path='shell-check.json',f=>f.manifest.receipts[0].path='../shell-check.json']){
  const f=await fixture();mutate(f);await assert.rejects(B.load(files(f)));
 }
});
test('real producer orientation bundle retains exact table bytes',async()=>{
 const dir=path.join(__dirname,'fixtures/orient-evidence'),selected=[];
 for(const name of await fs.readdir(dir))if(name.endsWith('.json'))selected.push(file(name,await fs.readFile(path.join(dir,name))));
 const r=await B.load(selected);assert.equal(r.manifest.slices.length,2);assert.equal(r.receipts.length,4);
 assert.equal(r.tableHash,await B.digest(r.tableBytes));
 assert.equal(r.manifestHash,'0b79365d547b5d0f360a9a35499f5b1beca6f4fee51c904308137dac174ab8a9');
 assert.equal(r.tableHash,'0295e63551efd604a4faad2939a2cd9ef3083c8e1f611ba927f48cc623f1071c');
});
