import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
import {routeFixture,testRef} from './route-test-fixture.mjs';
test('import retry freezes a new attempt and only corrects final width',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'import-retry-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const route=routeFixture(root),batchHash=route.sourceReview.archive.sha256,pdf=path.join(root,'source.pdf');fs.writeFileSync(pdf,'%PDF test staging only');
 const manifest=path.join(root,'manifest.json');fs.writeFileSync(manifest,JSON.stringify({version:1,articleId:'A',figureNumber:'1',outputs:[{number:'1',...testRef(pdf)}]}));
 const q=createWorkBuddyQueue({root:path.join(root,'jobs'),directProduction:{enabled:true,batchHashes:[batchHash],groups:['graph']},assertRoutineEligible:()=>({archive:route.sourceReview.archive,word:route.sourceReview.word}),publish:()=>assert.fail('retry must never publish')});
 const {job}=await q.prepareImport({kind:'production',label:'fixture 1',articleId:'A',figureId:'A-F1',figureNumber:'1',mainNumbers:['1'],outputNumbers:['1'],batchHash,group:'graph',sources:[route.sourceReview.archive,route.sourceReview.word],existingPdfManifest:testRef(manifest)},route,batchHash,{existingPdf:true});
 const next=q.retryImportedPdf(job.id,job.attempt,{'1':79});
 assert.equal(next.attempt,2);assert.equal(next.productionRoute.requirements.widthMm,79);
 assert.equal(JSON.parse(fs.readFileSync(path.join(job.attemptDir,'task.json'))).productionRoute.requirements.widthMm,80);
 assert.notEqual(next.existingPdf.outputs[0].staged.path,job.existingPdf.outputs[0].staged.path);
 assert.equal(testRef(next.existingPdf.outputs[0].staged.path).sha256,testRef(pdf).sha256);
 assert.throws(()=>q.retryImportedPdf(job.id,1,{'1':79}),/失效/);
 assert.throws(()=>q.retryImportedPdf(job.id,2,{'1':81}),/宽度/);
 fs.appendFileSync(pdf,'changed');assert.throws(()=>q.retryImportedPdf(job.id,2,{'1':79}),/哈希|变化/);
});

test('updated candidate starts new attempt without modifying prior PDF',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'import-replacement-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const route=routeFixture(root),batchHash=route.sourceReview.archive.sha256,pdf=path.join(root,'old.pdf'),next=path.join(root,'new.pdf');
 fs.writeFileSync(pdf,'%PDF old');fs.writeFileSync(next,'%PDF new');
 const mk=(file,out)=>{fs.writeFileSync(file,JSON.stringify({version:1,articleId:'A',figureNumber:'1',outputs:[{number:'1',...testRef(out)}]}));return testRef(file)};
 const first=mk(path.join(root,'old.json'),pdf),replacement=mk(path.join(root,'new.json'),next);
 const q=createWorkBuddyQueue({root:path.join(root,'jobs'),directProduction:{enabled:true,batchHashes:[batchHash],groups:['graph']},assertRoutineEligible:()=>({archive:route.sourceReview.archive,word:route.sourceReview.word}),publish:()=>assert.fail('retry must never publish')});
 const {job}=await q.prepareImport({kind:'production',label:'fixture 1',articleId:'A',figureId:'A-F1',figureNumber:'1',mainNumbers:['1'],outputNumbers:['1'],batchHash,group:'graph',sources:[route.sourceReview.archive,route.sourceReview.word],existingPdfManifest:first},route,batchHash,{existingPdf:true});
 const result=q.retryImportedPdf(job.id,1,{'1':79},replacement);
 assert.equal(result.attempt,2);assert.equal(testRef(result.existingPdf.outputs[0].staged.path).sha256,testRef(next).sha256);
 assert.equal(testRef(job.existingPdf.outputs[0].staged.path).sha256,testRef(pdf).sha256);
});
