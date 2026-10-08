const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const p=await browser.newPage({viewport:{width:390,height:844}}),errors=[];let dialogs=0;
 p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>{dialogs++;return d.accept();});
 await p.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
 const table=path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json'),raw=JSON.parse(fs.readFileSync(table,'utf8'));
 await p.locator('#table-file').setInputFiles(table);await p.locator('#draft-file').setInputFiles(path.join(__dirname,'fixtures/seed-draft.json'));
 await p.waitForFunction(()=>document.querySelectorAll('.helper-region').length===6);
 await p.locator('#mesh-file').setInputFiles(process.env.FDM_PREVIEW_MESH);await p.waitForFunction(()=>document.getElementById('mesh-status').textContent.startsWith('Mesh fingerprint matched'));
 await p.locator('#pin-reference').click();await p.getByRole('button',{name:'facet-01',exact:true}).click();await p.locator('#rationale').fill('Keep this unsaved planning note');
 const state=()=>p.evaluate(()=>({work:workSnapshot(),fingerprint,meshHash,selected:selected.id,dirty:hasDraftEdits(),source:Array.from(new Uint8Array(sourceTableBytes))}));
 const before=await state(),initialDialogs=dialogs;
 const mutations=[
  t=>{t.interfaces[0].support={toString:null};},
  t=>{t.keep_outs[0].rule={toString:null};},
  t=>{t.problem={id:{toString:null}};},
  t=>{t.candidates[0].columns.height_mm.value={toString:null};},
  t=>{t.candidates[0].columns.t_credited_mm3={value:1,fidelity:42};},
  t=>{t.candidates[0].reasons=[{toString:null}];},
 ];
 for(const mutate of mutations){const bad=structuredClone(raw);mutate(bad);
  await p.locator('#table-file').setInputFiles({name:'malformed-table.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
  await p.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Could not load table'));
  assert.equal(dialogs,initialDialogs,'invalid table must be rejected before prompting to discard work');assert.deepEqual(await state(),before);
  assert.match(await p.locator('#status').innerText(),/previous table and current draft remain available/);
 }
 // The original exact table remains downloadable after refusals.
 await p.locator('#handoff').evaluate(e=>e.open=true);
 const download=p.waitForEvent('download');await p.locator('#download-table').click();assert.deepEqual(fs.readFileSync(await (await download).path()),fs.readFileSync(table));
 await p.locator('#table-file').setInputFiles(table);await p.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Loaded'));
 assert.equal(dialogs,initialDialogs+1);assert.equal(await p.locator('.helper-region').count(),1);assert.equal(await p.locator('.helper-region [data-key="name"]').inputValue(),'');
 await p.getByRole('button',{name:'facet-00',exact:true}).click();assert.equal(await p.locator('#pose-name').innerText(),'facet-00');
 assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log('PASS malformed table refusal preserves six helpers, notes, comparison, mesh and exact source without discard prompt; valid replacement remains usable');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
