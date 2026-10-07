const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('dialog',dialog=>dialog.accept());
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
 const table=path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json');
 await page.locator('#table-file').setInputFiles(table);
 const original=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/revised-draft.json')));
 const draft=structuredClone(original);
 draft.proposal={generator:'fdmgen.massing.seed',label:'Full-solid field proposal; not an optimum.',status:'helpers_proposed',
  stress:{sha256:'c'.repeat(64),frame:'design',receipt:{load_n:117.72}},pose:{id:'facet-00'},
  accepted:[{id:draft.massing.helper_regions[0].id,cluster:3,cells:87,F_L_max:.061,nearest_restraint:['mount_lower',8]}],
  rejected:[{cluster:1,reason:'restraint_adjacent: modelled clamp <img src=x onerror=alert(1)>'}],
  sensitivity:[{restraint_margin_mm:4.8,accepted_clusters:[3]}],future:{preserve:true}};
 async function open(value){await page.locator('#draft-file').setInputFiles({name:'proposal.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));}
 await open(draft);const panel=page.locator('#proposal-evidence');
 assert(await panel.isVisible());await panel.getByText('1 rejected clusters at generation',{exact:true}).click();assert.match(await panel.innerText(),/Historical proposal provenance/);assert.match(await panel.innerText(),/restraint_adjacent/);assert.equal(await panel.locator('img').count(),0);
 await page.locator('[data-geometry="center_mm"][data-axis="1"]').fill('-22');
 await page.locator('#walls').fill('5');
 const pending=page.waitForEvent('download');await page.locator('#export').click();const download=await pending;
 const chunks=[];for await(const chunk of await download.createReadStream())chunks.push(chunk);const saved=JSON.parse(Buffer.concat(chunks));
 assert.deepEqual(saved.proposal,draft.proposal);assert.equal(saved.proposal_use,'historical_provenance_requires_recheck');
 assert.equal(saved.massing.walls,5);assert.equal(saved.massing.helper_regions[0].geometry.center_mm[1],-22);
 await open(saved);assert(await panel.isVisible());
 const empty=structuredClone(draft);empty.proposal.status='no_viable_helpers';empty.proposal.accepted=[];empty.massing.shell_only=true;empty.massing.helper_regions=[];
 await open(empty);await page.waitForFunction(()=>document.querySelector('#proposal-evidence').textContent.includes('No viable helpers'));
 assert.match(await panel.innerText(),/does not establish that shell-only is sufficient/);
 await page.setViewportSize({width:390,height:844});await panel.getByText('Complete original proposal provenance',{exact:true}).click();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await open(original);assert(await panel.isHidden());
 await open(draft);await page.locator('#table-file').setInputFiles([]);await page.locator('#table-file').setInputFiles(table);await page.waitForFunction(()=>document.querySelector('#proposal-evidence').hidden);
 if(process.env.FDM_SEED_DRAFT){
  const real=JSON.parse(fs.readFileSync(process.env.FDM_SEED_DRAFT));await open(real);
  assert(await panel.isVisible());assert.equal(await page.locator('.helper-region').count(),real.massing.helper_regions.length);
  await page.locator('#walls').fill('5');const pending=page.waitForEvent('download');await page.locator('#export').click();const downloaded=await pending;
  const chunks=[];for await(const chunk of await downloaded.createReadStream())chunks.push(chunk);const raw=Buffer.concat(chunks),reopened=JSON.parse(raw);
  assert.deepEqual(reopened.proposal,real.proposal);assert.equal(reopened.massing.walls,5);
  if(process.env.FDM_SEED_EXPORT)fs.writeFileSync(process.env.FDM_SEED_EXPORT,raw);
  await open(reopened);assert(await panel.isVisible());console.log('PASS actual producer draft import/edit/export with unchanged historical provenance');
 }
 assert.deepEqual(errors,[]);console.log('PASS proposal history, restraint warnings, inert text, edit/export preservation, empty proposal, reset and mobile');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
