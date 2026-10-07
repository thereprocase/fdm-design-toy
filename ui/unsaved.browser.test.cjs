const {chromium}=require('playwright'),path=require('node:path'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage(),errors=[],dialogs=[];let discard=false;
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{dialogs.push({type:d.type(),message:d.message()});await(discard?d.accept():d.dismiss());});
 const table=path.join(__dirname,'../tests/fixtures/orient/spool-rack-g2-ef.orientation-table.json');
 await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
 await page.locator('#table-file').setInputFiles(table);await page.getByRole('button',{name:'facet-00',exact:true}).click();
 await page.locator('#walls').fill('8');await page.locator('#rationale').fill('Keep this unfinished plan');
 await page.locator('#table-file').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{}')});
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Could not load'));
 assert.equal(dialogs.length,0);assert.equal(await page.locator('#walls').inputValue(),'8');
 await page.locator('#table-file').setInputFiles(table);
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('replacement cancelled'));
 assert.equal(dialogs.length,1);assert.equal(await page.locator('#walls').inputValue(),'8');assert.equal(await page.locator('#rationale').inputValue(),'Keep this unfinished plan');
 await page.locator('#draft-file').setInputFiles(path.join(__dirname,'../tests/fixtures/massing/sample-draft.json'));
 await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.includes('replacement cancelled'));
 assert.equal(dialogs.length,2);assert.equal(await page.locator('#walls').inputValue(),'8');
 // A real browser departure can also be cancelled without losing incomplete fields.
 await page.reload({timeout:5000}).catch(()=>{});
 assert.equal(dialogs.at(-1).type,'beforeunload');assert.equal(await page.locator('#walls').inputValue(),'8');
 discard=true;
 await page.locator('#draft-file').setInputFiles(path.join(__dirname,'../tests/fixtures/massing/sample-draft.json'));
 await page.waitForFunction(()=>document.querySelector('#draft-status').textContent.startsWith('Draft restored'));
 assert.equal(await page.locator('#walls').inputValue(),'4');
 const count=dialogs.length;
 await page.locator('#table-file').setInputFiles(table);
 await page.waitForFunction(()=>document.querySelector('#pose-name').textContent==='Choose a candidate');
 assert.equal(dialogs.length,count); // A just-opened, unedited draft needs no discard prompt.
 await page.getByRole('button',{name:'facet-00',exact:true}).click();await page.locator('#shell-only').check();
 await page.locator('#rationale').fill('Shell-only checkpoint test');
 const download=page.waitForEvent('download');await page.locator('#export').click();await download;
 const afterDownload=dialogs.length;await page.reload();assert.equal(dialogs.length,afterDownload);
 assert.deepEqual(errors,[]);console.log('PASS dirty replacement cancellation, invalid-input preservation, browser departure guard and clean checkpoint bypass');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
