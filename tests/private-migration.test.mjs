import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {exportPrivate,verifyPrivate,restorePrivate} from '../scripts/private-migration.mjs';
test('private migration follows references, strips tokens and excludes dead files',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'journal-move-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const source=path.join(dir,'source');fs.mkdirSync(source);
 const art=path.join(source,'figure.svg');fs.writeFileSync(art,'<svg/>');
 const dead=path.join(source,'failed-attempt.json');fs.writeFileSync(dead,'{}');
 const config=path.join(source,'workbuddy.config.json');fs.writeFileSync(config,JSON.stringify({reviewerToken:'DO-NOT-TRANSFER',source:art}));
 const output=path.join(dir,'export');
 const result=exportPrivate({seeds:[config]},output);
 assert.equal(result.files,2);assert.equal(result.missing,0);
 const manifest=verifyPrivate(output);assert.ok(!manifest.files.some(x=>x.originalPath===dead));
 const saved=JSON.parse(fs.readFileSync(path.join(output,'blobs',manifest.files.find(x=>x.kind==='local-config').sha256)));
 assert.equal(saved.reviewerToken,null);
 assert.throws(()=>restorePrivate(output),/destination_conflict/); // original token config must never be overwritten
 fs.unlinkSync(config);fs.unlinkSync(art);
 assert.equal(restorePrivate(output).restored,2);assert.equal(restorePrivate(output).restored,0);
 fs.writeFileSync(path.join(output,'blobs',manifest.files[0].sha256),'tampered');
 assert.throws(()=>verifyPrivate(output),/hash_mismatch/);
});
