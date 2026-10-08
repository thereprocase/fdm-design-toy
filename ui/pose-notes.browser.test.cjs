const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const p=await browser.newPage({viewport:{width:390,height:844}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
 await p.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
 const table=path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json');await p.locator('#table-file').setInputFiles(table);
 assert.match(await p.locator('#pose-notes-title').innerText(),/\(0\)/);
 await p.getByRole('button',{name:'facet-00',exact:true}).click();
 const literal='<b>Keep this pose</b> & review the bridge';await p.locator('#rationale').fill(literal);
 await p.locator('#pin-reference').click();await p.getByRole('button',{name:'facet-01',exact:true}).click();await p.locator('#rationale').fill('Alternative needs support review');
 assert.equal(await p.locator('[data-comparison-note="facet-00"]').textContent(),literal);
 assert.equal(await p.locator('[data-comparison-note="facet-01"]').textContent(),'Alternative needs support review');
 assert.equal(await p.locator('[data-comparison-note] b').count(),0);
 assert.match(await p.locator('#pose-notes-title').innerText(),/\(2\)/);
 const before=await p.evaluate(()=>draftFormState());await p.locator('#pose-notes > summary').click();assert.equal(await p.evaluate(()=>draftFormState()),before);
 assert.match(await p.locator('#pose-notes-list').innerText(),/Keep this pose/);assert.equal(await p.locator('#pose-notes-list b').count(),0);
 await p.getByRole('button',{name:'Edit note for facet-00',exact:true}).click();
 assert.equal(await p.locator('#rationale').inputValue(),literal);assert(await p.locator('#rationale').evaluate(e=>document.activeElement===e));assert.match(await p.locator('#planning-pose').innerText(),/facet-00/);
 await p.locator('#rationale').fill('');assert.match(await p.locator('#pose-notes-title').innerText(),/\(1\)/);assert.equal(await p.getByRole('button',{name:'Edit note for facet-00',exact:true}).count(),0);
 assert.equal(await p.locator('[data-comparison-note="facet-00"]').first().textContent(),'No note recorded.');
 // Actual snapshot restore must refresh the list, even with the same selected pose.
 const raw=await p.evaluate(()=>workSnapshot());raw.pose_notes['facet-00']='Restored current note';raw.rationale='Restored current note';
 await p.locator('#work-file').setInputFiles({name:'work.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(raw))});
 await p.waitForFunction(()=>document.getElementById('work-file').value==='');
 assert.match(await p.locator('#pose-notes-title').innerText(),/\(2\)/);assert.match(await p.locator('#pose-notes-list').innerText(),/Restored current note/);
 assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log('PASS pose-note discovery, reference comparison, plain text, no mutation on disclosure, explicit selection/focus, deletion, snapshot refresh and mobile');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
