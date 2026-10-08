const fs=require('node:fs');
const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1300,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('dialog',dialog=>dialog.accept());
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
 await page.locator('#feasible-only').uncheck();
 const fitRows=await page.locator('#rows tr').evaluateAll(rows=>rows.map(r=>({bed:r.cells[7].textContent,feasible:r.cells[8].textContent})));
 assert.equal(fitRows.filter(r=>r.bed.startsWith('Fits')).length,10);
 assert.equal(fitRows.filter(r=>r.feasible.startsWith('Fits / stable')).length,2);
 assert(fitRows.some(r=>r.bed.startsWith('Fits')&&r.feasible.startsWith('Fit needs review')));
 assert.equal(fitRows.filter(r=>r.bed.startsWith('Does not fit')).length,3);
 await page.getByRole('button',{name:'facet-00',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/4,344/);assert.match(await page.locator('#toolpath-settings').innerText(),/support 1, threshold 45/);assert.match(await page.locator('#credited-scope').innerText(),/support excluded/);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/Not checked/);assert.match(await page.locator('#toolpath-settings').innerText(),/No support-column slicer context/);assert.equal(await page.locator('#credited-scope').innerText(),'');
 assert.equal(await page.locator('#pose-shell-summary').innerText(),'Not checked');
 assert.match(await page.locator('#pose-bridges').innerText(),/Not checked/);
 assert.match(await page.locator('#rows tr.selected [data-bridge-summary]').innerText(),/External: Not checked[\s\S]*Internal: Not checked/);
 await page.locator('#sliced-only').check();assert.equal(await page.locator('#rows tr').count(),2);assert.match(await page.locator('#pose-count').innerText(),/Selected pose facet-02 is hidden/);await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#toolpath-metrics').innerText(),/8,596/);
 // Batch shell/bridge enrichment supplies evidence without support-count columns.
 const checksOnly=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell-bridge.orientation-table.json')));
 for(const candidate of checksOnly.candidates)delete candidate.columns.t_support_segments;
 for(const mode of ['shell-and-bridge','bridge-only','shell-only','invalid-evidence']){
  const fixture=structuredClone(checksOnly);
  for(const candidate of fixture.candidates){
   if(mode==='bridge-only')delete candidate.columns.t_shell_thin_fraction;
   if(mode==='shell-only'){delete candidate.columns.t_bridge_span_external_mm;delete candidate.columns.t_bridge_span_internal_mm;}
   if(mode==='invalid-evidence')for(const key of ['t_shell_thin_fraction','t_bridge_span_external_mm','t_bridge_span_internal_mm'])if(candidate.columns[key])candidate.columns[key].level='M';
  }
  await page.locator('#table-file').setInputFiles({name:mode+'.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(fixture))});
  await page.locator('#sliced-only').check();
  const poses=await page.locator('#rows button').allTextContents();
  if(mode==='invalid-evidence'){assert.deepEqual(poses,['Show all poses']);continue;}
  assert.deepEqual(poses,['facet-00','facet-01']);
  await page.getByRole('button',{name:'facet-00',exact:true}).click();
  assert.match(await page.locator('#rows tr').first().locator('td').nth(4).innerText(),/Not checked/);
  assert.match(await page.locator('#toolpath-metrics').innerText(),/Not checked/);
 }
 // Exact producer fixture exposes the distinguishing bridge measurements in the table.
 await page.locator('#table-file').setInputFiles(path.join(__dirname,'fixtures/orient-evidence/orientation-table.enriched.json'));
 for(const id of ['facet-00','facet-01']){
  const row=page.locator('#rows tr').filter({has:page.getByRole('button',{name:id,exact:true})});
  const expected=await page.evaluate(id=>analysis.candidates.find(c=>c.id===id).columns,id);
  for(const [key,label] of [['t_bridge_span_external_mm','External'],['t_bridge_span_internal_mm','Internal']]){
   const column=expected[key],display=await page.evaluate(v=>metricNumber(v),column.value);
   assert((await row.locator('[data-bridge-summary]').innerText()).includes(`${label}: ${column.verdict} · ${display} mm · T`));
  }
  assert.match(await row.locator('[data-bridge-summary]').innerText(),/shell-only/);
 }
 await page.setViewportSize({width:390,height:844});await page.locator('.pose-table').evaluate(e=>e.scrollLeft=e.scrollWidth);
 const bridgeLayout=await page.locator('#rows tr').first().evaluate(row=>{const panel=row.closest('.pose-table').getBoundingClientRect(),id=row.cells[0].getBoundingClientRect(),bridge=row.querySelector('[data-bridge-summary]').getBoundingClientRect();return {width:bridge.width,idLeft:id.left-panel.left,nowrap:getComputedStyle(row.cells[0]).whiteSpace,right:bridge.right-panel.right};});
 assert(bridgeLayout.width>=220);assert(bridgeLayout.idLeft>=0&&bridgeLayout.idLeft<3);assert.equal(bridgeLayout.nowrap,'nowrap');assert(Math.abs(bridgeLayout.right)<2);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.setViewportSize({width:1300,height:1000});
 // Mixed slice kinds are not silently presented as controlled orientation evidence.
 const mixedKinds=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/orient-evidence/orientation-table.enriched.json')));
 mixedKinds.candidates.find(c=>c.id==='facet-01').columns.t_shell_thin_fraction.receipt.slice_kind='project';
 await page.locator('#table-file').setInputFiles({name:'synthetic-mixed-kinds.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(mixedKinds))});
 await page.getByRole('button',{name:'facet-00',exact:true}).click();await page.locator('#pin-reference').click();await page.getByRole('button',{name:'facet-01',exact:true}).click();
 const shellKinds=page.locator('#comparison-rows tr').filter({has:page.getByRole('rowheader',{name:'Thin shell fraction · T',exact:true})});
 assert.deepEqual(await shellKinds.locator('[data-slice-kind]').allTextContents(),['Slice kind: shell-only','Slice kind: project']);
 assert.match(await page.locator('#comparison-slice-context').innerText(),/not a controlled orientation comparison/);
 assert.match(await shellKinds.locator('td > span').first().innerText(),/PASS/);
 await page.getByRole('button',{name:'facet-00',exact:true}).click();
 assert.match(await page.locator('#comparison-slice-context').innerText(),/Equal kinds alone do not establish/);
 // Missing metadata remains explicit, and source records are not rewritten.
 delete mixedKinds.candidates.find(c=>c.id==='facet-01').columns.t_shell_thin_fraction.receipt.slice_kind;
 await page.locator('#table-file').setInputFiles({name:'synthetic-missing-kind.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(mixedKinds))});
 await page.getByRole('button',{name:'facet-00',exact:true}).click();await page.locator('#pin-reference').click();await page.getByRole('button',{name:'facet-01',exact:true}).click();
 assert.deepEqual(await shellKinds.locator('[data-slice-kind]').allTextContents(),['Slice kind: shell-only','Slice kind: not recorded']);
 // Known-order comparison fixture: zero is measured, unchecked numeric values stay last.
 await page.locator('#sliced-only').uncheck();
 const table=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json')));
 const base=table.candidates[0];
 table.candidates=['large','zero','unknown','tie'].map((id,i)=>({...structuredClone(base),id,feasible:i!==2,columns:{...structuredClone(base.columns),
  t_support_segments:{value:[9,0,-1,9][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  F_L_max:{value:[.3,.1,null,.3][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  contact_mm2:{value:[100,20,null,100][i],verdict:i===2?'NOT_CHECKED':'PASS'},
  height_mm:{value:[30,10,null,30][i],unit:'mm',verdict:i===2?'NOT_CHECKED':'PASS'},
  t_bridge_span_external_mm:{value:[3.2,0,52,52][i],limit_mm:10,unit:'mm',rule:'BRG-001',level:'T',verdict:i===2?'NOT_CHECKED':i===3?'FAIL':'PASS',provisional:true,fidelity:'Synthetic shell-only bridge screen <b>inert</b>'},
  t_bridge_span_internal_mm:{value:i===1?0:122,limit_mm:18,unit:'mm',rule:'BRG-001',level:'T',verdict:i===2?'NOT_CHECKED':i===1?'PASS':'FAIL',provisional:true,fidelity:'Synthetic internal bridge screen',coverage:{bridge_roads:i===1?4:8,external_roads:4,internal_roads:i===1?0:4,cell_mm:.4,max_cantilever_mm:2}},
  t_shell_thin_fraction:{value:[.02,0,.1,.02][i],unit:'fraction',rule:'SHELL-001',level:'T',verdict:i===2?'NOT_CHECKED':i===0?'FAIL':'PASS',provisional:true,fidelity:'Synthetic shell-only screen; seed 0, cell 0.1 mm. <b>inert</b>'}}}));
 await page.locator('#table-file').setInputFiles({name:'sort-fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(table))});
 await page.getByRole('button',{name:'large',exact:true}).click();await page.locator('#rationale').fill('Keep this choice while comparing.');
 const formBeforePin=await page.evaluate(()=>draftFormState());
 await page.locator('#pin-reference').click();assert.equal(await page.evaluate(()=>draftFormState()),formBeforePin);
 assert.match(await page.locator('#reference-status').innerText(),/Select another pose/);
 await page.getByRole('button',{name:'zero',exact:true}).click();
 assert.equal(await page.locator('#reference-name').innerText(),'Reference: large');
 assert.equal(await page.locator('#comparison-name').innerText(),'Selected: zero');
 assert.match(await page.locator('#planning-pose').innerText(),/Planning pose: zero/);
 assert.doesNotMatch(await page.locator('#planning-pose').innerText(),/large/);
 const shellRow=page.locator('#comparison-rows tr').filter({has:page.getByRole('rowheader',{name:'Thin shell fraction · T',exact:true})});
 assert.match(await shellRow.locator('td').nth(0).innerText(),/FAIL · 2% thin/);assert.match(await shellRow.locator('td').nth(1).innerText(),/PASS · 0% thin/);
 await shellRow.locator('summary').first().click();assert.match(await shellRow.locator('td').first().innerText(),/Synthetic shell-only screen/);assert.equal(await shellRow.locator('b').count(),0);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.setViewportSize({width:1300,height:1000});
 await page.getByRole('button',{name:'unknown',exact:true}).click();assert.match(await shellRow.locator('td').nth(1).innerText(),/Not checked/);
 assert.match(await page.locator('#planning-pose').innerText(),/Planning pose: unknown/);assert.match(await page.locator('#planning-pose-checks').innerText(),/fit\/stability: needs review/);
 await page.locator('#feasible-only').check();assert.match(await page.locator('#reference-status').innerText(),/Reference: large.*Selected for planning: unknown/);
 await page.locator('#feasible-only').uncheck();
 await page.locator('#clear-reference').click();assert(await page.locator('#reference-comparison').isHidden());
 await page.getByRole('button',{name:'large',exact:true}).click();await page.locator('#pin-reference').click();

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
 assert.deepEqual(await page.locator('#rows tr').evaluateAll(rows=>rows.map(r=>r.cells[6].textContent)),['10 mm','30 mm','30 mm','Not checked']);
 assert.equal(await page.getByRole('columnheader',{name:'Height mm',exact:true}).count(),1);
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
 assert(await page.locator('#reference-comparison').isHidden());assert(await page.locator('#clear-reference').isDisabled());
 assert.match(await page.locator('#pose-shell-summary').innerText(),/PASS · 0.22% thin · T · provisional/);
 assert.match(await page.locator('#pose-shell-fidelity').innerText(),/shell-only slice 494c9ec43d5d/);
 assert.match(await page.locator('#pose-shell-coverage').innerText(),/20,000 of 20,000.*0 unmeasured; 0 mm³ clipped/);
 assert.equal(JSON.parse(await page.locator('#pose-shell-receipt').textContent()).receipt.sha256,'b7b362a889869725fa019522e7d73be3671f48fd7805d1a734176a2f847e29fd');
 await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#pose-shell-summary').innerText(),/0.19% thin/);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.equal(await page.locator('#pose-shell-summary').innerText(),'Not checked');assert(await page.locator('#pose-shell-details').isHidden());
 // Real chained shell + bridge evidence, preserving separate verdicts and original receipt hashes.
 await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell-bridge.orientation-table.json'));
 await page.getByRole('button',{name:'facet-00',exact:true}).click();
 assert.equal(await page.locator('#pose-bridges [data-bridge-remedy]').count(),1);
 assert.match(await page.locator('#pose-bridges [data-bridge-remedy]').innerText(),/no verified helper-edit remedy/);
 assert.deepEqual(await page.locator('#pose-bridges [data-bridge-remedy] a').evaluateAll(a=>a.map(x=>x.href)),['https://github.com/thereprocase/fdm-design-toy/issues/9','https://github.com/thereprocase/fdm-design-toy/issues/12','https://github.com/thereprocase/fdm-design-toy/issues/17#issuecomment-6049963530']);
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
 assert.match(await page.locator('#pose-bridges').innerText(),/Ceiling span maximum: not recorded/);
 await page.locator('#pin-reference').click();
 const ceilingRow=label=>page.locator('#comparison-rows tr').filter({has:page.getByRole('rowheader',{name:label,exact:true})});
 assert.deepEqual(await ceilingRow('Internal bridge ceiling maximum · T').locator('td > span').allTextContents(),['Not recorded','Not recorded']);
 await page.getByRole('button',{name:'facet-02',exact:true}).click();assert.equal(await page.locator('#pose-bridges details').count(),0);
 // Synthetic additive column coverage; no legacy receipt is changed.
 const ceilingTable=JSON.parse(fs.readFileSync(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.shell-bridge.orientation-table.json')));
 ceilingTable.candidates.find(c=>c.id==='facet-00').columns.t_bridge_span_internal_mm.ceiling_span_mm=15.7;
 await page.locator('#table-file').setInputFiles({name:'synthetic-ceiling-table.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(ceilingTable))});
 await page.getByRole('button',{name:'facet-00',exact:true}).click();
 assert.match(await page.locator('#pose-bridges').innerText(),/Ceiling span maximum: 15.7 mm/);
 assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 122.1 mm longest unsupported strand run/);
 assert.match(await page.locator('#pose-bridges').innerText(),/recorded verdict uses the strand span/);
 assert.match(await page.locator('#pose-bridges').innerText(),/independent per-measure maxima/);
 // Fresh measured receipt enrichment, kept separately from the original pinned tables.
 const realCeilingPath=path.join(__dirname,'fixtures/ceiling/orientation-table.json');
 assert.equal(require('node:crypto').createHash('sha256').update(fs.readFileSync(realCeilingPath)).digest('hex'),'d1f365b2bc64142789f7dc4073ec0582348382e8be4945cc8fd4c05dcab373d1');
 await page.locator('#table-file').setInputFiles(realCeilingPath);
 await page.getByRole('button',{name:'facet-00',exact:true}).click();
 assert.match(await page.locator('#pose-bridges').innerText(),/Ceiling span maximum: 2 mm/);
 assert.match(await page.locator('#pose-bridges').innerText(),/Ceiling span maximum: 15.678 mm/);
 assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 122.1 mm/);
 assert.equal(JSON.parse(await page.locator('#pose-bridges pre').first().textContent()).receipt.sha256,'3dda4f12515dc2969f64e3270af297e22ac2b46ec04cc3698f49fa443787a237');
 await page.locator('#pin-reference').click();
 await page.getByRole('button',{name:'facet-01',exact:true}).click();
 assert.match(await page.locator('#pose-bridges').innerText(),/FAIL · 52.2 mm/);
 assert.match(await page.locator('#pose-bridges').innerText(),/Ceiling span maximum: 52.2 mm/);
 assert.deepEqual(await ceilingRow('External bridge ceiling maximum · T').locator('td > span').allTextContents(),['2 mm · supplementary','52.2 mm · supplementary']);
 assert.deepEqual(await ceilingRow('Internal bridge ceiling maximum · T').locator('td > span').allTextContents(),['15.678 mm · supplementary','15.647 mm · supplementary']);
 assert.match(await ceilingRow('Internal bridge ceiling maximum · T').innerText(),/may occur on a different road/);
 assert.match(await page.locator('#comparison-rows').innerText(),/FAIL · 122.1 mm/);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 const beforeReviewJump=await page.evaluate(()=>draftFormState());
 for(const width of [1366,390]){
  await page.setViewportSize({width,height:844});
  await page.locator('#review-selected').click();
  assert.equal(await page.evaluate(()=>document.activeElement.id),'pose-name');
  const plan=await page.locator('#plan-pose').boundingBox();assert(plan.y>=0&&plan.y+plan.height<=844);
  assert.equal(await page.evaluate(()=>draftFormState()),beforeReviewJump);
  assert.match(await page.locator('#review-selected').innerText(),/facet-01/);
 }
 const scrollTable=page.locator('.pose-table');
 await page.locator('#feasible-only').uncheck();await page.locator('#sliced-only').uncheck();
 const activeButton=page.getByRole('button',{name:'facet-01',exact:true});
 await activeButton.scrollIntoViewIfNeeded();
 const initialX=(await activeButton.boundingBox()).x;
 await scrollTable.evaluate(e=>e.scrollLeft=e.scrollWidth);
 const farRight=await activeButton.boundingBox(),tableBox=await scrollTable.boundingBox();
 assert(Math.abs(farRight.x-initialX)<2,'Pose identifier remains pinned while metrics scroll');
 assert(farRight.x>=tableBox.x&&farRight.x+farRight.width<=tableBox.x+tableBox.width);
 assert(await scrollTable.evaluate(e=>e.scrollLeft>0));
 await activeButton.focus();await page.keyboard.press('Enter');
 assert.equal(await page.locator('#pose-name').innerText(),'facet-01');
 assert(await activeButton.evaluate(e=>e===document.activeElement));
 if(process.env.FDM_TABLE_SCREENSHOT)await scrollTable.screenshot({path:process.env.FDM_TABLE_SCREENSHOT});
 await scrollTable.evaluate(e=>e.scrollLeft=0);
 table.feasible_scope='BED-001 and BED-002 only. <b>Scope text, not markup.</b>';
 table.candidates[2].feasible=null;
 table.candidates[2].columns.fits_bed={value:true,rule:'BED-001',level:'M',verdict:'NOT_CHECKED'};
 await page.locator('#table-file').setInputFiles({name:'scope-fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(table))});
 await page.locator('#feasible-only').uncheck();await page.locator('#sliced-only').uncheck();
 assert.equal(await page.locator('#feasible-scope').innerText(),'Producer feasibility scope: '+table.feasible_scope);
 assert.equal(await page.locator('#feasible-scope b').count(),0);
 assert.match(await page.locator('#rows tr').filter({has:page.getByRole('button',{name:'unknown',exact:true})}).innerText(),/Fit not recorded/);
 assert.equal(await page.locator('#rows tr').filter({has:page.getByRole('button',{name:'unknown',exact:true})}).locator('td').nth(7).innerText(),'Not checked');
 await page.locator('#feasible-only').check();assert.equal(await page.getByRole('button',{name:'unknown',exact:true}).count(),0);
 delete table.feasible_scope;
 await page.locator('#table-file').setInputFiles({name:'no-scope.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(table))});
 await page.waitForFunction(()=>document.querySelector('#feasible-scope').textContent.includes('scope not supplied'));
 assert.match(await page.locator('#feasible-scope').innerText(),/scope not supplied/);
 for(const c of table.candidates){c.feasible=false;for(const key of ['t_support_segments','t_shell_thin_fraction','t_bridge_span_external_mm','t_bridge_span_internal_mm'])c.columns[key]={value:null,verdict:'NOT_CHECKED'};}
 await page.locator('#table-file').setInputFiles({name:'unsliced.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(table))});
 await page.waitForFunction(()=>document.querySelector('#pose-count').textContent.includes('0 have measured slices'));
 assert(await page.locator('#review-selected').isDisabled());
 await page.locator('#feasible-only').check();await page.locator('#sliced-only').check();
 const beforeEmpty=await page.evaluate(()=>draftFormState());
 await page.getByRole('button',{name:'Show all poses',exact:true}).focus();await page.keyboard.press('Enter');
 assert.equal(await page.locator('#rows button').count(),4);assert.equal(await page.evaluate(()=>selected),null);
 assert.equal(await page.evaluate(()=>draftFormState()),beforeEmpty);
 assert(await page.locator('#rows button').first().evaluate(e=>e===document.activeElement));
 await page.getByRole('button',{name:'unknown',exact:true}).click();await page.locator('#rationale').fill('Keep this choice while revealing alternatives');
 await page.locator('#pose-sort').selectOption('height_mm');
 const beforeSelectedEmpty=await page.evaluate(()=>draftFormState());
 await page.locator('#feasible-only').check();await page.locator('#sliced-only').check();
 await page.getByRole('button',{name:'Show all poses',exact:true}).click();
 assert.equal(await page.locator('#pose-sort').inputValue(),'height_mm');
 assert.equal(await page.evaluate(()=>draftFormState()),beforeSelectedEmpty);
 assert(await page.getByRole('button',{name:'unknown',exact:true}).evaluate(e=>e===document.activeElement));
 table.candidates[0].columns.F_L_max={value:0,unit:'1',verdict:'PASS'};
 table.candidates[2].columns.F_L_max={value:.00004,unit:'1',verdict:'PASS'};
 table.candidates[2].columns.F_L_max_vendor_corner={value:.00002,unit:'1',verdict:'PASS'};
 await page.locator('#table-file').setInputFiles({name:'small-values.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(table))});
 await page.waitForFunction(()=>analysis.candidates[2].columns.F_L_max.value===.00004);
 const rowFor=id=>page.locator('#rows tr').filter({has:page.getByRole('button',{name:id,exact:true})});
 assert.equal(await rowFor('large').locator('td').nth(1).innerText(),'0');
 assert.equal(await rowFor('unknown').locator('td').nth(1).innerText(),'4.00e-5');
 await page.getByRole('button',{name:'unknown',exact:true}).click();
 assert.match(await page.locator('#metrics').innerText(),/4\.00e-5/);
 assert.match(await page.locator('#strength-range').innerText(),/2\.00e-5–4\.00e-5/);
 assert.equal(await page.evaluate(()=>selected.columns.F_L_max.value),.00004);
 assert.equal(await page.evaluate(()=>formatted({value:[0,-.00004,1.25],unit:'mm',verdict:'PASS'})),'0, -4.00e-5, 1.25 mm');
 for(const key of ['F_L_max','F_L_max_vendor_corner']){
   const unchecked=structuredClone(table);unchecked.candidates[2].columns[key].verdict='NOT_CHECKED';
   await page.locator('#table-file').setInputFiles({name:key+'-unchecked.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(unchecked))});
   await page.waitForFunction(key=>analysis.candidates[2].columns[key].verdict==='NOT_CHECKED',key);
   await page.getByRole('button',{name:'unknown',exact:true}).click();
   assert.equal(await page.locator('#strength-range').innerText(),'Strength comparison is not checked for both material corners.');
   assert.equal(await page.evaluate(key=>selected.columns[key].value,key),table.candidates[2].columns[key].value);
 }
 console.log('PASS measured pose support, fidelity/settings, missing slice remains unchecked, slice filter, mobile, console');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
