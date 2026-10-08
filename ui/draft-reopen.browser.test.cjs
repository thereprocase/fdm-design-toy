const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});try{
 const p=await browser.newPage(),errors=[];let accept=true,dialogs=0;
 p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>{dialogs++;return accept?d.accept():d.dismiss();});
 await p.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
 const table=path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.with-keep-outs.orientation-table.json'),draft=path.join(__dirname,'fixtures/seed-draft.json');
 await p.locator('#table-file').setInputFiles(table);
 const reopen=async()=>{await p.locator('#draft-file').setInputFiles(draft);await p.waitForFunction(()=>document.getElementById('draft-file').value==='');};
 await reopen();assert.equal(await p.locator('.helper-region').count(),6);
 const original=await p.evaluate(()=>workSnapshot());
 await p.locator('.helper-region [data-key="name"]').first().fill('Unsaved helper edit');
 const edited=await p.evaluate(()=>workSnapshot());accept=false;
 await reopen();assert.equal(dialogs,1);assert.deepEqual(await p.evaluate(()=>workSnapshot()),edited);
 accept=true;await reopen();assert.equal(dialogs,2);assert.deepEqual(await p.evaluate(()=>workSnapshot()),original);
 // No artificial empty-file selection: a table reset must allow this exact path again.
 await p.locator('#table-file').setInputFiles(table);await p.waitForFunction(()=>document.querySelectorAll('.helper-region').length===1);
 await reopen();assert.equal(await p.locator('.helper-region').count(),6);assert.deepEqual(await p.evaluate(()=>workSnapshot()),original);
 const bad={name:'invalid-draft.json',mimeType:'application/json',buffer:Buffer.from('{')};
 for(let i=0;i<2;i++){
  await p.locator('#draft-file').setInputFiles(bad);await p.waitForFunction(()=>document.getElementById('draft-file').value==='');
  assert.match(await p.locator('#draft-status').innerText(),/Could not reopen draft/);assert.deepEqual(await p.evaluate(()=>workSnapshot()),original);
 }
 assert.deepEqual(errors,[]);console.log('PASS same draft reopen, cancelled discard/retry, table replacement and malformed retry preserve the expected work');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
