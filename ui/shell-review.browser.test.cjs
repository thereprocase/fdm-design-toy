const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({locale:'en-US'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(__dirname,'massing-review.html')).href);
 const fixture=name=>path.join(__dirname,'fixtures/seed-'+name+'.json');
 await page.locator('#review-draft').setInputFiles(fixture('draft'));
 await page.locator('#review-receipt').setInputFiles(fixture('export-report'));
 await page.waitForFunction(()=>document.querySelector('#review-status').textContent.startsWith('Receipt fingerprint matched'));
 assert(await page.locator('#review-shell').isDisabled());
 await page.locator('#review-slice').setInputFiles(fixture('slice-evidence'));
 await page.waitForFunction(()=>!document.querySelector('#review-shell').disabled);
 await page.locator('#review-shell').setInputFiles(fixture('project-shell-check'));
 await page.waitForFunction(()=>!document.querySelector('#shell-results').hidden);
 assert.match(await page.locator('#shell-summary').innerText(),/0.22% of 20000 measured samples/);
 assert.match(await page.locator('#shell-pairing').innerText(),/geometry pairing is not established/);
 assert.match(await page.locator('#shell-method').innerText(),/not structurally recorded/);
 const original=JSON.parse(fs.readFileSync(fixture('project-shell-check')));
 for(const [patch,message] of [[{gcode_sha256:'a'.repeat(64)},'G-code differs'],[{table_sha256:'b'.repeat(64)},'table_sha256 differs'],[{result:{...original.result,metrics:{...original.result.metrics,samples:1}}},'counts differ']]){
  await page.locator('#review-shell').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...original,...patch}))});
  await page.waitForFunction(message=>document.querySelector('#shell-status').textContent.includes(message),message);
  assert(await page.locator('#shell-results').isVisible());assert.match(await page.locator('#shell-summary').innerText(),/0.22%/);
 }
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('#review-slice').setInputFiles([]);await page.locator('#review-slice').setInputFiles(fixture('slice-evidence'));
 await page.waitForFunction(()=>document.querySelector('#shell-results').hidden);
 assert.deepEqual(errors,[]);console.log('PASS shell G-code/pose pairing, legacy provenance disclosure, bad receipt retention, sample accounting, invalidation, mobile');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
