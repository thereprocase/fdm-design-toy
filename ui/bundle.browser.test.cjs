const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict'),fixture=require('./evidence-bundle-fixture.cjs');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({locale:'en-US'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(__dirname,'massing-review.html')).href);
 assert(await page.locator('#review-bundle').isDisabled());
 await page.locator('#review-draft').setInputFiles(path.join(__dirname,'fixtures/seed-draft.json'));
 await page.locator('#review-receipt').setInputFiles(path.join(__dirname,'fixtures/seed-export-report.json'));
 await page.waitForFunction(()=>!document.querySelector('#review-bundle').disabled);
 const f=fixture(),files=()=>[{name:'evidence-bundle.json',buffer:Buffer.from(JSON.stringify(f.manifest))},...f.files].map(x=>({...x,mimeType:'application/json'}));
 await page.locator('#review-bundle').setInputFiles(files());
 await page.waitForFunction(()=>document.querySelector('#bundle-status').textContent.startsWith('All five'));
 assert.match(await page.locator('#shell-comparison-status').innerText(),/0 percentage points/);
 assert.match(await page.locator('#bundle-bridges').innerText(),/122.1 mm/);
 assert.match(await page.locator('#bundle-bridges').innerText(),/Ceiling model maxima: external not recorded; internal not recorded/);
 // Synthetic withholding metadata exercises display, not measured producer evidence.
 f.manifest.paired={'shell-check':{withheld:['Slicer profile differs <b>literal</b>','Raster methods differ']},'bridge-check':{withheld:['Bridge limits differ']}};
 await page.locator('#review-bundle').setInputFiles(files());
 await page.waitForFunction(()=>document.querySelector('#bundle-summary').textContent.includes('Slicer profile differs'));
 assert.match(await page.locator('#bundle-summary').innerText(),/Slicer profile differs <b>literal<\/b>/);
 assert.deepEqual(await page.locator('#bundle-withheld li').allTextContents(),['Slicer profile differs <b>literal</b>','Raster methods differ','Bridge limits differ']);
 assert.equal(await page.locator('#bundle-withheld b').count(),0);
 assert.match(await page.locator('#shell-comparison-status').innerText(),/Producer withheld/);
 assert.doesNotMatch(await page.locator('#shell-comparison-status').innerText(),/percentage points/);
 f.manifest.paired={};await page.locator('#review-bundle').setInputFiles(files());
 await page.waitForFunction(()=>document.querySelector('#bundle-withheld').hidden);
 assert.match(await page.locator('#shell-comparison-status').innerText(),/0 percentage points/);
 // Synthetic additive ceiling measurement, with a freshly computed matching file hash.
 const ceiling=JSON.parse(f.files[3].buffer);ceiling.result.metrics.max_ceiling_span_external_mm=7.8;ceiling.result.metrics.max_ceiling_span_internal_mm=15.7;
 f.files[3].buffer=Buffer.from(JSON.stringify(ceiling));f.manifest.receipts[3].sha256=fixture.sha(f.files[3].buffer);
 await page.locator('#review-bundle').setInputFiles(files());
 await page.waitForFunction(()=>document.querySelector('#bundle-bridges').textContent.includes('external 7.8 mm; internal 15.7 mm'));
 assert.match(await page.locator('#bundle-bridges').innerText(),/Project bridges · T FAIL/);
 assert.match(await page.locator('#bundle-bridges').innerText(),/does not override the recorded strand verdict/);
 assert.match(await page.locator('#bundle-bridges').innerText(),/maxima need not occur on the same road/);
 f.files[0].buffer=Buffer.from('{}');await page.locator('#review-bundle').setInputFiles(files());
 await page.waitForFunction(()=>document.querySelector('#bundle-status').textContent.includes('fingerprint differs'));
 assert(await page.locator('#bundle-results').isVisible());assert.match(await page.locator('#shell-comparison-status').innerText(),/0 percentage points/);
 // Exact files from the real producer run; no receipt fields or hashes changed.
 const fs=require('node:fs'),dir=path.join(__dirname,'fixtures/seed-evidence-bundle');
 assert.equal(fixture.sha(fs.readFileSync(path.join(dir,'evidence-bundle.json'))),'9ac5182352d61b8e759c180b9268cf2e04d781db00a17e79dc79d1ed3493f303');
 await page.locator('#review-bundle').setInputFiles(fs.readdirSync(dir).filter(n=>n.endsWith('.json')).map(n=>path.join(dir,n)));
 await page.waitForFunction(()=>document.querySelector('#bundle-status').textContent.startsWith('All five'));
 const real=JSON.parse(await page.locator('#bundle-provenance').textContent());
 assert.equal(real.receipts.find(r=>r.check==='bridge-check'&&r.slice_kind==='project').sha256,'e82806aa7543dff15d94459ab1eff1d7af221bd06a871ad905ba687eb46fd76b');
 assert.match(await page.locator('#bundle-bridges').innerText(),/Project bridges · T FAIL/);
 assert.match(await page.locator('#bundle-bridges').innerText(),/Shell-only baseline bridges · T FAIL/);
 assert.equal(await page.locator('#bundle-bridges [data-bridge-remedy]').count(),2);
 assert.match(await page.locator('#bundle-bridges [data-bridge-remedy]').first().innerText(),/no verified helper-edit remedy/);
 assert.deepEqual(await page.locator('#bundle-bridges [data-bridge-remedy]').first().locator('a').evaluateAll(a=>a.map(x=>x.href)),['https://github.com/thereprocase/fdm-design-toy/issues/9','https://github.com/thereprocase/fdm-design-toy/issues/12','https://github.com/thereprocase/fdm-design-toy/issues/17#issuecomment-6049963530']);

 assert.match(await page.locator('#bundle-bridges').innerText(),/internal: 122.1 mm \(limit 18 mm\)/);
 assert.match(await page.locator('#shell-comparison-status').innerText(),/0 percentage points/);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('#review-shell').setInputFiles(path.join(__dirname,'fixtures/seed-project-shell-check-v03.json'));
 await page.waitForFunction(()=>document.querySelector('#bundle-results').hidden);
 await page.locator('#review-draft').setInputFiles(path.join(__dirname,'fixtures/revised-draft.json'));
 await page.waitForFunction(()=>document.querySelector('#review-bundle').disabled);
 assert.deepEqual(errors,[]);console.log('PASS synthetic and exact real bundle import, bridge failures retained, fingerprint rejection, retention, manual override invalidation and mobile');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
