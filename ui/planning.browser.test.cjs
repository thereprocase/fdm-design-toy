// Optional integration: expose a temporary Playwright install through NODE_PATH.
const {chromium}=require('playwright');
const crypto=require('node:crypto'),path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs/promises'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1200,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',dialog=>dialog.accept());
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.locator('#table-file').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('null')});
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Could not load table'));
  assert(await page.locator('#workspace').isHidden());
  await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
  assert.equal(await page.locator('#planning-pose').innerText(),'No pose selected for this draft.');
  await page.getByRole('button',{name:'facet-00',exact:true}).click();
  assert.match(await page.locator('#planning-pose').innerText(),/Planning pose: facet-00/);
  await page.locator('#export').click();
  assert.equal(await page.evaluate(()=>document.activeElement.id),'rationale');
  assert.equal(await page.locator('#rationale').getAttribute('aria-invalid'),'true');
  assert.match(await page.locator('#export-status').innerText(),/Choice rationale/);
  assert.match(await page.locator('#draft-field-error').innerText(),/Choice rationale/);
  assert.equal(await page.locator('#rationale').getAttribute('aria-errormessage'),'draft-field-error');
  await page.locator('#rationale').fill('Keep the seat load in the layer plane.');
  assert.equal(await page.locator('#rationale').getAttribute('aria-invalid'),null);
  await page.locator('#export').click();
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.key),'name');
  assert.match(await page.locator('#draft-field-error').innerText(),/Helper 1 name/);
  assert.equal(await page.locator('.helper-region').first().locator('#draft-field-error').count(),1);
  assert.equal(await page.locator('.helper-region [data-key="name"]').getAttribute('aria-invalid'),'true');

  const fill=async(box,name)=>{for(const [key,value] of Object.entries({name,location:'Rear seat to mounting plate',purpose:'Transfer the seat load',keep_clear:'Rod bore and washer seats'}))await box.locator(`[data-key="${key}"]`).fill(value);};
  await fill(page.locator('.helper-region').first(),'Seat rib');
  const beforeAdd=await page.evaluate(()=>JSON.parse(draftFormState()).helpers[0]);
  await page.setViewportSize({width:390,height:844});
  await page.locator('#add-helper').focus();await page.keyboard.press('Enter');
  const added=page.locator('.helper-region').last(),addedName=added.locator('[data-key="name"]');
  assert(await addedName.evaluate(e=>e===document.activeElement));
  assert(await added.locator('.helper-editor').evaluate(e=>e.open));
  assert.equal(await page.locator('#preview-helper').inputValue(),await added.getAttribute('data-id'));
  assert(await addedName.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}));
  assert.deepEqual(await page.evaluate(()=>JSON.parse(draftFormState()).helpers[0]),beforeAdd);
  await page.keyboard.type('Mount backing');assert.equal(await addedName.inputValue(),'Mount backing');
  await page.setViewportSize({width:1200,height:900});
  await fill(added,'Mount backing');
  const download=async()=>{const pending=page.waitForEvent('download');await page.locator('#export').click();const file=await pending;assert.equal(file.suggestedFilename(),'spool-rack-g2-ef-facet-00-massing-plan.json');return JSON.parse(await fs.readFile(await file.path(),'utf8'));};
  assert.equal(await page.locator('[data-export-error]').count(),0);
  assert.equal(await page.locator('#draft-field-error').count(),0);
  const sourceDownload=async expected=>{
   await page.locator('#handoff').evaluate(e=>e.open=true);
   const state=await page.locator('#draft-edit-state').innerText(),pending=page.waitForEvent('download');
   await page.locator('#download-table').click();const file=await pending,bytes=await fs.readFile(await file.path());
   assert.deepEqual(bytes,expected);
   const hash=crypto.createHash('sha256').update(expected).digest('hex');
   assert.equal(file.suggestedFilename(),`orientation-table-${hash.slice(0,12)}.json`);
   assert.match(await page.locator('#table-download-status').innerText(),new RegExp(hash));
   assert.equal(await page.locator('#draft-edit-state').innerText(),state);
  };
  const original=await download();assert.equal(original.massing.helper_regions.length,2);assert.match(await page.locator('#handoff-readiness').innerText(),/2 helper\(s\) without a box/);assert(await page.locator('#handoff').evaluate(e=>e.open));
  assert.equal(await page.locator('#handoff-missing-boxes button').count(),2);
  const beforeBoxNavigation=await page.evaluate(()=>draftFormState());
  await page.locator('.helper-region').last().locator('.helper-editor').evaluate(e=>e.open=false);
  await page.locator('#handoff-missing-boxes button').last().click();
  assert(await page.locator('.helper-region').last().locator('[data-spatial]').evaluate(e=>e===document.activeElement&&!e.checked));
  assert(await page.locator('.helper-region').last().locator('.helper-editor').evaluate(e=>e.open));
  assert.equal(await page.evaluate(()=>draftFormState()),beforeBoxNavigation);
  await page.locator('#shell-only').check();assert(await page.locator('#handoff-missing-boxes button').first().isDisabled());
  await page.locator('#shell-only').uncheck();assert(await page.locator('#handoff-missing-boxes button').first().isEnabled());
  assert.match(await page.locator('#draft-edit-state').innerText(),/No edits since the last draft download/);
  assert.equal(await page.locator('#handoff-command').innerText(),`fdmgen massing spool-rack-g2-ef-facet-00-massing-plan.json --table orientation-table-${original.source.orientation_table_sha256.slice(0,12)}.json --template PROFILE.3mf --out out/massing`);
  await sourceDownload(await fs.readFile(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json')));
  assert.equal(await page.locator('#handoff-project').innerText(),'out/massing/spool-rack-g2-ef-facet-00-massing.3mf');
  assert.equal(await page.locator('#handoff-baseline').innerText(),'out/massing/spool-rack-g2-ef-facet-00-massing-shell-only.3mf');
  assert.match(await page.locator('#evidence-command').innerText(),/spool-rack-g2-ef-facet-00-massing.json project.gcode shell-only.gcode/);
  assert.match(await page.locator('#evidence-command').innerText(),/--pose facet-00 --out out\/evidence/);
  for(const id of ['handoff-command','evidence-command']){
    const beforeSelect=await page.evaluate(()=>draftFormState());
    await page.locator('#select-'+id).focus();await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>getSelection().toString()),await page.locator('#'+id).textContent());
    assert(await page.locator('#'+id).evaluate(e=>e===document.activeElement));
    assert.match(await page.locator('#'+id+'-selection').innerText(),/Nothing has been run/);
    assert.equal(await page.evaluate(()=>draftFormState()),beforeSelect);
  }

  assert(await page.locator('#handoff-placeholders').isHidden());
  const invalidHelperId=structuredClone(original);invalidHelperId.massing.helper_regions[0].id='Invalid Helper';
  const beforeInvalidId=await page.evaluate(()=>draftFormState());
  await page.locator('#draft-file').setInputFiles({name:'bad-helper-id.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(invalidHelperId))});
  await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.includes('Helper 1 identifier must be'));
  assert.equal(await page.evaluate(()=>draftFormState()),beforeInvalidId);
  assert.deepEqual(await download(),original);
  for(const [choice,message] of [[true,'Shell-only draft contains helpers'],['false','boolean shell-only choice']]){
    const inconsistent=structuredClone(original);inconsistent.massing.shell_only=choice;
    await page.locator('#draft-file').setInputFiles({name:'inconsistent.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(inconsistent))});
    await page.waitForFunction(message=>document.querySelector('#draft-status').textContent.includes(message),message);
    assert.equal(await page.evaluate(()=>draftFormState()),beforeInvalidId);
    assert.equal(await page.locator('.helper-region').count(),2);
  }
  assert.deepEqual(await download(),original);


  assert.match(await page.locator('#handoff-snapshot').innerText(),/describe the last downloaded draft/);
  await page.locator('#walls').fill('5');
  assert.match(await page.locator('#handoff-snapshot').innerText(),/Current edits are not included/);
  await page.locator('#walls').fill('4');
  assert.doesNotMatch(await page.locator('#handoff-snapshot').innerText(),/Current edits are not included/);


  await page.locator('#collapse-other-helpers').click();
  assert.equal(await page.locator('.helper-editor[open]').count(),1);
  assert.match(await page.locator('#draft-edit-state').innerText(),/No edits since the last draft download/);
  assert.deepEqual((await download()).massing,original.massing);
  const firstHelperId=await page.locator('.helper-region').first().getAttribute('data-id');
  await page.locator('#preview-helper').selectOption(firstHelperId);
  assert(await page.locator('.helper-editor').first().evaluate(e=>e.open));
  await page.locator('.helper-region').first().locator('[data-key="name"]').fill('');
  await page.locator('.helper-editor').first().locator(':scope > summary').click();
  assert.equal(await page.locator('.helper-editor').first().evaluate(e=>e.open),false);
  await page.locator('#export').click();
  assert(await page.locator('.helper-editor').first().evaluate(e=>e.open));
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.key),'name');
  assert.match(await page.locator('#draft-field-error').innerText(),/Helper 1 name/);
  assert.equal(await page.locator('.helper-region').first().locator('#draft-field-error').count(),1);
  await page.locator('.helper-region').first().locator('[data-key="name"]').fill('Seat rib');
  await page.locator('#expand-helpers').click();assert.equal(await page.locator('.helper-editor[open]').count(),2);
  await page.locator('#view-top').click();assert.match(await page.locator('#draft-edit-state').innerText(),/No edits since/);
  await page.getByRole('button',{name:'facet-01',exact:true}).click();assert.match(await page.locator('#draft-edit-state').innerText(),/Changes since/);
  await page.getByRole('button',{name:'facet-00',exact:true}).click();assert.match(await page.locator('#draft-edit-state').innerText(),/No edits since/);
  assert(await page.locator('#undo-remove').isDisabled());
  // Restore multiple deletions without changing identity, order or export values.
  await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  assert.equal(await page.locator('#handoff-missing-boxes button:enabled').count(),0);assert.equal(await page.locator('.helper-region').count(),0);assert.match(await page.locator('#draft-edit-state').innerText(),/Changes since/);
  await page.locator('#undo-remove').click();await page.locator('#undo-remove').click();
  assert.match(await page.locator('#draft-edit-state').innerText(),/No edits since/);
  assert.deepEqual(await download(),original);assert(await page.locator('#undo-remove').isDisabled());
  // Incomplete edits must survive too; undo must not coerce blanks into zero.
  const first=page.locator('.helper-region').first();
  await first.locator('[data-spatial]').check();await first.locator('[data-geometry="size_mm"]').first().fill('');
  await first.locator('[data-interface-id]').first().check();await first.locator('[data-clearance]').fill('1.7');
  await page.setViewportSize({width:390,height:844});
  await first.getByRole('button',{name:'Remove region'}).click();await page.locator('#undo-remove').click();
  assert(await first.locator('[data-key="name"]').evaluate(e=>{const r=e.getBoundingClientRect();return e===document.activeElement&&r.top>=0&&r.bottom<=innerHeight;}),'Restored helper name is focused and visible on mobile');
  await page.setViewportSize({width:1200,height:900});
  assert.equal(await first.locator('[data-geometry="size_mm"]').first().inputValue(),'');
  assert(await first.locator('[data-spatial]').isChecked());assert(await first.locator('[data-interface-id]').first().isChecked());
  assert.equal(await first.locator('[data-clearance]').inputValue(),'1.7');
  await page.setViewportSize({width:390,height:844});
  await page.locator('#export').click(); // Invalid box must not checkpoint failed export.
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.geometry),'size_mm');
  assert.equal(await first.locator('[data-geometry="size_mm"]').first().getAttribute('aria-errormessage'),'draft-field-error');
  assert.equal(await first.locator('[data-geometry="size_mm"]').first().inputValue(),'');
  assert.match(await page.locator('#draft-field-error').innerText(),/three finite millimetre values/);
  assert(await page.locator('#draft-field-error').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}),'Inline geometry error is visible beside the focused field on mobile');
  await page.locator('#export').click();assert.equal(await page.locator('#draft-field-error').count(),1);
  await first.locator('[data-geometry="size_mm"]').first().fill('9');
  assert.equal(await page.locator('#draft-field-error').count(),0);
  assert.equal(await first.locator('[aria-invalid]').count(),0);
  await first.locator('[data-geometry="size_mm"]').first().fill('');
  await page.setViewportSize({width:1200,height:900});
  assert.match(await page.locator('#draft-edit-state').innerText(),/Changes since/);
  await page.locator('#walls').fill('6');assert.match(await page.locator('#draft-edit-state').innerText(),/Changes since/);
  await page.locator('#walls').fill('7');await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  const upload=async object=>page.locator('#draft-file').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(object))});
  await upload(original);await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));
  assert.match(await page.locator('#draft-edit-state').innerText(),/No edits since reopening this draft/);
  assert.equal(await page.locator('#walls').inputValue(),'4');assert.equal(await page.locator('.helper-region').count(),2);assert.deepEqual(await download(),original);assert(await page.locator('#undo-remove').isDisabled());
  await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  const beforeWrongTable=await page.evaluate(()=>draftFormState());
  const wrong=structuredClone(original);wrong.source.orientation_table_sha256='0'.repeat(64);await upload(wrong);
  await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.includes('different orientation table'));assert.equal(await page.locator('.helper-region').count(),1);
  assert.match(await page.locator('#draft-status').innerText(),/orientation-table-000000000000\.json/);
  assert((await page.locator('#draft-status').innerText()).includes('Required table SHA256: '+'0'.repeat(64)));
  assert.equal(await page.evaluate(()=>draftFormState()),beforeWrongTable);
  assert.match(await page.locator('#draft-edit-state').innerText(),/Changes since/);
  assert(await page.locator('#undo-remove').isEnabled());await page.locator('#undo-remove').click();assert.deepEqual(await download(),original);
  await page.locator('#shell-only').check();assert.deepEqual((await download()).massing.helper_regions,[]);assert.match(await page.locator('#handoff-readiness').innerText(),/geometry inputs needed/);
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  await page.locator('#shell-only').uncheck();await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  const plain=await fs.readFile(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
  const bom=Buffer.concat([Buffer.from([0xef,0xbb,0xbf]),plain]);
  await page.locator('#table-file').setInputFiles({name:'table-bom.json',mimeType:'application/json',buffer:bom});
  await page.getByRole('button',{name:'facet-00',exact:true}).click();await page.locator('#rationale').fill('Preserve exact source bytes.');await page.locator('#shell-only').check();
  assert(await page.locator('#undo-remove').isDisabled());
  assert.match(await page.locator('#handoff-command').innerText(),/massing DRAFT.json --table TABLE.json/);
  assert.match(await page.locator('#evidence-command').innerText(),/PART-POSE-massing.json/);
  await sourceDownload(bom);
  const exact=await download();assert.equal(exact.source.orientation_table_sha256,crypto.createHash('sha256').update(bom).digest('hex'));
  await upload(exact);await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));
  assert.match(await page.locator('#handoff-command').innerText(),/massing DRAFT.json --table TABLE.json/);
  assert.match(await page.locator('#evidence-command').innerText(),/PART-POSE-massing.json/);
  assert.match(await page.locator('#handoff-readiness').innerText(),/Export this draft/);assert.equal(await page.locator('#handoff-missing-boxes button').count(),0);
  assert.match(await page.locator('#handoff-snapshot').innerText(),/No export from this draft/);
  assert.match(await page.locator('#planning-pose').innerText(),/Planning pose: facet-00/);
  assert.match(await page.locator('#planning-pose-checks').innerText(),/Design-frame build direction/);

  const malformed=Buffer.concat([Buffer.from('{"problem":"'),Buffer.from([0xff]),Buffer.from('"}')]);
  await page.locator('#table-file').setInputFiles({name:'malformed.json',mimeType:'application/json',buffer:malformed});
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Could not load table'));
  assert(await page.locator('#workspace').isVisible());assert.match(await page.locator('#status').innerText(),/encoded data|UTF-8/i);
  assert.match(await page.locator('#status').innerText(),/previous table and current draft remain/);
  await sourceDownload(bom);
  assert.deepEqual(await download(),exact);
  // Render-invalid metadata must be rejected before the current table is replaced.
  await page.locator('#shell-only').uncheck();await page.locator('#add-helper').click();
  await fill(page.locator('.helper-region').first(),'Recoverable helper');
  await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  for(const [change,message] of [[{mesh:{path:7}},'Mesh path'],[{interfaces:{}},'interfaces must'],[{keep_outs:[null]},'keep_outs entries']]){
    const bad={...JSON.parse(plain),...change};
    await page.locator('#table-file').setInputFiles({name:'bad-table.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
    await page.waitForFunction(message=>document.querySelector('#status').textContent.includes(message),message);
    assert(await page.locator('#workspace').isVisible());assert(await page.locator('#undo-remove').isEnabled());
    assert.match(await page.locator('#draft-edit-state').innerText(),/Changes since/);
  }

  const beforeBadPose=await page.evaluate(()=>draftFormState());
  for(const change of [{R_design_to_print:[[1,0,0],[0,1,0],[0,0,-1]]},{t_mm:[0,0]},{build_dir_design:[0,0,2]}]){
    const bad=JSON.parse(plain);Object.assign(bad.candidates[0],change);
    await page.locator('#table-file').setInputFiles({name:'bad-pose.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Candidate facet-00:'));
    assert.equal(await page.evaluate(()=>draftFormState()),beforeBadPose);
    assert(await page.locator('#undo-remove').isEnabled());
  }
  await page.locator('#undo-remove').click();assert.equal(await page.locator('.helper-region').first().locator('[data-key="name"]').inputValue(),'Recoverable helper');
  const recovered=await download();assert.equal(recovered.source.orientation_table_sha256,exact.source.orientation_table_sha256);
  assert.equal(recovered.massing.helper_regions[0].name,'Recoverable helper');assert.deepEqual(errors,[]);
  console.log('PASS: multi-helper save/reopen, edits restored, exact round-trip, wrong-source rejection preserves draft, shell-only export, mobile, console');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
