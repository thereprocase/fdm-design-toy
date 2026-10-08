const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const p=await browser.newPage({viewport:{width:390,height:844}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
 const url=pathToFileURL(path.join(__dirname,'index.html')).href,table=path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json'),draftPath=path.join(__dirname,'fixtures/seed-draft.json'),original=JSON.parse(fs.readFileSync(draftPath));
 async function download(button){const event=p.waitForEvent('download');await p.locator(button).click();const file=await event;return fs.readFileSync(await file.path());}
 await p.goto(url);await p.locator('#table-file').setInputFiles(table);await p.locator('#draft-file').setInputFiles(draftPath);await p.waitForFunction(()=>document.querySelectorAll('.helper-region').length===6);
 const size=p.locator('.helper-region').first().locator('[data-geometry="size_mm"][data-axis="0"]'),value=await size.inputValue();await size.fill('');
 const rationale=original.orientation.designer_decision.rationale+'\nRecovered unfinished draft for review.';await p.locator('#rationale').fill(rationale);
 await p.locator('#work-snapshot').evaluate(e=>e.open=true);const snapshot=await download('#save-work');
 await p.goto(url);await p.locator('#table-file').setInputFiles(table);await p.locator('#work-file').setInputFiles({name:'unfinished-work.json',mimeType:'application/json',buffer:snapshot});await p.waitForFunction(()=>document.getElementById('work-file').value==='');
 assert.equal(await size.inputValue(),'');assert.equal(await p.locator('#rationale').inputValue(),rationale);
 await p.locator('#export').click();assert.match(await p.locator('#export-status').innerText(),/finite|positive/i);assert.equal(await size.inputValue(),'');
 await size.fill(value);const final=await download('#export'),draft=JSON.parse(final);
 assert.equal(draft.schema,'fdmgen.massing-plan.v0.3');const normaliseRefs=m=>{const copy=structuredClone(m);for(const h of copy.helper_regions)for(const key of ['interface_ids','keep_out_ids'])h.keep_clear[key].sort();return copy;};assert.deepEqual(normaliseRefs(draft.massing),normaliseRefs(original.massing));assert.deepEqual(draft.source,original.source);assert.deepEqual(draft.proposal,original.proposal);assert.equal(draft.orientation.designer_decision.rationale,rationale);
 const tableBytes=await download('#download-table');assert(tableBytes.equals(fs.readFileSync(table)));
 if(process.env.FDM_RECOVERY_OUT){fs.mkdirSync(process.env.FDM_RECOVERY_OUT,{recursive:true});for(const [name,bytes] of [['work.json',snapshot],['draft.json',final],['table.json',tableBytes]])fs.writeFileSync(path.join(process.env.FDM_RECOVERY_OUT,name),bytes);}
 assert.deepEqual(errors,[]);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 console.log('PASS actual incomplete snapshot -> reload -> validation refusal -> completed draft + exact table; six helper inputs and proposal unchanged');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
