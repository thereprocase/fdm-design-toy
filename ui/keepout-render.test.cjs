const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const K=require('./keepout-render.js'),{transformMesh}=require('./viewer.js');
const root='tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs';
const bytes=fs.readFileSync(root+'.orientation-table.json'),table=JSON.parse(bytes),sha=crypto.createHash('sha256').update(bytes).digest('hex');
const geometry=JSON.parse(fs.readFileSync(root+'.keepout-render.json'));
test('real keep-out geometry pins table, mesh, frame and complete constraint declarations',()=>{
 assert.equal(K.validate(geometry,table,sha),geometry);
 for(const mutate of [g=>g.table.sha256='0'.repeat(64),g=>g.mesh.sha256='0'.repeat(64),g=>g.frame='installed',g=>g.units='m',g=>g.installed_to_design.R[0][0]=-1,g=>g.installed_to_design.t_mm[0]=1,g=>delete g.problem,g=>g.clip.bbox_mm[0][0]=null,g=>g.items.pop(),g=>g.items.push(g.items[0]),g=>g.items[0].rule='different',g=>g.items[0].min_mm[0]=null,g=>g.items[0].original.min_mm[0]=2,g=>g.items[1].discs[0].radius_mm=-1,g=>g.items[1].coverage.discs=1]){
  const bad=structuredClone(geometry);mutate(bad);assert.throws(()=>K.validate(bad,table,sha));
 }
});
test('wire geometry uses declared design bounds and sampled sweep radii; pose applied once',()=>{
 const box={rendered:true,type:'box',min_mm:[0,1,2],max_mm:[3,5,7]},lines=K.segments(box);
 assert.equal(lines.length,12);assert.deepEqual(lines[0],[[0,1,2],[3,1,2]]);
 assert.deepEqual(Array.from(transformMesh(lines[0].flat(),[[0,-1,0],[1,0,0],[0,0,1]],[10,20,30])),[9,20,32,9,23,32]);
 const sweep={rendered:true,type:'flange_sweep',discs:[{centre_xy_mm:[10,20],radius_mm:5}],z_min_mm:-2,z_max_mm:2};
 const paths=K.segments(sweep);assert.equal(paths.length,132);
 for(const point of paths.flat()){assert(Math.abs(Math.hypot(point[0]-10,point[1]-20)-5)<1e-12);assert([-2,2].includes(point[2]));}
 assert.deepEqual(K.segments({rendered:false}),[]);
});
