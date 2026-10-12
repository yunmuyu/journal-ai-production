import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {waitForCompletePdf} from '../lib/pdf-output.mjs';

test('waits through delayed creation and partial PDF writes',async()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'jfw-pdf-wait-')),file=path.join(dir,'figure.pdf');
 const child=spawn(process.execPath,['-e',"const fs=require('fs');setTimeout(()=>fs.writeFileSync(process.argv[1],'%PDF-1.7\\npartial'),100);setTimeout(()=>fs.appendFileSync(process.argv[1],'\\n%%EOF\\n'),300);",file],{windowsHide:true});
 const closed=new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error('writer failed')));});
 const started=Date.now();
 try{waitForCompletePdf(file,{timeoutMs:5000,intervalMs:30});assert.ok(Date.now()-started>=300);await closed;}finally{rmSync(dir,{recursive:true,force:true});}
});
test('rejects incomplete or non-PDF output within a bounded timeout',()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'jfw-pdf-invalid-')),file=path.join(dir,'figure.pdf');
 try{for(const value of ['%PDF-1.7\npartial','not-a-pdf\n%%EOF']){writeFileSync(file,value);assert.throws(()=>waitForCompletePdf(file,{timeoutMs:90,intervalMs:20}),/Timed out/);}}finally{rmSync(dir,{recursive:true,force:true});}
});
