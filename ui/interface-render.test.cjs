const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const I=require('./interface-render.js'),{transformMesh}=require('./viewer.js'),make=require('./interface-test-data.cjs');
const root='tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs',bytes=fs.readFileSync(root+'.orientation-table.json'),table=JSON.parse(bytes),sha=crypto.createHash('sha256').update(bytes).digest('hex'),keepout=JSON.parse(fs.readFileSync(root+'.keepout-render.json'));
const g=make(table,sha,keepout);
test('interface consumer checks pins, identity, complete declarations and derived model geometry',()=>{
 assert.equal(I.validate(g,table,sha),g);
 for(const change of [x=>x.table.sha256='0'.repeat(64),x=>x.mesh.sha256='0'.repeat(64),x=>x.frame='installed',x=>x.units='m',x=>x.installed_to_design.R[0][0]=-1,x=>x.installed_to_design.t_mm[0]=1,x=>delete x.problem,x=>x.clip.bbox_mm[0][0]=null,x=>x.clip.margin_mm=-1,x=>x.items.pop(),x=>x.items.push(x.items[0]),x=>x.items[0].base_radius_mm+=.5,x=>x.items[0].source_fields.seat_radius_mm=[13.6],x=>x.items[0].centre_plane.value=[91,0],x=>x.items[0].axis_end_mm[2]+=1,x=>x.items[0].axis_start_mm[0]+=1,x=>x.items[0].unbounded=[],x=>x.items[0].axis='X',x=>x.items[0].support='allowed']){
  const bad=structuredClone(g);change(bad);assert.throws(()=>I.validate(bad,table,sha));
 }
});
test('all-axis wireframes keep base radius and clipping ends; pose is applied once',()=>{
 for(const axis of ['X','Y','Z']){
  const k='XYZ'.indexOf(axis),indices=[0,1,2].filter(a=>a!==k),start=[10,20,30],end=[10,20,30];start[k]=-2;end[k]=4;
  const item={rendered:true,axis,base_radius_mm:3,axis_start_mm:start,axis_end_mm:end},lines=I.segments(item);
  assert.equal(lines.length,132);
  for(const p of lines.flat()){assert([-2,4].includes(p[k]));assert(Math.abs(Math.hypot(...indices.map(a=>p[a]-start[a]))-3)<1e-12);}
 }
 const line=I.segments({rendered:true,axis:'Z',base_radius_mm:3,axis_start_mm:[10,20,-2],axis_end_mm:[10,20,4]})[128];
 assert.deepEqual(line,[[13,20,-2],[13,20,4]]);
 assert.deepEqual(Array.from(transformMesh(line.flat(),[[0,-1,0],[1,0,0],[0,0,1]],[100,200,300])),[80,213,298,80,213,304]);
 assert.deepEqual(I.segments({rendered:false}),[]);
});
test('unsupported declared interfaces remain listed without invented geometry',()=>{
 const t=structuredClone(table);t.interfaces.push({id:'unknown',type:'new_model'});const data=make(t,sha,keepout);assert.equal(I.validate(data,t,sha),data);assert.equal(data.items.at(-1).rendered,false);
 data.items.at(-1).reason='';assert.throws(()=>I.validate(data,t,sha));
});

test('real producer interface sidecar matches the original pinned table',()=>{
 const real=JSON.parse(fs.readFileSync(root+'.interface-render.json'));assert.equal(I.validate(real,table,sha),real);
 assert.deepEqual(real.items.map(i=>[i.id,i.axis,i.base_radius_mm]),[['rear_seat','Z',13.6],['front_seat','Z',13.6],['mount_upper','X',2.6],['mount_lower','X',2.6]]);
});
