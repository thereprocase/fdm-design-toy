const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
 await page.getByRole('button',{name:'facet-00',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/4,344/);assert.match(await page.locator('#toolpath-settings').innerText(),/support 1, threshold 45/);assert.match(await page.locator('#credited-scope').innerText(),/support excluded/);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/Not checked/);assert.match(await page.locator('#toolpath-settings').innerText(),/No pose slice/);assert.equal(await page.locator('#credited-scope').innerText(),'');
 await page.locator('#sliced-only').check();assert.equal(await page.locator('#rows tr').count(),2);assert.match(await page.locator('#pose-count').innerText(),/Selected pose facet-02 is hidden/);await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/8,596/);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log('PASS measured pose support, fidelity/settings, missing slice remains unchecked, slice filter, mobile, console');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
