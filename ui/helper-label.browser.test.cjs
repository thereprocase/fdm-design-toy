const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const p=await browser.newPage({viewport:{width:390,height:844}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
 await p.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json'));
 await p.locator('#draft-file').setInputFiles(path.join(__dirname,'fixtures/seed-draft.json'));await p.waitForFunction(()=>document.querySelectorAll('.helper-region').length===6);
 await p.locator('#mesh-file').setInputFiles(process.env.FDM_PREVIEW_MESH);await p.waitForFunction(()=>document.getElementById('mesh-status').textContent.startsWith('Mesh fingerprint matched'));
 const name=p.locator('.helper-region').first().locator('[data-key="name"]');await name.fill('Seat backing — preserve this full descriptive helper name');
 const before=await p.evaluate(()=>workSnapshot());
 // Observe the real canvas draw call, including measured font width.
 await p.evaluate(()=>{window.drawnLabels=[];const ctx=viewer.canvas.getContext('2d'),fill=ctx.fillText.bind(ctx);ctx.fillText=(text,x,y,...rest)=>{if(text.startsWith('Editing: '))window.drawnLabels.push({text,x,y,width:ctx.measureText(text).width});return fill(text,x,y,...rest);};});
 for(const view of ['#view-iso','#view-top','#view-x']){
  await p.locator(view).click();await p.waitForFunction(()=>!viewer.pending);
  const bounds=await p.evaluate(()=>({label:window.drawnLabels.at(-1),width:viewer.canvas.clientWidth,height:viewer.canvas.clientHeight}));
  assert(bounds.label);assert(bounds.label.x>=8&&bounds.label.x+bounds.label.width<=bounds.width-8);assert(bounds.label.y<bounds.height-73);assert(bounds.label.text.endsWith('…'));
  assert(bounds.label.x>=138||bounds.label.y-15>=132);
 }
 assert.match(await p.locator('#preview-helper option:checked').innerText(),/preserve this full descriptive helper name/);assert.deepEqual(await p.evaluate(()=>workSnapshot()),before);
 await p.locator('#view-iso').click();await p.waitForFunction(()=>!viewer.pending);
 if(process.env.FDM_LABEL_SCREENSHOT)await p.locator('#part-view').screenshot({path:process.env.FDM_LABEL_SCREENSHOT});
 assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log('PASS real mobile helper labels remain inside canvas and outside keys across views; full name and draft preserved');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
