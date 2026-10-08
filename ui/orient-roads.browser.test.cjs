const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox']});try{
 const p=await b.newPage({viewport:{width:1366,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
 const dir=path.join(__dirname,'fixtures/orient-evidence'),sha=v=>crypto.createHash('sha256').update(v).digest('hex');
 // Synthetic recombination: original shell receipts plus untouched newer bridge receipts.
 const data=new Map(fs.readdirSync(dir).map(n=>[n,fs.readFileSync(path.join(dir,n))])),m=JSON.parse(data.get('orient-evidence.json')),table=JSON.parse(data.get('orientation-table.enriched.json'));
 for(const e of m.receipts.filter(e=>e.check==='bridge-check')){
  const bytes=fs.readFileSync(path.join(__dirname,'fixtures/bridge-locations',e.pose+'-shell-only.bridge-check.json')),r=JSON.parse(bytes);data.set(e.path,bytes);e.sha256=sha(bytes);
  for(const col of Object.values(table.candidates.find(c=>c.id===e.pose).columns).filter(c=>c.rule==='BRG-001'&&c.level==='T')){col.receipt.sha256=e.sha256;col.receipt.source_sha256=r.source_sha256;}
 }
 data.set(m.enriched_table.path,Buffer.from(JSON.stringify(table)));m.enriched_table.sha256=sha(data.get(m.enriched_table.path));data.set('orient-evidence.json',Buffer.from(JSON.stringify(m)));
 const files=()=>[...data].map(([name,buffer])=>({name,buffer,mimeType:'application/json'}));
 await p.goto(pathToFileURL(path.join(__dirname,'index.html')).href);await p.locator('#orientation-bundle-options > summary').click();await p.locator('#orientation-bundle-files').setInputFiles(files());
 await p.waitForFunction(()=>document.querySelector('#orientation-bundle-status').textContent.startsWith('Complete bundle verified'));
 await p.getByRole('button',{name:'Review facet-01',exact:true}).click();await p.locator('#pose-road-options > summary').click();
 assert.equal(await p.locator('#pose-road-buttons button').count(),4);
 const before=await p.evaluate(()=>draftFormState());
 await p.locator('#pose-road-buttons').getByRole('button',{name:'external strand · 52.2 mm',exact:true}).click();
 await p.locator('#mesh-file').setInputFiles(process.env.FDM_PREVIEW_MESH);await p.waitForFunction(()=>document.querySelector('#mesh-status').textContent.startsWith('Mesh fingerprint matched'));
 const real=JSON.parse(data.get(m.receipts.find(e=>e.pose==='facet-01'&&e.check==='bridge-check').path));
 assert.deepEqual(await p.evaluate(()=>viewer.roadWitness),real.result.metrics.worst.external.strand.design_mm);
 assert.equal(await p.evaluate(()=>draftFormState()),before);
 await p.getByRole('button',{name:'facet-00',exact:true}).click();assert.equal(await p.evaluate(()=>viewer.roadWitness),null);
 await p.locator('#pose-road-buttons').getByRole('button',{name:'internal strand · 122.1 mm',exact:true}).click();
 await p.locator('#pose-road-hide').focus();await p.keyboard.press('Enter');assert.equal(await p.evaluate(()=>viewer.roadWitness),null);
 assert.match(await p.evaluate(()=>document.activeElement.textContent),/internal strand/);
 await p.setViewportSize({width:390,height:844});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await p.locator('#table-file').setInputFiles(path.join(dir,'orientation-table.enriched.json'));
 await p.waitForFunction(()=>document.querySelector('#pose-name').textContent==='Choose a candidate');
 assert.equal(await p.locator('#pose-road-buttons button').count(),0);assert.equal(await p.evaluate(()=>viewer.roadWitness),null);
 await p.getByRole('button',{name:'facet-01',exact:true}).click();assert.equal(await p.locator('#pose-road-buttons button').count(),0);
 assert.deepEqual(errors,[]);console.log('PASS orientation bundle road locations, flipped pose, mesh-load persistence, view-only draft state, pose/table reset and mobile');
}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1)});
