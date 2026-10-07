const fs=require('node:fs');
const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
 await page.getByRole('button',{name:'facet-00',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/4,344/);assert.match(await page.locator('#toolpath-settings').innerText(),/support 1, threshold 45/);assert.match(await page.locator('#credited-scope').innerText(),/support excluded/);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/Not checked/);assert.match(await page.locator('#toolpath-settings').innerText(),/No pose slice/);assert.equal(await page.locator('#credited-scope').innerText(),'');
 assert.equal(await page.locator('#pose-shell-summary').innerText(),'Not checked');
 assert.match(await page.locator('#pose-bridges').innerText(),/Not checked/);
 await page.locator('#sliced-only').check();assert.equal(await page.locator('#rows tr').count(),2);assert.match(await page.locator('#pose-count').innerText(),/Selected pose facet-02 is hidden/);await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/8,596/);
 // Known-order comparison fixture: zero is measured, unchecked numeric values stay last.
 await page.locator('#sliced-only').uncheck();
 const table=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json')));
 const base=table.candidates[0];
 table.candidates=['large','zero','unknown','tie'].map((id,i)=>({...structuredClone(base),id,feasible:i!==2,columns:{...structuredClone(base.columns),
  t_support_segments:{value:[9,0,-1,9][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  F_L_max:{value:[.3,.1,null,.3][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  contact_mm2:{value:[100,20,null,100][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  height_mm:{value:[30,10,null,30][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  t_bridge_span_external_mm:{value:[3.2,0,52,52][i],limit_mm:10,unit:'mm',rule:'BRG-001',level:'T',verdict:i===2?'NOT_CHECKED':i===3?'FAIL':'PASS',provisional:true,fidelity:'Synthetic shell-only bridge screen <b>inert</b>'},
  t_bridge_span_internal_mm:{value:i===1?0:122,limit_mm:18,unit:'mm',rule:'BRG-001',level:'T',verdict:i===1?'PASS':'FAIL',provisional:true,fidelity:'Synthetic internal bridge screen',coverage:{bridge_roads:i===1?4:8,external_roads:4,internal_roads:i===1?0:4,cell_mm:.4,max_cantilever_mm:2}},
  t_shell_thin_fraction:{value:[.02,0,.1,.02][i],unit:'fraction',rule:'SHELL-001',level:'T',verdict:i===2?'NOT_CHECKED':i===0?'FAIL':'PASS',provisional:true,fidelity:'Synthetic shell-only screen; seed 0, cell 0.1 mm. <b>inert</b>'}}}));
 await page.locator('#table-file').setInputFiles({name:'sort-fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(table))});
 await page.getByRole('button',{name:'large',exact:true}).click();await page.locator('#rationale').fill('Keep this choice while comparing.');
 assert.match(await page.locator('#pose-bridges').innerText(),/PASS · 3.2 mm longest unsupported strand run; recorded limit 10 mm/);
 assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 122 mm/);assert.equal(await page.locator('#pose-bridges b').count(),0);
 assert.match(await page.locator('#pose-bridges').innerText(),/Bridge-road coverage is not established/);
 assert.match(await page.locator('#pose-bridges').innerText(),/longest cantilever across all bridge roads 2 mm \(reported, not judged\)/);
 assert.match(await page.locator('#pose-shell-summary').innerText(),/FAIL · 2% thin · T/);
 assert.match(await page.locator('#pose-shell-fidelity').innerText(),/Synthetic shell-only/);
 assert.match(await page.locator('#pose-shell-coverage').innerText(),/not established/);
 assert.equal(await page.locator('#pose-shell-fidelity b').count(),0);
 await page.locator('#sliced-only').check();assert.equal(await page.locator('#rows tr').count(),3);
 await page.locator('#sliced-only').uncheck();
 await page.getByRole('button',{name:'zero',exact:true}).click();assert.match(await page.locator('#pose-shell-summary').innerText(),/PASS · 0% thin/);assert.match(await page.locator('#pose-bridges').innerText(),/No roads of this type were evaluated/);
 await page.getByRole('button',{name:'unknown',exact:true}).click();assert.equal(await page.locator('#pose-shell-summary').innerText(),'Not checked');
 await page.getByRole('button',{name:'large',exact:true}).click();
 const order=()=>page.locator('#rows button').allTextContents();
 for(const key of ['t_support_segments','F_L_max','height_mm']){
  await page.locator('#pose-sort').selectOption(key);assert.deepEqual(await order(),['zero','large','tie','unknown']);
 }
 await page.locator('#pose-sort').selectOption('contact_mm2');assert.deepEqual(await order(),['large','tie','zero','unknown']);
 await page.locator('#pose-sort').selectOption('analysis');assert.deepEqual(await order(),['large','zero','unknown','tie']);
 assert.equal(await page.locator('#pose-name').innerText(),'large');assert.equal(await page.locator('#rationale').inputValue(),'Keep this choice while comparing.');
 // Reveal only relaxes filters excluding the selected pose, without choosing or editing it.
 await page.locator('#feasible-only').check();await page.locator('#sliced-only').check();
 assert(await page.locator('#reveal-pose').isHidden());
 await page.locator('#feasible-only').uncheck();await page.locator('#sliced-only').uncheck();
 await page.getByRole('button',{name:'unknown',exact:true}).click();await page.locator('#rationale').fill('Preserve my selected pose notes');await page.locator('#walls').fill('6');
 await page.locator('#pose-sort').selectOption('height_mm');await page.locator('#feasible-only').check();await page.locator('#sliced-only').check();
 await page.locator('#reveal-pose').click();
 assert.equal(await page.locator('#feasible-only').isChecked(),false);assert.equal(await page.locator('#sliced-only').isChecked(),false);
 assert.equal(await page.locator('#pose-sort').inputValue(),'height_mm');assert.equal(await page.locator('#rationale').inputValue(),'Preserve my selected pose notes');assert.equal(await page.locator('#walls').inputValue(),'6');
 assert.equal(await page.evaluate(()=>document.activeElement.textContent),'unknown');assert(await page.locator('#reveal-pose').isHidden());
 // Actual enriched receipts: preserve producer precision and show provenance as text.
 await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell.orientation-table.json'));
 await page.getByRole('button',{name:'facet-00',exact:true}).click();
 assert.match(await page.locator('#pose-shell-summary').innerText(),/PASS · 0.22% thin · T · provisional/);
 assert.match(await page.locator('#pose-shell-fidelity').innerText(),/shell-only slice 494c9ec43d5d/);
 assert.match(await page.locator('#pose-shell-coverage').innerText(),/20,000 of 20,000.*0 unmeasured; 0 mm³ clipped/);
 assert.equal(JSON.parse(await page.locator('#pose-shell-receipt').textContent()).receipt.sha256,'b7b362a889869725fa019522e7d73be3671f48fd7805d1a734176a2f847e29fd');
 await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#pose-shell-summary').innerText(),/0.19% thin/);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.equal(await page.locator('#pose-shell-summary').innerText(),'Not checked');assert(await page.locator('#pose-shell-details').isHidden());
 // Real chained shell + bridge evidence, preserving separate verdicts and original receipt hashes.
 await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell-bridge.orientation-table.json'));
 await page.getByRole('button',{name:'facet-00',exact:true}).click();
 assert.match(await page.locator('#pose-bridges').innerText(),/PASS · 3.15 mm/);assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 122.1 mm/);
 assert.match(await page.locator('#failed-checks').innerText(),/Internal bridge span · BRG-001 · T · provisional/);
 assert.doesNotMatch(await page.locator('#failed-checks').innerText(),/External bridge span/);
 assert.match(await page.locator('#rows tr.selected').innerText(),/Fits \/ stable; [1-9][0-9]* recorded failed check/);
 assert.match(await page.locator('#pose-bridges').innerText(),/111 external bridges evaluated/);
 assert.equal(JSON.parse(await page.locator('#pose-bridges pre').first().textContent()).receipt.sha256,'934bd2833b96ae4805164cdc69759550201a0aed38967b349148c3da784ad9a3');
 assert.match(await page.locator('#pose-shell-summary').innerText(),/0.22% thin/);
 const layout=await page.evaluate(()=>({table:document.querySelector('.pose-table').getBoundingClientRect().height,action:document.querySelector('#plan-pose').getBoundingClientRect().top-document.querySelector('#pose-name').getBoundingClientRect().top}));
 assert(layout.table<=460);assert(layout.action>=0&&layout.action<200);
 await page.locator('#plan-pose').click();assert.equal(await page.evaluate(()=>document.activeElement.id),'walls');

 await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 52.2 mm/);assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 53.95 mm/);
 assert.match(await page.locator('#failed-checks').innerText(),/External bridge span · BRG-001 · T/);
 assert.match(await page.locator('#pose-bridges').innerText(),/Ceiling span: not recorded/);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.equal(await page.locator('#pose-bridges details').count(),0);
 // Synthetic additive column coverage; no legacy receipt is changed.
 const ceilingTable=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell-bridge.orientation-table.json')));
 ceilingTable.candidates.find(c=>c.id==='facet-00').columns.t_bridge_span_internal_mm.ceiling_span_mm=15.7;
 await page.locator('#table-file').setInputFiles({name:'synthetic-ceiling-table.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(ceilingTable))});
 await page.getByRole('button',{name:'facet-00',exact:true}).click();
 assert.match(await page.locator('#pose-bridges').innerText(),/Ceiling span: 15.7 mm/);
 assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 122.1 mm longest unsupported strand run/);
 assert.match(await page.locator('#pose-bridges').innerText(),/recorded verdict uses the strand span/);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log('PASS measured pose support, fidelity/settings, missing slice remains unchecked, slice filter, mobile, console');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
