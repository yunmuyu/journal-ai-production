import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {routeFixture,testRef} from './route-test-fixture.mjs';
const {createWorkBuddyQueue}=await import(process.env.DIRECT_QUEUE_MODULE||'./workbuddy-queue.mjs');

function fixture(t,extra={}){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'direct-production-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const route=routeFixture(root,{raster:true}),batchHash=route.sourceReview.archive.sha256;
 const options={root:path.join(root,'jobs'),directProduction:{enabled:true,batchHashes:[batchHash],groups:['raster']},
  assertRoutineEligible:()=>({archive:route.sourceReview.archive,word:route.sourceReview.word}),
  verifyAutomatic:()=>({kind:'automatic-candidate',status:'candidate',manual_status:'pending'}),publish(){},...extra};
 const q=createWorkBuddyQueue(options);
 const input=number=>({key:batchHash+':article:'+number,batchHash,articleId:'article',figureNumber:String(number),mainNumbers:['1','2'],outputNumbers:[String(number)],label:'fixture '+number,group:'raster',sources:[route.sourceReview.archive,route.sourceReview.word],productionRoute:route});
 return {root,route,options,q,input};
}
function candidate(job){
 const jpg=path.join(job.attemptDir,'image.jpg'),png=path.join(job.attemptDir,'image.png');
 fs.writeFileSync(jpg,Buffer.from([255,216,255,217]));fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 return {evidence:'Transport fixture, no artwork validation claim',outputs:[{number:job.figureNumber,...testRef(jpg),preview:png,fontLabel:''}]};
}
test('direct production prepares and returns original tasks without resume, claim or a global lease',async t=>{
 let returned=0;const {q,route,input}=fixture(t,{publish:()=>returned++});
 const first=q.enqueue(input(1));q.pause(first.id);const second=q.enqueue(input(2));q.pause(second.id);
 const a=q.prepareDirect(first.id,route).job,b=q.prepareDirect(second.id,route).job;
 assert.equal(a.id,first.id);assert.equal(a.lease,undefined);assert.equal(b.lease,undefined);assert.equal(q.claim('legacy'),null);
 assert.equal(q.list().length,2);assert.throws(()=>q.resumeRoutine(first.id,route));
 await q.submitDirect(a.id,a.attempt,candidate(a));await q.submitDirect(b.id,b.attempt,candidate(b));
 assert.equal(returned,2);assert.ok(q.list().every(j=>j.state==='ready'&&j.qualityVerification.manualStatus==='pending'&&!j.accepted&&!j.approved));
 assert.equal(q.prepareDirect(a.id,route).alreadyReturned,true);assert.equal(returned,2);
 await assert.rejects(async()=>q.submitDirect(a.id,a.attempt,candidate(a)));
});
test('direct production rejects out-of-scope, approved, changed and duplicate work',t=>{
 const {q,route,input}=fixture(t);
 const foreign=q.enqueue({...input(1),batchHash:'f'.repeat(64)});q.pause(foreign.id);assert.throws(()=>q.prepareDirect(foreign.id,route),/范围/);
 const approved=q.enqueue({...input(2),approved:true});q.pause(approved.id);assert.throws(()=>q.prepareDirect(approved.id,route),/原任务/);
 const duplicate=q.enqueue(input(3));q.pause(duplicate.id);q.enqueue({...input(3),key:'newer'});assert.throws(()=>q.prepareDirect(duplicate.id,route),/同图/);
 const changed=q.enqueue(input(4));q.pause(changed.id);fs.appendFileSync(route.sourceReview.word.path,'changed');assert.throws(()=>q.prepareDirect(changed.id,route),/变化/);
});
test('a direct attempt survives a server restart and elapsed lease time without creating another attempt',t=>{
 const {q,route,input,options}=fixture(t,{now:()=>0});const id=q.enqueue(input(1)).id;q.pause(id);
 const first=q.prepareDirect(id,route).job;
 const before=fs.readFileSync(path.join(first.attemptDir,'task.json'),'utf8');
 const restored=createWorkBuddyQueue({...options,now:()=>999999});
 const again=restored.prepareDirect(id,route).job;
 assert.equal(again.state,'running');assert.equal(again.attempt,first.attempt);assert.equal(again.attemptDir,first.attemptDir);
 assert.equal(fs.readFileSync(path.join(first.attemptDir,'task.json'),'utf8'),before);
});
test('new authoritative feedback during automatic checking blocks direct publication',async t=>{
 let changed=false,returned=0;const {q,route,input}=fixture(t,{assertRoutineEligible:()=>{if(changed)throw Error('feedback changed');return {archive:route.sourceReview.archive,word:route.sourceReview.word};},verifyAutomatic:()=>{changed=true;return {kind:'automatic-candidate',status:'candidate',manual_status:'pending'};},publish:()=>returned++});
 const id=q.enqueue(input(1)).id;q.pause(id);const task=q.prepareDirect(id,route).job;
 await assert.rejects(q.submitDirect(id,task.attempt,candidate(task)),/feedback changed/);assert.equal(returned,0);assert.equal(q.list()[0].state,'failed');
});

test('corrected direct failures retain attempts and reject retry while old lock exists',t=>{
 const {q,route,input}=fixture(t);
 const id=q.enqueue(input(1)).id;q.pause(id);
 const first=q.prepareDirect(id,route).job;q.failDirect(id,first.attempt,'bad evidence');
 const second=q.prepareDirect(id,route).job;q.failDirect(id,second.attempt,'bad frozen schema');
 const lock=path.join(second.attemptDir,'.direct-run.lock');fs.writeFileSync(lock,'still-owned');
 assert.throws(()=>q.prepareDirect(id,route),/安全结束/);
 fs.unlinkSync(lock);
 const third=q.prepareDirect(id,route).job;
 assert.equal(third.attempt,3);assert.notEqual(third.attemptDir,second.attemptDir);
 assert.equal(fs.existsSync(path.join(first.attemptDir,'task.json')),true);
 assert.equal(fs.existsSync(path.join(second.attemptDir,'task.json')),true);
});
