const {chromium}=require('playwright');
const path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs'),crypto=require('node:crypto'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
 const bundle=vm.runInNewContext(fs.readFileSync(path.join(__dirname,'capabilities-data.js'),'utf8')+'\nmodifierCapabilities');
 assert.equal(bundle.sha256,crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname,'..',bundle.source))).digest('hex'),'Regenerate the catalog snapshot when its source changes');
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',dialog=>dialog.accept());
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
  const panel=page.locator('#modifier-evidence');
  assert.match(await panel.innerText(),/no verified slicer\/template match/);
  await panel.getByText('Tested slicer, profile and evidence limits',{exact:true}).click();
  assert.match(await panel.innerText(),/template_3mf_sha256/);
  await panel.getByText('Inspect measured overrides and side effects',{exact:true}).click();
  for(const record of bundle.evidence.settings){
   // Probe ids distinguish the density-only case from combined requests.
   const exact=panel.locator(`[data-capability="${record.receipt.probe}"]`);
   await exact.locator('summary').click();
   const body=await exact.innerText();
   assert(body.includes(record.receipt.gcode_sha256));
   if(record.non_local_side_effect)assert(body.includes(record.non_local_side_effect));
   if(record.receipt.positive_control_gcode_sha256)assert(body.includes(record.receipt.positive_control_gcode_sha256));
   if(record.receipt.slicer_build)assert(body.includes('slicer_build'));
  }
  assert.match(await panel.innerText(),/wall_generator=classic — ignored/);
  assert.match(await panel.innerText(),/layer_height=0.1 — ignored/);
  assert(await page.locator('#walls').isEnabled());assert(await page.locator('#skin').isEnabled());
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log('PASS capability source hash, exact requests, context, ignored settings, side effects, positive control/build receipts, editable body settings, mobile');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
