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
  const checkReturn=async selector=>{
    const state=await page.evaluate(()=>draftFormState());
    await region.locator('.helper-editor summary').click();
    assert.equal(await region.locator('.helper-editor').evaluate(e=>e.open),false);
    await page.locator('#return-helper').focus();await page.keyboard.press('Enter');
    assert(await region.locator('.helper-editor').evaluate(e=>e.open));
    const target=region.locator(selector).first();
    assert(await target.evaluate(e=>e===document.activeElement));
    assert(await target.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}));
    assert.equal(await page.evaluate(()=>draftFormState()),state);
  };
  await page.setViewportSize({width:390,height:844});
  await checkReturn('[data-geometry="center_mm"]');
  await region.locator('[data-spatial]').uncheck();
  await checkReturn('[data-key="name"]');
  await region.locator('[data-spatial]').check();
  await page.setViewportSize({width:1300,height:1000});
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
  const beforeGeometryLayout=await page.evaluate(()=>draftFormState());
  for(const width of [1300,390]){
    await page.setViewportSize({width,height:844});
    const centreGroup=region.getByRole('group',{name:'Box centre — design frame'});
    const sizeGroup=region.getByRole('group',{name:'Box dimensions — design frame'});
    assert.equal(await centreGroup.locator('input').count(),3);
    assert.equal(await sizeGroup.locator('input').count(),3);
    const centreZ=await centreGroup.locator('[data-axis="2"]').boundingBox();
    const sizeX=await sizeGroup.locator('[data-axis="0"]').boundingBox();
    assert(sizeX.y>=centreZ.y+centreZ.height,'Dimensions start below every centre coordinate');
    assert.deepEqual(await page.evaluate(()=>draftFormState()),beforeGeometryLayout);
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
  await page.mouse.click(overlay.x+overlay.width-40,overlay.y+overlay.height-40);
  assert.equal(await page.evaluate(()=>window.pickCalls),0);
  assert.deepEqual(await page.evaluate(()=>({state:draftFormState(),yaw:viewer.yaw,pitch:viewer.pitch})),beforeOverlay);
  const hit=await page.evaluate(()=>{
    const v=viewer.vertices;let best=null,area=-1;for(let i=0;i<v.length;i+=9){const p=[0,3,6].map(j=>viewer.project(v[i+j],v[i+j+1],v[i+j+2]));const a=Math.abs((p[1][0]-p[0][0])*(p[2][1]-p[0][1])-(p[2][0]-p[0][0])*(p[1][1]-p[0][1]));if(a>area){area=a;best=[p.reduce((s,q)=>s+q[0],0)/3,p.reduce((s,q)=>s+q[1],0)/3];}}const r=viewer.canvas.getBoundingClientRect();return [best[0]+r.left,best[1]+r.top];
  });
  const beforeAuxiliary=await page.evaluate(()=>({form:draftFormState(),yaw:viewer.yaw,pitch:viewer.pitch}));
  for(const button of ['right','middle']){
    await page.mouse.click(...hit,{button});
    await page.mouse.move(...hit);await page.mouse.down({button});await page.mouse.move(hit[0]+20,hit[1],{steps:2});await page.mouse.up({button});
  }
  await page.locator('#part-view').dispatchEvent('pointerdown',{clientX:hit[0],clientY:hit[1],pointerId:99,isPrimary:false,button:0});
  await page.locator('#part-view').dispatchEvent('pointermove',{clientX:hit[0]+20,clientY:hit[1],pointerId:99,isPrimary:false});
  await page.locator('#part-view').dispatchEvent('pointerup',{clientX:hit[0],clientY:hit[1],pointerId:99,isPrimary:false,button:0});
  assert.equal(await page.evaluate(()=>window.pickCalls),0);
  assert.deepEqual(await page.evaluate(()=>({form:draftFormState(),yaw:viewer.yaw,pitch:viewer.pitch})),beforeAuxiliary);
  await page.locator('#part-view').dispatchEvent('pointerdown',{clientX:hit[0],clientY:hit[1],pointerId:1,isPrimary:true});
  await page.locator('#part-view').dispatchEvent('pointercancel',{pointerId:1,isPrimary:true});
  await page.locator('#part-view').dispatchEvent('pointerup',{clientX:hit[0],clientY:hit[1],pointerId:1,isPrimary:true});
  assert.equal(await page.evaluate(()=>window.pickCalls),0);assert(await page.evaluate(()=>!!viewer.onPick));
  const beforeOrbit=await page.evaluate(()=>draftFormState());
  await page.mouse.move(...hit);await page.mouse.down();
  await page.mouse.move(hit[0]+30,hit[1],{steps:3});await page.mouse.move(...hit,{steps:3});await page.mouse.up();
  assert.equal(await page.evaluate(()=>window.pickCalls),0);
  assert.equal(await page.evaluate(()=>draftFormState()),beforeOrbit);assert(await page.evaluate(()=>!!viewer.onPick));
  await page.locator('#view-top').click();await page.waitForFunction(()=>!viewer.pending);
  await page.mouse.click(...hit);await page.waitForFunction(()=>document.querySelector('#placement-status').textContent.startsWith('Region centre placed'));
  assert.equal(await page.evaluate(()=>viewer.regions.length),1);
  await region.getByRole('button',{name:'Undo last centre move'}).click();
  assert.equal(await page.evaluate(()=>draftFormState()),beforeOverlay.state);
  assert(await region.getByRole('button',{name:'Undo last centre move'}).isDisabled());
  await region.locator('[data-geometry="center_mm"][data-axis="0"]').fill('');
  const blankBeforePick=await page.evaluate(()=>draftFormState());
  await region.getByRole('button',{name:'Place centre on part'}).click();await page.mouse.click(...hit);
  await page.waitForFunction(()=>document.querySelector('#placement-status').textContent.startsWith('Region centre placed'));
  await region.getByRole('button',{name:'Undo last centre move'}).click();
  assert.equal(await page.evaluate(()=>draftFormState()),blankBeforePick);
  assert.equal(await region.locator('[data-geometry="center_mm"][data-axis="0"]').inputValue(),'');
  await region.getByRole('button',{name:'Place centre on part'}).click();await page.mouse.click(...hit);
  await page.waitForFunction(()=>document.querySelector('#placement-status').textContent.startsWith('Region centre placed'));
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
  const warningState=await page.evaluate(()=>draftFormState());
  await region.locator('.helper-editor').evaluate(e=>e.open=false);
  await page.locator('#region-warnings li').filter({hasText:'an edge is below'}).getByRole('button',{name:'Edit Seat backing',exact:true}).click();
  assert(await region.locator('.helper-editor').evaluate(e=>e.open));
  assert(await region.locator('[data-geometry="size_mm"][data-axis="0"]').evaluate(e=>e===document.activeElement));
  assert.equal(await page.evaluate(()=>draftFormState()),warningState);

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
  const duplicateWarning=page.locator('#region-warnings li').filter({hasText:'identical planning boxes'});
  assert.equal(await duplicateWarning.getByRole('button').count(),2);
  const beforeWarningNavigation=await page.evaluate(()=>draftFormState());
  await duplicateWarning.getByRole('button',{name:'Edit Seat backing',exact:true}).click();
  assert(await region.evaluate(e=>e.classList.contains('active-helper')));
  await duplicateWarning.getByRole('button',{name:'Edit Seat backing copy',exact:true}).click();
  assert(await copy.evaluate(e=>e.classList.contains('active-helper')));
  assert.equal(await page.evaluate(()=>draftFormState()),beforeWarningNavigation);
  const drawnHelperLabels=()=>page.evaluate(()=>{
    const ctx=viewer.canvas.getContext('2d'),original=ctx.fillText,labels=[];
    ctx.fillText=function(value,...args){if(value.includes('Seat backing'))labels.push(value);return original.call(this,value,...args);};
    try{viewer.draw();}finally{ctx.fillText=original;}return labels;
  });
  assert.deepEqual(await drawnHelperLabels(),['Editing: Seat backing copy']);
  await page.locator('#all-helper-labels').check();
  assert.deepEqual(await drawnHelperLabels(),['Seat backing','Editing: Seat backing copy']);
  await page.locator('#all-helper-labels').uncheck();
  assert.deepEqual(await drawnHelperLabels(),['Editing: Seat backing copy']);
  assert.equal(await page.evaluate(()=>viewer.regions.length),2);
  assert.equal(await page.evaluate(()=>draftFormState()),beforeWarningNavigation);


  const scaleLabels=()=>page.evaluate(()=>{
    const labels=[],ctx=viewer.canvas.getContext('2d'),original=ctx.fillText;
    ctx.fillText=function(value,...args){if(/^[\d.,]+ mm$/.test(value))labels.push(value);return original.call(this,value,...args);};
    try{viewer.draw();}finally{ctx.fillText=original;}return labels;
  });
  const wholeScale=await scaleLabels();assert.equal(wholeScale.length,1);
  const beforeFrame=await page.evaluate(()=>({form:draftFormState(),pose:selected.id,vertices:Array.from(viewer.vertices)}));
  await page.locator('#focus-helper').click();await page.waitForFunction(()=>!viewer.pending);
  assert.equal(await page.evaluate(()=>viewer.focusId),await copy.getAttribute('data-id'));
  const focusedScale=await scaleLabels();assert.equal(focusedScale.length,1);assert.notDeepEqual(focusedScale,wholeScale);
  const framing=await page.evaluate(()=>{
    const region=viewer.regions.find(r=>r.active),c=transformMesh(region.geometry.center_mm,viewer.R,viewer.t),p=viewer.project(...c);
    return {x:p[0],y:p[1],width:viewer.canvas.clientWidth,height:viewer.canvas.clientHeight};
  });
  assert(Math.abs(framing.x-framing.width/2)<1e-8&&Math.abs(framing.y-framing.height/2)<1e-8);
  assert.deepEqual(await page.evaluate(()=>({form:draftFormState(),pose:selected.id,vertices:Array.from(viewer.vertices)})),beforeFrame);
  await page.locator('#view-whole').click();assert.equal(await page.evaluate(()=>viewer.focusId),null);
  await page.locator('#focus-helper').click();await page.locator('#view-top').click();assert.equal(await page.evaluate(()=>viewer.focusId),null);
  await page.locator('#focus-helper').click();await copy.locator('[data-spatial]').uncheck();
  assert(await page.locator('#focus-helper').isDisabled());assert.equal(await page.evaluate(()=>viewer.focusId),null);
  await copy.locator('[data-spatial]').check();
  assert.deepEqual(await page.evaluate(()=>({form:draftFormState(),pose:selected.id,vertices:Array.from(viewer.vertices)})),beforeFrame);

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
