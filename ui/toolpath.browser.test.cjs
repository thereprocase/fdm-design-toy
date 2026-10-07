const fs=require('node:fs');
const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
 await page.getByRole('button',{name:'facet-00',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/4,344/);assert.match(await page.locator('#toolpath-settings').innerText(),/support 1, threshold 45/);assert.match(await page.locator('#credited-scope').innerText(),/support excluded/);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/Not checked/);assert.match(await page.locator('#toolpath-settings').innerText(),/No pose slice/);assert.equal(await page.locator('#credited-scope').innerText(),'');
 await page.locator('#sliced-only').check();assert.equal(await page.locator('#rows tr').count(),2);assert.match(await page.locator('#pose-count').innerText(),/Selected pose facet-02 is hidden/);await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/8,596/);
 // Known-order comparison fixture: zero is measured, unchecked numeric values stay last.
 await page.locator('#sliced-only').uncheck();
 const table=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json')));
 const base=table.candidates[0];
 table.candidates=['large','zero','unknown','tie'].map((id,i)=>({...structuredClone(base),id,columns:{...structuredClone(base.columns),
  t_support_segments:{value:[9,0,-1,9][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  F_L_max:{value:[.3,.1,null,.3][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  contact_mm2:{value:[100,20,null,100][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  height_mm:{value:[30,10,null,30][i],verdict:i===2?'NOT_CHECKED':'PASS'}}}));
 await page.locator('#table-file').setInputFiles({name:'sort-fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(table))});
 await page.getByRole('button',{name:'large',exact:true}).click();await page.locator('#rationale').fill('Keep this choice while comparing.');
 const order=()=>page.locator('#rows button').allTextContents();
 for(const key of ['t_support_segments','F_L_max','height_mm']){
  await page.locator('#pose-sort').selectOption(key);assert.deepEqual(await order(),['zero','large','tie','unknown']);
 }
 await page.locator('#pose-sort').selectOption('contact_mm2');assert.deepEqual(await order(),['large','tie','zero','unknown']);
 await page.locator('#pose-sort').selectOption('analysis');assert.deepEqual(await order(),['large','zero','unknown','tie']);
 assert.equal(await page.locator('#pose-name').innerText(),'large');assert.equal(await page.locator('#rationale').inputValue(),'Keep this choice while comparing.');
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log('PASS measured pose support, fidelity/settings, missing slice remains unchecked, slice filter, mobile, console');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
