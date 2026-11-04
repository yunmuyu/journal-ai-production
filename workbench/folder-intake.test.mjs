import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {intakeFolder} from './folder-intake.mjs';

test('folder intake uses the existing endpoint and preserves provenance without touching sources',async t=>{
 const python=process.env.WORKSPACE_TEST_PYTHON;if(!python)return t.skip('Python runtime not configured');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'folder-source-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.writeFileSync(path.join(root,'论文.docx'),'word fixture');fs.writeFileSync(path.join(root,'图1.pptx'),'picture fixture');
 fs.mkdirSync(path.join(root,'交付'));fs.writeFileSync(path.join(root,'交付','old.pdf'),'candidate');
 let uploads=0;const send=async(url,options)=>{uploads++;assert.equal(url.pathname,'/archive-intake');assert.equal(options.headers.Origin,'http://127.0.0.1:9999');assert.ok(options.body.length>0);return {ok:true,json:async()=>({batch:{duplicate:uploads===2}})};};
 const request={folder:root,origin:'http://127.0.0.1:9999',editor:'测试',month:11,count:1,python};
 const first=await intakeFolder(request,send),second=await intakeFolder(request,send);
 assert.equal(first.archiveSha256,second.archiveSha256);assert.equal(second.result.batch.duplicate,true);
 const manifest=JSON.parse(fs.readFileSync(first.sourceManifest,'utf8'));
 assert.deepEqual(manifest.members.map(m=>m.path).sort(),['图1.pptx','论文.docx'].sort());
 assert.equal(fs.readFileSync(path.join(root,'论文.docx'),'utf8'),'word fixture');
 await assert.rejects(intakeFolder({...request,origin:'http://example.com'},send),/local_workbench/);
});
