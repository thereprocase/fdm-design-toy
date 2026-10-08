const {chromium}=require('playwright');
const path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs/promises'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',dialog=>dialog.accept());
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
  await page.getByRole('button',{name:'facet-00',exact:true}).click();
  await page.locator('#mesh-file').setInputFiles(process.env.FDM_PREVIEW_MESH);
  await page.waitForFunction(()=>document.querySelector('#mesh-status').textContent.startsWith('Mesh fingerprint matched'));
  await page.locator('#rationale').fill('Preserve loaded interfaces.');
  await page.locator('#plan-pose').click();assert(await page.locator('#walls').evaluate(e=>e===document.activeElement));
  const region=page.locator('.helper-region').first();
  for(const [key,value] of Object.entries({name:'Seat backing',location:'Rear seat',purpose:'Seat load transfer',keep_clear:'Preserve rod bore'}))await region.locator(`[data-key="${key}"]`).fill(value);
  await region.locator('[data-interface-id="rear_seat"]').check();await region.locator('[data-spatial]').check();
  await page.locator('#zoom-in').click();assert(await page.evaluate(()=>viewer.zoom>1));await page.locator('#zoom-out').click();
  const beforeViews=await page.evaluate(()=>({form:draftFormState(),pose:selected.id,vertices:Array.from(viewer.vertices)}));
  for(const [id,yaw] of [['view-x',Math.PI/2],['view-y',0]]){
    await page.locator('#zoom-in').click();await page.locator('#'+id).click();
    assert.deepEqual(await page.evaluate(()=>[viewer.yaw,viewer.pitch,viewer.zoom]),[yaw,0,1]);
    await page.waitForFunction(()=>!viewer.pending);
    const axes=await page.evaluate(()=>{const p=viewer.project(0,0,0),z=viewer.project(0,0,1);return [z[0]-p[0],z[1]-p[1]];});
    assert(Math.abs(axes[0])<1e-9&&axes[1]<0); // Print Z points up in both side views.
    assert.deepEqual(await page.evaluate(()=>({form:draftFormState(),pose:selected.id,vertices:Array.from(viewer.vertices)})),beforeViews);
  }
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('#view-x').isVisible());assert(await page.locator('#view-y').isVisible());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.setViewportSize({width:1300,height:1000});

  await page.locator('#view-top').click();await region.getByRole('button',{name:'Place centre on part'}).click();
  const overlay=await page.locator('#part-view').boundingBox(),beforeOverlay=await page.evaluate(()=>({state:draftFormState(),yaw:viewer.yaw,pitch:viewer.pitch}));
  await page.evaluate(()=>{window.pickCalls=0;const pick=viewer.onPick;viewer.onPick=p=>{window.pickCalls++;pick(p);};});
  await page.mouse.click(overlay.x+67,overlay.y+75);
  await page.mouse.move(overlay.x+67,overlay.y+75);await page.mouse.down();await page.mouse.move(overlay.x+180,overlay.y+150,{steps:3});await page.mouse.up();
  assert.equal(await page.evaluate(()=>window.pickCalls),0);
  assert.deepEqual(await page.evaluate(()=>({state:draftFormState(),yaw:viewer.yaw,pitch:viewer.pitch})),beforeOverlay);
  const hit=await page.evaluate(()=>{
    const v=viewer.vertices;let best=null,area=-1;for(let i=0;i<v.length;i+=9){const p=[0,3,6].map(j=>viewer.project(v[i+j],v[i+j+1],v[i+j+2]));const a=Math.abs((p[1][0]-p[0][0])*(p[2][1]-p[0][1])-(p[2][0]-p[0][0])*(p[1][1]-p[0][1]));if(a>area){area=a;best=[p.reduce((s,q)=>s+q[0],0)/3,p.reduce((s,q)=>s+q[1],0)/3];}}const r=viewer.canvas.getBoundingClientRect();return [best[0]+r.left,best[1]+r.top];
  });
  await page.locator('#part-view').dispatchEvent('pointerdown',{clientX:hit[0],clientY:hit[1],pointerId:1});
  await page.locator('#part-view').dispatchEvent('pointercancel',{pointerId:1});
  await page.locator('#part-view').dispatchEvent('pointerup',{clientX:hit[0],clientY:hit[1],pointerId:1});
  assert.equal(await page.evaluate(()=>window.pickCalls),0);assert(await page.evaluate(()=>!!viewer.onPick));
  await page.mouse.click(...hit);await page.waitForFunction(()=>document.querySelector('#placement-status').textContent.startsWith('Region centre placed'));
  assert.equal(await page.evaluate(()=>viewer.regions.length),1);
  await page.locator('#return-helper').click();
  assert(await region.locator('[data-geometry="center_mm"][data-axis="0"]').evaluate(e=>e===document.activeElement));
  assert(await page.evaluate(()=>{const v=document.querySelector('#part-view').getBoundingClientRect(),p=document.querySelector('.preview').getBoundingClientRect(),e=document.querySelector('.editor').getBoundingClientRect();return v.top>=0&&v.bottom<=innerHeight&&p.right<=e.left;}));
  const centers=await region.locator('[data-geometry="center_mm"]').evaluateAll(fields=>fields.map(f=>f.value));
  assert(await page.locator('#cancel-placement').isHidden());
  const beforeCancel=await page.evaluate(()=>draftFormState());
  for(const action of ['button','escape']){
   await region.getByRole('button',{name:'Place centre on part'}).click();
   assert(await page.locator('#cancel-placement').isVisible());
   if(action==='button')await page.locator('#cancel-placement').click();else await page.keyboard.press('Escape');
   assert(await page.evaluate(()=>viewer.onPick===null&&viewer.canvas.style.cursor===''));
   assert(await page.locator('#cancel-placement').isHidden());
   assert.match(await page.locator('#placement-status').innerText(),/cancelled/);
   assert.equal(await page.evaluate(()=>draftFormState()),beforeCancel);
   assert(await page.locator('#part-view').evaluate(e=>e===document.activeElement));
  }
  for(const selector of ['[data-spatial]','#shell-only']){
   await region.getByRole('button',{name:'Place centre on part'}).click();
   const control=page.locator(selector),wasChecked=await control.isChecked();
   await control.setChecked(!wasChecked);
   assert(await page.evaluate(()=>viewer.onPick===null));assert(await page.locator('#cancel-placement').isHidden());
   await control.setChecked(wasChecked);
   assert.equal(await page.evaluate(()=>draftFormState()),beforeCancel);
  }
  await region.locator('[data-nudge-step]').selectOption('0.4');
  const sizes=await region.locator('[data-geometry="size_mm"]').evaluateAll(fields=>fields.map(f=>f.value));
  await region.getByRole('button',{name:'Place centre on part'}).click();assert(await page.evaluate(()=>!!viewer.onPick));
  await region.getByRole('button',{name:'Move X +',exact:true}).click();
  assert(await page.evaluate(()=>viewer.onPick===null&&viewer.canvas.style.cursor===''));
  assert(Math.abs(Number(await region.locator('[data-geometry="center_mm"][data-axis="0"]').inputValue())-Number(centers[0])-.4)<1e-6);
  assert.deepEqual(await region.locator('[data-geometry="size_mm"]').evaluateAll(fields=>fields.map(f=>f.value)),sizes);
  assert.match(await region.locator('[data-nudge-status]').innerText(),/along design X/);
  await region.getByRole('button',{name:'Place centre on part'}).click();assert(await page.evaluate(()=>!!viewer.onPick));
  await region.getByRole('button',{name:'Undo last centre move'}).click();
  assert(await page.evaluate(()=>viewer.onPick===null));
  assert.deepEqual(await region.locator('[data-geometry="center_mm"]').evaluateAll(fields=>fields.map(f=>f.value)),centers);
  await region.getByRole('button',{name:'Place centre on part'}).click();
  const cy=region.locator('[data-geometry="center_mm"][data-axis="1"]');await cy.fill('');
  assert(await page.evaluate(()=>viewer.onPick===null));
  await region.getByRole('button',{name:'Move X +',exact:true}).click();
  assert.equal(await cy.inputValue(),'');assert.match(await region.locator('[data-nudge-status]').innerText(),/Complete all three/);
  await cy.fill(centers[1]);assert(await region.getByRole('button',{name:'Undo last centre move'}).isDisabled());
  await region.getByRole('button',{name:'Place centre on part'}).click();
  await page.getByRole('button',{name:'facet-01',exact:true}).click();assert(await page.evaluate(()=>viewer.onPick===null));assert(await page.locator('#cancel-placement').isHidden());await page.locator('#rationale').fill('Alternative pose for the same reinforcement.');
  assert.deepEqual(await region.locator('[data-geometry="center_mm"]').evaluateAll(fields=>fields.map(f=>f.value)),centers);
  await region.locator('[data-geometry="size_mm"][data-axis="0"]').fill('0.5');await page.waitForFunction(()=>document.querySelector('#region-warnings').textContent.includes('0.84'));
  await region.locator('[data-geometry="size_mm"][data-axis="0"]').fill('10');
  const pending=page.waitForEvent('download');await page.locator('#export').click();const draft=JSON.parse(await fs.readFile(await(await pending).path(),'utf8'));
  assert.equal(draft.massing.helper_regions[0].geometry.frame,'design');assert.equal(draft.massing.helper_regions[0].geometry_status,'sketch');assert.deepEqual(draft.massing.helper_regions[0].keep_clear.interface_ids,['rear_seat']);
  await page.locator('#draft-file').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(draft))});await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));
  assert.deepEqual(await region.locator('[data-geometry="center_mm"]').evaluateAll(fields=>fields.map(f=>Number(f.value))),draft.massing.helper_regions[0].geometry.center_mm);
  await page.locator('#add-helper').click();const second=page.locator('.helper-region').last();
  await second.locator('[data-key="name"]').fill('Second helper');await second.locator('[data-spatial]').check();
  assert(await second.evaluate(e=>e.classList.contains('active-helper')));assert.match(await page.locator('#active-helper-status').innerText(),/Second helper/);
  assert(await page.evaluate(()=>viewer.regions.filter(r=>r.active).length===1&&viewer.regions.find(r=>r.active).name==='Second helper'));
  const firstId=await region.getAttribute('data-id');await page.locator('#preview-helper').selectOption(firstId);
  assert(await region.locator('[data-key="name"]').evaluate(e=>e===document.activeElement));assert(await region.evaluate(e=>e.classList.contains('active-helper')));
  await region.getByRole('button',{name:'Place centre on part'}).click();assert(await page.evaluate(()=>!!viewer.onPick));
  await second.locator('[data-key="name"]').focus();assert(await page.evaluate(()=>viewer.onPick===null));
  await second.getByRole('button',{name:'Remove region'}).click();assert.equal(await page.locator('#preview-helper').inputValue(),'');
  await region.getByRole('button',{name:'Duplicate region'}).click();
  const copy=page.locator('.helper-region').nth(1),copyId=await copy.getAttribute('data-id');
  assert.notEqual(copyId,firstId);assert.equal(await copy.locator('[data-key="name"]').inputValue(),'Seat backing copy');
  assert(await copy.locator('[data-key="name"]').evaluate(e=>e===document.activeElement));
  assert.deepEqual(await copy.locator('[data-geometry]').evaluateAll(fields=>fields.map(f=>f.value)),await region.locator('[data-geometry]').evaluateAll(fields=>fields.map(f=>f.value)));
  assert(await copy.locator('[data-interface-id="rear_seat"]').isChecked());
  assert.match(await page.locator('#region-warnings').innerText(),/identical planning boxes/);
  const copyDownload=page.waitForEvent('download');await page.locator('#export').click();
  const copied=JSON.parse(await fs.readFile(await(await copyDownload).path(),'utf8'));
  const [a,b]=copied.massing.helper_regions;assert.notEqual(a.id,b.id);
  assert.deepEqual({...b,id:a.id,name:a.name},a); // Exact independent planning intent, apart from identity/name.
  const oldX=await region.locator('[data-geometry="center_mm"][data-axis="0"]').inputValue();
  await copy.locator('[data-geometry="center_mm"][data-axis="0"]').fill(String(Number(oldX)+20));
  assert.equal(await region.locator('[data-geometry="center_mm"][data-axis="0"]').inputValue(),oldX);
  assert.match(await page.locator('#draft-edit-state').innerText(),/Changes since/);
  await copy.locator('[data-geometry="size_mm"][data-axis="0"]').fill('');
  await copy.getByRole('button',{name:'Duplicate region'}).click();
  assert.equal(await page.locator('.helper-region').nth(2).locator('[data-geometry="size_mm"][data-axis="0"]').inputValue(),'');
  if(process.env.FDM_PREVIEW_SCREENSHOT)await page.screenshot({path:process.env.FDM_PREVIEW_SCREENSHOT,fullPage:false});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  console.log('PASS spatial click placement, design-frame persistence across poses, size screen, interface refs, sketch export/reopen, mobile, console');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
