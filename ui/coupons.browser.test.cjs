const {chromium}=require('playwright'),path=require('node:path'),fs=require('node:fs/promises'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const dir=path.join(__dirname,'../tests/fixtures/coupons');await page.goto(pathToFileURL(path.join(__dirname,'coupons.html')).href);
 await page.locator('#plate-file').setInputFiles(path.join(dir,'ladder-plate.json'));await page.waitForFunction(()=>!document.querySelector('#receipt-files').disabled);
 await page.locator('#receipt-files').setInputFiles(['slice-evidence-support45.json','slice-evidence-nosupport.json'].map(x=>path.join(dir,x)));
 await page.waitForFunction(()=>!document.querySelector('#coupon-workspace').hidden);
 assert.match(await page.locator('#slicer-settings').innerText(),/45/);assert.match(await page.locator('#rung-metrics').innerText(),/1,058/);
 await page.locator('#receipt-choice').selectOption('1');assert.match(await page.locator('#receipt-note').innerText(),/Support disabled/);
 assert.match(await page.locator('#slicer-settings').innerText(),/30/);assert.match(await page.locator('#rung-metrics').innerText(),/Support segments\n0/);
 await page.locator('#rung-map [aria-label="brg-06"]').focus();await page.keyboard.press('Enter');assert.match(await page.locator('#rung-title').innerText(),/brg-06/);
 const bad=JSON.parse(await fs.readFile(path.join(dir,'slice-evidence-support45.json'),'utf8'));bad.plate.sha256='0'.repeat(64);
 await page.locator('#receipt-files').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});await page.waitForFunction(()=>document.querySelector('#coupon-status').textContent.includes('Could not pair'));
 assert.match(await page.locator('#receipt-note').innerText(),/Support disabled/);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 if(process.env.FDM_COUPON_SCREENSHOT)await page.screenshot({path:process.env.FDM_COUPON_SCREENSHOT,fullPage:true});
 console.log('PASS coupon hash pairing, settings/outcomes switch, keyboard rung selection, mismatch preserves valid data, mobile overflow, console');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
