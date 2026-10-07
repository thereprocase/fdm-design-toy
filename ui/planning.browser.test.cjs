// Optional integration: expose a temporary Playwright install through NODE_PATH.
const {chromium}=require('playwright');
const crypto=require('node:crypto'),path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs/promises'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1200,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.locator('#table-file').setInputFiles(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
  await page.getByRole('button',{name:'facet-00',exact:true}).click();
  await page.locator('#rationale').fill('Keep the seat load in the layer plane.');
  const fill=async(box,name)=>{for(const [key,value] of Object.entries({name,location:'Rear seat to mounting plate',purpose:'Transfer the seat load',keep_clear:'Rod bore and washer seats'}))await box.locator(`[data-key="${key}"]`).fill(value);};
  await fill(page.locator('.helper-region').first(),'Seat rib');await page.locator('#add-helper').click();await fill(page.locator('.helper-region').last(),'Mount backing');
  const download=async()=>{const pending=page.waitForEvent('download');await page.locator('#export').click();return JSON.parse(await fs.readFile(await (await pending).path(),'utf8'));};
  const original=await download();assert.equal(original.massing.helper_regions.length,2);assert.match(await page.locator('#handoff-readiness').innerText(),/2 helper\(s\) without a box/);assert(await page.locator('#handoff').evaluate(e=>e.open));
  assert(await page.locator('#undo-remove').isDisabled());
  // Restore multiple deletions without changing identity, order or export values.
  await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  assert.equal(await page.locator('.helper-region').count(),0);
  await page.locator('#undo-remove').click();await page.locator('#undo-remove').click();
  assert.deepEqual(await download(),original);assert(await page.locator('#undo-remove').isDisabled());
  // Incomplete edits must survive too; undo must not coerce blanks into zero.
  const first=page.locator('.helper-region').first();
  await first.locator('[data-spatial]').check();await first.locator('[data-geometry="size_mm"]').first().fill('');
  await first.locator('[data-interface-id]').first().check();await first.locator('[data-clearance]').fill('1.7');
  await first.getByRole('button',{name:'Remove region'}).click();await page.locator('#undo-remove').click();
  assert.equal(await first.locator('[data-geometry="size_mm"]').first().inputValue(),'');
  assert(await first.locator('[data-spatial]').isChecked());assert(await first.locator('[data-interface-id]').first().isChecked());
  assert.equal(await first.locator('[data-clearance]').inputValue(),'1.7');
  await page.locator('#walls').fill('7');await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  const upload=async object=>page.locator('#draft-file').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(object))});
  await upload(original);await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));
  assert.equal(await page.locator('#walls').inputValue(),'4');assert.equal(await page.locator('.helper-region').count(),2);assert.deepEqual(await download(),original);assert(await page.locator('#undo-remove').isDisabled());
  await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  const wrong=structuredClone(original);wrong.source.orientation_table_sha256='0'.repeat(64);await upload(wrong);
  await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.includes('different orientation table'));assert.equal(await page.locator('.helper-region').count(),1);
  assert(await page.locator('#undo-remove').isEnabled());await page.locator('#undo-remove').click();assert.deepEqual(await download(),original);
  await page.locator('#shell-only').check();assert.deepEqual((await download()).massing.helper_regions,[]);assert.match(await page.locator('#handoff-readiness').innerText(),/geometry inputs needed/);
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  await page.locator('#shell-only').uncheck();await page.locator('.helper-region').first().getByRole('button',{name:'Remove region'}).click();
  const plain=await fs.readFile(path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json'));
  const bom=Buffer.concat([Buffer.from([0xef,0xbb,0xbf]),plain]);
  await page.locator('#table-file').setInputFiles({name:'table-bom.json',mimeType:'application/json',buffer:bom});
  await page.getByRole('button',{name:'facet-00',exact:true}).click();await page.locator('#rationale').fill('Preserve exact source bytes.');await page.locator('#shell-only').check();
  assert(await page.locator('#undo-remove').isDisabled());
  const exact=await download();assert.equal(exact.source.orientation_table_sha256,crypto.createHash('sha256').update(bom).digest('hex'));
  await upload(exact);await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));
  const malformed=Buffer.concat([Buffer.from('{"problem":"'),Buffer.from([0xff]),Buffer.from('"}')]);
  await page.locator('#table-file').setInputFiles({name:'malformed.json',mimeType:'application/json',buffer:malformed});
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Could not load table'));
  assert(await page.locator('#workspace').isHidden());assert.match(await page.locator('#status').innerText(),/encoded data|UTF-8/i);
  console.log('PASS: multi-helper save/reopen, edits restored, exact round-trip, wrong-source rejection preserves draft, shell-only export, mobile, console');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
