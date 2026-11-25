import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {planCurrentPackage,packageCurrentDelivery} from '../scripts/package-current-delivery.mjs';
function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'package-current-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const current=path.join(root,'当前');fs.mkdirSync(current);
 const file=path.join(current,'a.pdf');fs.writeFileSync(file,'synthetic PDF fixture');
 const sha256=createHash('sha256').update(fs.readFileSync(file)).digest('hex');
 const manifest={schema:'jfw-current-delivery-v1',issues:[],items:[{articleId:'a',author:'Example',number:'1',state:'review',relative:'a.pdf',sha256}]};
 const manifestPath=path.join(current,'manifest.json'),save=()=>fs.writeFileSync(manifestPath,JSON.stringify(manifest));save();
 return {root,file,manifest,manifestPath,save,options:{manifestPath,articleId:'a',output:path.join(root,'author.zip'),python:process.env.WORKSPACE_TEST_PYTHON??'python'}};
}
test('packaging is explicit and selected current figures keep review state',t=>{
 const f=fixture(t),before=fs.readFileSync(f.manifestPath),r=packageCurrentDelivery(f.options);
 assert.equal(r.stateChanged,false);assert.equal(r.files[0].name,'待终检/Example-图1.pdf');assert.deepEqual(fs.readFileSync(f.manifestPath),before);
 const listing=execFileSync(f.options.python,['-c','import zipfile,sys; print("|".join(zipfile.ZipFile(sys.argv[1]).namelist()))',r.output],{encoding:'utf8'});
 assert.match(listing,/交付清单.json/);assert.throws(()=>packageCurrentDelivery(f.options),/new_zip/);
});
test('no author guessing, missing figures, duplicated numbers, changed hashes or issue suppression',t=>{
 const f=fixture(t);
 for(const change of [m=>m.items[0].author='待确认作者',m=>m.items.push({...m.items[0]}),m=>m.issues.push({error:'missing output'}),m=>m.items[0].sha256='wrong']){
  const original=structuredClone(f.manifest);change(f.manifest);f.save();assert.throws(()=>planCurrentPackage(f.options));f.manifest.items=original.items;f.manifest.issues=original.issues;
 }
 f.save();assert.throws(()=>planCurrentPackage({...f.options,numbers:['2']}),/missing/);assert.throws(()=>planCurrentPackage({...f.options,articleId:null}),/explicit/);
});
test('hash-bound explicit subset cannot silently include another article or old source',t=>{
 const f=fixture(t);f.manifest.items.push({...f.manifest.items[0],articleId:'b',number:'2'});f.save();
 assert.equal(planCurrentPackage(f.options).files.length,1);assert.throws(()=>planCurrentPackage({...f.options,numbers:['2']}),/missing/);
 fs.appendFileSync(f.file,'edited');assert.throws(()=>packageCurrentDelivery(f.options),/hash_changed/);assert.equal(fs.existsSync(f.options.output),false);
});
test('manifest path escape is rejected even if hash matches',t=>{
 const f=fixture(t);f.manifest.items[0].relative=f.file;f.save();assert.throws(()=>planCurrentPackage(f.options),/unsafe/);
});
test('canonical optional package command does not require or start the production runtime',t=>{
 const f=fixture(t),config=path.join(f.root,'config.json'),request=path.join(f.root,'request.json');
 fs.writeFileSync(config,JSON.stringify({python:f.options.python}));fs.writeFileSync(request,JSON.stringify(f.options));
 const result=JSON.parse(execFileSync(process.execPath,['journal.mjs','package','--config',config,'--request',request],{encoding:'utf8'}));
 assert.equal(result.stateChanged,false);assert.equal(result.articleId,'a');assert.ok(fs.existsSync(result.output));
});

test('historical snapshots cannot be relabeled current even when old file hashes match',t=>{
 const f=fixture(t);f.manifest.archiveMode='changed-content-only';f.manifest.retainedInCurrent=[];f.save();
 assert.throws(()=>planCurrentPackage(f.options),/authoritative_current_manifest/);
 delete f.manifest.archiveMode;delete f.manifest.retainedInCurrent;f.save();
 const historical=path.join(f.root,'historical.json');fs.copyFileSync(f.manifestPath,historical);
 assert.throws(()=>planCurrentPackage({...f.options,manifestPath:historical}),/authoritative_current_manifest/);
});
