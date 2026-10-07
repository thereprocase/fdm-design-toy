const {chromium}=require('playwright');
const path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs/promises'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
  await page.getByRole('button',{name:'facet-00',exact:true}).click();
  await page.locator('#mesh-file').setInputFiles(process.env.FDM_PREVIEW_MESH);
  await page.waitForFunction(()=>document.querySelector('#mesh-status').textContent.startsWith('Mesh fingerprint matched'));
  await page.locator('#rationale').fill('Preserve loaded interfaces.');
  const region=page.locator('.helper-region').first();
  for(const [key,value] of Object.entries({name:'Seat backing',location:'Rear seat',purpose:'Seat load transfer',keep_clear:'Preserve rod bore'}))await region.locator(`[data-key="${key}"]`).fill(value);
  await region.locator('[data-interface-id="rear_seat"]').check();await region.locator('[data-spatial]').check();
  await page.locator('#zoom-in').click();assert(await page.evaluate(()=>viewer.zoom>1));await page.locator('#zoom-out').click();
  await page.locator('#view-top').click();await region.getByRole('button',{name:'Place centre on part'}).click();
  const hit=await page.evaluate(()=>{
    const v=viewer.vertices,p=viewer.project((v[0]+v[3]+v[6])/3,(v[1]+v[4]+v[7])/3,(v[2]+v[5]+v[8])/3),r=viewer.canvas.getBoundingClientRect();return [p[0]+r.left,p[1]+r.top];
  });await page.mouse.click(...hit);await page.waitForFunction(()=>document.querySelector('#placement-status').textContent.startsWith('Region centre placed'));
  assert.equal(await page.evaluate(()=>viewer.regions.length),1);
  const centers=await region.locator('[data-geometry="center_mm"]').evaluateAll(fields=>fields.map(f=>f.value));
  await page.getByRole('button',{name:'facet-01',exact:true}).click();await page.locator('#rationale').fill('Alternative pose for the same reinforcement.');
  assert.deepEqual(await region.locator('[data-geometry="center_mm"]').evaluateAll(fields=>fields.map(f=>f.value)),centers);
  await region.locator('[data-geometry="size_mm"][data-axis="0"]').fill('0.5');await page.waitForFunction(()=>document.querySelector('#region-warnings').textContent.includes('0.84'));
  await region.locator('[data-geometry="size_mm"][data-axis="0"]').fill('10');
  const pending=page.waitForEvent('download');await page.locator('#export').click();const draft=JSON.parse(await fs.readFile(await(await pending).path(),'utf8'));
  assert.equal(draft.massing.helper_regions[0].geometry.frame,'design');assert.equal(draft.massing.helper_regions[0].geometry_status,'sketch');assert.deepEqual(draft.massing.helper_regions[0].keep_clear.interface_ids,['rear_seat']);
  await page.locator('#draft-file').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(draft))});await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));
  assert.deepEqual(await region.locator('[data-geometry="center_mm"]').evaluateAll(fields=>fields.map(f=>Number(f.value))),draft.massing.helper_regions[0].geometry.center_mm);
  if(process.env.FDM_PREVIEW_SCREENSHOT)await page.screenshot({path:process.env.FDM_PREVIEW_SCREENSHOT,fullPage:true});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  console.log('PASS spatial click placement, design-frame persistence across poses, size screen, interface refs, sketch export/reopen, mobile, console');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
