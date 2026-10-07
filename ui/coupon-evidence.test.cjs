const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),C=require('./coupon-evidence.js');
const dir=path.join(__dirname,'../tests/fixtures/coupons'),raw=fs.readFileSync(path.join(dir,'ladder-plate.json')),plate=JSON.parse(raw),hash=crypto.createHash('sha256').update(raw).digest('hex');
const read=name=>JSON.parse(fs.readFileSync(path.join(dir,name)));
test('same plate pairs with opposite support-setting receipts without inferring printability',()=>{
 const on=C.pair(plate,hash,read('slice-evidence-support45.json')),off=C.pair(plate,hash,read('slice-evidence-nosupport.json'));
 assert.equal(C.supportLabel(on.gcode.settings),'Support enabled');assert.equal(C.supportLabel(off.gcode.settings),'Support disabled');
 assert(on.rungs.find(x=>x.id==='ovh-35').support_segments>0);assert.equal(off.rungs.find(x=>x.id==='ovh-35').support_segments,0);
});
test('mismatched plate, duplicate rungs and missing data fail pairing',()=>{
 const r=read('slice-evidence-support45.json');assert.throws(()=>C.pair(plate,'0'.repeat(64),r),/fingerprint/);
 r.rungs.push(r.rungs[0]);assert.throws(()=>C.pair(plate,hash,r),/duplicate/);
 const missing=read('slice-evidence-support45.json');missing.rungs.pop();assert.throws(()=>C.pair(plate,hash,missing),/missing/);
});
test('invalid frame and negative measurements cannot appear as evidence',()=>{
 assert.throws(()=>C.plate({...plate,frame:'design'}),/print-frame/);
 const r=read('slice-evidence-support45.json');r.rungs[0].support_volume_mm3=-1;assert.throws(()=>C.pair(plate,hash,r),/Invalid/);
});
