const test=require('node:test'),assert=require('node:assert/strict'),{locations}=require('./bridge-locations.js');
function fixture(){
 const R=[[0,-1,0],[1,0,0],[0,0,1]],t=[10,20,30],sha='a'.repeat(64),pose={id:'p',R_design_to_print:R,t_mm:t,build_dir_design:[0,0,1]};
 const draft={orientation:pose,source:{mesh:{sha256:sha},orientation_table_sha256:sha}};
 const points={road_start:[10,20,31],road_end:[20,20,31],run_start:[12,20,31],run_end:[18,20,31]};
 const w={road_index:4,role:'Bridge',z_mm:31,value_mm:6,print_mm:points,plate_mm:Object.fromEntries(Object.entries(points).map(([k,p])=>[k,[p[0]+3,p[1]-2,p[2]]])),design_mm:Object.fromEntries(Object.entries(points).map(([k,p])=>[k,[p[1]-20,10-p[0],p[2]-30]]))};
 const receipt={schema:'fdmgen/bridge-check@0.2',pose,mesh:{sha256:sha},table:{sha256:sha},placement:{shift_xy_mm:[3,-2]},result:{rule:'BRG-001',level:'T',metrics:{max_span_external_mm:6,max_span_internal_mm:0,max_ceiling_span_external_mm:0,max_ceiling_span_internal_mm:0,worst:{external:{strand:w,ceiling:null},internal:{strand:null,ceiling:null}}}}};
 return {receipt,draft};
}
test('rotated pose and shifted plate preserve the distinct road and unsupported run',()=>{const {receipt,draft}=fixture(),r=locations(receipt,draft);assert.equal(r.length,1);assert.equal(r[0].value_mm,6);assert.deepEqual(r[0].source.design_mm.run_end,[0,-8,1]);});
test('legacy receipts offer no invented location',()=>{const {receipt,draft}=fixture();delete receipt.result.metrics.worst;assert.deepEqual(locations(receipt,draft),[]);});
test('frame, maximum, run and source mismatches withhold optional geometry',()=>{
 for(const corrupt of [r=>r.mesh.sha256='b'.repeat(64),r=>r.placement.shift_xy_mm[0]=0,r=>r.result.metrics.max_span_external_mm=7,r=>r.result.metrics.worst.external.strand.design_mm.run_end[0]=1,r=>r.result.metrics.worst.external.strand.value_mm=0,r=>r.result.metrics.worst.external.strand=null]){const {receipt,draft}=fixture();corrupt(receipt);assert.throws(()=>locations(receipt,draft));}
});

test('exact producer witnesses match both bracket poses and root table',()=>{
 const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
 const table=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json')));
 for(const [name,sha] of [["facet-00-shell-only.bridge-check.json", "6d9c291875ded0fb338ffaa35a0c67b9876f72fd63c21b5b615c2f1081b46fb0"], ["facet-01-shell-only.bridge-check.json", "2342cbeb6c1e4d9c2d6f036b61140aace0f65ae498cdf0dce7fdc56440127aa9"]]){
  const bytes=fs.readFileSync(path.join(__dirname,'fixtures/bridge-locations',name));assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),sha);
  const r=JSON.parse(bytes),pose=table.candidates.find(p=>p.id===r.pose.id),out=locations(r,{orientation:pose,source:{mesh:table.mesh,orientation_table_sha256:r.table.sha256}});
  assert.equal(out.length,4);assert(out.every(w=>w.value_mm>0));
 }
});

test('frame-consistent sideways run still must lie on the parent road',()=>{
 const {receipt,draft}=fixture(),w=receipt.result.metrics.worst.external.strand;
 for(const k of ['run_start','run_end']){w.print_mm[k][1]+=.05;w.plate_mm[k][1]+=.05;w.design_mm[k][0]+=.05;}
 assert.throws(()=>locations(receipt,draft),/outside the road/);
});
