const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs/promises'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[],dialogs=[];let accept=false;
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{dialogs.push(d.message());await(accept?d.accept():d.dismiss());});
 const dir=path.join(__dirname,'fixtures/orient-evidence'),files=(await fs.readdir(dir)).filter(n=>n.endsWith('.json')).map(n=>path.join(dir,n));
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
 await page.locator('#orientation-bundle-options > summary').click();
 await page.locator('#orientation-bundle-files').setInputFiles(path.join(dir,'orient-evidence.json'));
 await page.waitForFunction(()=>document.querySelector('#orientation-bundle-status').textContent.includes('Missing orientation evidence files'));
 assert(await page.locator('#workspace').isHidden());assert.equal(dialogs.length,0);
 await page.locator('#orientation-bundle-files').setInputFiles(files);
 await page.waitForFunction(()=>document.querySelector('#orientation-bundle-status').textContent.startsWith('Complete bundle verified'));
 assert.match(await page.locator('#orientation-bundle-count').innerText(),/2 pose slices; 4 receipt fingerprints checked; 2 FAIL/);
 assert.equal(await page.locator('[data-bundle-pose]').count(),2);
 assert.equal(await page.locator('[data-process-profile]').count(),4);
 assert((await page.locator('[data-process-profile]').allTextContents()).every(v=>v==='Recorded process profile: Part P1S ASA 4w 8-skin screen'));

 assert.match(await page.locator('#orientation-bundle-scope').innerText(),/not opened by this browser/);
 await page.getByRole('button',{name:'Review facet-01',exact:true}).click();
 assert.equal(await page.locator('#pose-name').innerText(),'facet-01');assert.match(await page.locator('#pose-bridges').innerText(),/52.2 mm/);
 // Reopen the identical paths without manually emptying the picker.
 accept=true;
 await page.locator('#orientation-bundle-files').setInputFiles(files);
 await page.waitForFunction(()=>document.querySelector('#pose-name').textContent==='Choose a candidate');
 assert.equal(await page.locator('#orientation-bundle-files').inputValue(),'');
 assert.equal(dialogs.length,1);dialogs.length=0;accept=false;
 await page.getByRole('button',{name:'Review facet-01',exact:true}).click();
 await page.locator('#handoff > summary').click();
 const download=page.waitForEvent('download');await page.locator('#download-table').click();
 assert.deepEqual(await fs.readFile(await(await download).path()),await fs.readFile(path.join(dir,'orientation-table.enriched.json')));
 const identities=await page.locator('#orientation-bundle-manifest').textContent();
 await page.locator('#draft-file').setInputFiles(path.join(__dirname,'fixtures/seed-draft.json'));
 await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.includes('different orientation table'));
 assert.equal(await page.locator('#pose-name').innerText(),'facet-01');
 await page.locator('#walls').fill('7');await page.locator('#rationale').fill('Keep these pending edits');
 const before=await page.evaluate(()=>draftFormState());
 const bad=[];
 for(const p of files){let b=await fs.readFile(p);if(path.basename(p)==='facet-01-shell-only.shell-check.json')b=Buffer.concat([b,Buffer.from(' ')]);bad.push({name:path.basename(p),mimeType:'application/json',buffer:b});}
 await page.locator('#orientation-bundle-files').setInputFiles(bad);
 await page.waitForFunction(()=>document.querySelector('#orientation-bundle-status').textContent.includes('fingerprint differs'));
 assert.equal(dialogs.length,0);assert.equal(await page.evaluate(()=>draftFormState()),before);assert.equal(await page.locator('#orientation-bundle-manifest').textContent(),identities);
 await page.locator('#orientation-bundle-files').setInputFiles(files);
 await page.waitForFunction(()=>document.querySelector('#orientation-bundle-status').textContent.includes('replacement cancelled'));
 assert.equal(dialogs.length,1);assert.equal(await page.evaluate(()=>draftFormState()),before);assert.equal(await page.locator('#orientation-bundle-manifest').textContent(),identities);
 accept=true;await page.locator('#orientation-bundle-files').setInputFiles(files);
 await page.waitForFunction(()=>document.querySelector('#orientation-bundle-status').textContent.startsWith('Complete bundle verified'));
 assert.equal(await page.locator('#walls').inputValue(),'4');assert.equal(await page.evaluate(()=>selected),null);
 // A later ordinary table import removes the old bundle verification summary.
 await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
 await page.waitForFunction(()=>document.querySelector('#orientation-bundle-summary').hidden);
 assert.match(await page.locator('#orientation-bundle-status').innerText(),/No orientation bundle verified/);
 await page.locator('#orientation-bundle-files').setInputFiles(files);
 await page.waitForFunction(()=>!document.querySelector('#orientation-bundle-summary').hidden);
 await page.setViewportSize({width:390,height:844});
 await page.locator('#orientation-bundle-summary > details > summary').click();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 console.log('PASS real orientation bundle atomic import, receipt failures, exact table download, root draft refusal, dirty cancellation, retention and mobile');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
