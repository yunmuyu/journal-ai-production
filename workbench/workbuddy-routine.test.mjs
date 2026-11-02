import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {routeFixture} from './route-test-fixture.mjs';
import {routeSourceRefs} from './production-route.mjs';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
import {createWorkBuddyHandler} from './workbuddy-http.mjs';
import {createHash} from 'node:crypto';

function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'routine-trial-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const route=routeFixture(dir,{raster:true}),routineTrial={id:'authorized-three',maxTasks:3,groups:['routine raster']};
 const assertRoutineEligible=j=>({archive:route.sourceReview.archive,word:route.sourceReview.word});
 const options={root:path.join(dir,'jobs'),publish:()=>{throw Error('must not publish');},routineTrial,assertRoutineEligible};
 const input=n=>({key:'figure-'+n,articleId:'registered-paper',figureNumber:String(n),mainNumbers:[String(n)],outputNumbers:[String(n)],label:'figure '+n,group:'routine raster',sources:routeSourceRefs(route),productionRoute:route});
 return {dir,route,routineTrial,options,input};
}
test('autonomous routine resume is opt-in, source-bound, same-job, and capped across restart',t=>{
 const {dir,route,options,input}=fixture(t);let q=createWorkBuddyQueue(options);
 const jobs=[1,2,3,4].map(n=>{const j=q.enqueue(input(n));q.pause(j.id);return j;});
 assert.throws(()=>createWorkBuddyQueue({...options,routineTrial:undefined}).resumeRoutine(jobs[0].id,route),/未启用/);
 // Legacy paused task is explicitly migrated only through the bounded source-checked entry.
 const file=path.join(options.root,jobs[0].id,'job.json'),legacy=JSON.parse(fs.readFileSync(file,'utf8'));delete legacy.productionRoute;legacy.instructions='old generic PDF';fs.writeFileSync(file,JSON.stringify(legacy));q=createWorkBuddyQueue(options);
 const changed=structuredClone(route);changed.sourceReview.word=routeFixture(fs.mkdtempSync(path.join(dir,'other-')),{raster:true}).sourceReview.word;
 assert.throws(()=>q.resumeRoutine(jobs[0].id,changed),/原包及Word/);
 q.resumeRoutine(jobs[0].id,route);assert.equal(q.list().length,4);assert.equal(q.list()[0].attempt,0);assert.equal(q.list().find(j=>j.id===jobs[0].id).state,'queued');
 q=createWorkBuddyQueue(options);q.resumeRoutine(jobs[1].id,route);q=createWorkBuddyQueue(options);q.resumeRoutine(jobs[2].id,route);
 q=createWorkBuddyQueue(options);assert.throws(()=>q.resumeRoutine(jobs[3].id,route),/累计名额/);assert.equal(q.routineOptions().remaining,0);assert.equal(q.list().find(j=>j.id===jobs[3].id).state,'paused');
 assert.equal(q.routineOptions().status,'trial_complete');assert.ok(q.events(jobs[0].id).some(e=>e.message.includes(options.routineTrial.id)));
});
test('routine resume rejects feedback, prior output, other routes, and authoritative user constraints',t=>{
 const {route,options,input}=fixture(t),q=createWorkBuddyQueue(options);
 for(const [n,extra] of [[1,{feedback:{text:'user request'}}],[2,{kind:'revision'}],[3,{approved:true}],[4,{candidateResult:{outputs:[]}}],[5,{attempt:1}],[6,{group:'protected professional'}]]){
  const j=q.enqueue({...input(n),...extra});q.pause(j.id);
  if(n===5){const file=path.join(options.root,j.id,'job.json'),record=JSON.parse(fs.readFileSync(file,'utf8'));record.attempt=1;fs.writeFileSync(file,JSON.stringify(record));assert.throws(()=>createWorkBuddyQueue(options).resumeRoutine(j.id,route),/未生产/);}
  else assert.throws(()=>q.resumeRoutine(j.id,route),/授权范围|未生产/);
 }
 const j=q.enqueue(input(7));q.pause(j.id);assert.throws(()=>createWorkBuddyQueue({...options,assertRoutineEligible(){throw Error('row already approved');}}).resumeRoutine(j.id,route),/already approved/);
 const pdf=structuredClone(route);pdf.method='editable-pdf';pdf.requirements={format:'pdf',fontCheck:'editable',widthMm:80};const other=q.enqueue({...input(8),productionRoute:pdf});q.pause(other.id);assert.throws(()=>q.resumeRoutine(other.id,route),/授权范围/);
 const duplicate=q.enqueue({...input(7),key:'newer-output'});assert.throws(()=>q.resumeRoutine(j.id,route),/同图已有/);assert.equal(duplicate.state,'queued');
});
test('worker HTTP and CLI expose paused reasons then resume one source-checked job without a lease',async t=>{
 const {dir,route,options,input,routineTrial}=fixture(t);let handler;
 const server=http.createServer((req,res)=>handler.handle(req,res,new URL(req.url,origin))||res.writeHead(404).end());await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 t.after(()=>server.close());handler=createWorkBuddyHandler({...options,origin,config:{workerToken:'worker-only',routineTrial},restore:()=>{}});
 const j=handler.queue.enqueue(input(1));handler.queue.pause(j.id);
 const response=await fetch(origin+'/workbuddy/worker',{method:'POST',headers:{Origin:origin},body:JSON.stringify({action:'resume-routine',id:j.id,productionRoute:route})});assert.equal(response.status,403);
 const configFile=path.join(dir,'config.json'),routeFile=path.join(dir,'route.json');fs.writeFileSync(configFile,JSON.stringify({origin,workerToken:'worker-only'}));fs.writeFileSync(routeFile,JSON.stringify(route));
 const cli=fileURLToPath(new URL('./workbuddy-cli.mjs',import.meta.url)),invoke=(...args)=>promisify(execFile)(process.execPath,[cli,configFile,...args],{windowsHide:true});
 const empty=JSON.parse((await invoke('claim')).stdout);assert.equal(empty.job,null);assert.equal(empty.routine.remaining,3);assert.equal(empty.routine.paused[0].eligible,true);assert.match(empty.routine.action,/resume-routine/);
 const restored=JSON.parse((await invoke('resume-routine',j.id,routeFile)).stdout);assert.equal(restored.job.id,j.id);assert.equal(restored.job.state,'queued');assert.equal(handler.queue.list().length,1);
 const claim=JSON.parse((await invoke('claim')).stdout);assert.equal(claim.job.id,j.id);assert.ok(claim.leaseFile);await assert.rejects(invoke('resume-routine',j.id,routeFile),/暂停常规图/);
});

function candidate(j){
 const jpg=path.join(j.attemptDir,'candidate.jpg'),preview=path.join(j.attemptDir,'preview.png');fs.writeFileSync(jpg,Buffer.from([255,216,255,217]));fs.writeFileSync(preview,Buffer.from([137,80,78,71,13,10,26,10]));
 return {evidence:'Transport fixture; not artwork quality evidence',outputs:[{number:j.outputNumbers[0],path:jpg,preview,sha256:createHash('sha256').update(fs.readFileSync(jpg)).digest('hex'),fontLabel:''}]};
}
const automaticReceipt=()=>({kind:'automatic-candidate',status:'candidate',manualStatus:'pending'});
test('opted-in routine returns automatically only after server gate, with no user acceptance and no double publication',async t=>{
 const {route,options,input}=fixture(t);let published=0,release;const blocked=new Promise(r=>release=r);
 const q=createWorkBuddyQueue({...options,routineTrial:{...options.routineTrial,autoReturn:true},publish:()=>published++,verifyAutomatic:async()=>{await blocked;return automaticReceipt();}});
 const id=q.enqueue(input(1)).id;q.pause(id);q.resumeRoutine(id,route);const j=q.claim('producer'),result=candidate(j);
 assert.equal(j.returnMode,'automatic-candidate');assert.equal(JSON.parse(fs.readFileSync(path.join(options.root,id,'job.json'),'utf8')).returnMode,'automatic-candidate');
 const pending=q.submitCandidate(j.id,j.lease,result);assert.equal(published,0);assert.throws(()=>q.submitCandidate(j.id,j.lease,result),/正在回传/);release();await pending;
 const completed=q.list()[0];assert.equal(published,1);assert.equal(completed.state,'ready');assert.equal(completed.qualityVerification.manualStatus,'pending');assert.equal(completed.accepted,undefined);assert.equal(completed.approved,undefined);
 assert.throws(()=>q.submitCandidate(j.id,j.lease,result),/租约/);
});
test('automatic failure retains evidence and permits bounded same-job new-attempt retry by original lease only',async t=>{
 const {route,options,input}=fixture(t);const q=createWorkBuddyQueue({...options,routineTrial:{...options.routineTrial,autoReturn:true,maxAttempts:2},verifyAutomatic:()=>{throw Error('pixel mismatch');}});
 const id=q.enqueue(input(1)).id;q.pause(id);q.resumeRoutine(id,route);const j=q.claim('producer');
 await assert.rejects(q.submitCandidate(id,j.lease,candidate(j)),/pixel mismatch/);assert.equal(q.list()[0].state,'failed');assert.ok(fs.existsSync(path.join(j.attemptDir,'candidate-error.json')));assert.ok(fs.existsSync(path.join(j.attemptDir,'candidate-submission.json')));
 assert.throws(()=>q.retryRoutine(id,'foreign-lease'),/原执行器/);q.retryRoutine(id,j.lease);const next=q.claim('producer');assert.equal(next.id,id);assert.equal(next.attempt,2);assert.notEqual(next.attemptDir,j.attemptDir);
 await assert.rejects(q.submitCandidate(id,next.lease,candidate(next)),/pixel mismatch/);assert.throws(()=>q.retryRoutine(id,next.lease),/次数已达上限/);
});
test('old pending candidates and non-opted-in routes never auto publish; sealed attempts reject route edits',async t=>{
 const {route,options,input}=fixture(t);let automaticCalls=0;const q=createWorkBuddyQueue({...options,verifyAutomatic:()=>{automaticCalls++;return automaticReceipt();}});
 const id=q.enqueue({...input(1),returnMode:'automatic-candidate'}).id;q.pause(id);q.resumeRoutine(id,route);const j=q.claim('producer');
 assert.equal(j.returnMode,'independent-review');assert.equal(JSON.parse(fs.readFileSync(path.join(options.root,id,'job.json'),'utf8')).returnMode,'independent-review');
 const nested=path.join(j.attemptDir,'workspace','.task-quality');fs.mkdirSync(nested,{recursive:true});fs.writeFileSync(path.join(nested,'envelope.json'),'{}');assert.throws(()=>q.prepareRoute(id,j.lease,route),/预检或封存/);
 q.submitCandidate(id,j.lease,candidate(j));assert.equal(q.list()[0].state,'review_pending');
 const restored=createWorkBuddyQueue({...options,routineTrial:{...options.routineTrial,autoReturn:true},verifyAutomatic:()=>{automaticCalls++;return automaticReceipt();}});assert.equal(restored.list()[0].state,'review_pending');assert.equal(automaticCalls,0);assert.throws(()=>restored.retryRoutine(id,j.lease),/原执行器/);
});

test('HTTP awaits automatic candidate gate and CLI retries the original stopped attempt without reviewer token',async t=>{
 const {dir,route,options,input}=fixture(t);let handler,published=0,failGate=true;
 const server=http.createServer((req,res)=>handler.handle(req,res,new URL(req.url,origin))||res.writeHead(404).end());await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;t.after(()=>server.close());
 handler=createWorkBuddyHandler({...options,origin,config:{workerToken:'worker',routineTrial:{...options.routineTrial,autoReturn:true}},publish:()=>published++,restore:()=>{},verifyAutomatic:async()=>{await new Promise(r=>setTimeout(r,10));if(failGate)throw Error('candidate mismatch');return automaticReceipt();}});
 const job=handler.queue.enqueue(input(1));handler.queue.pause(job.id);handler.queue.resumeRoutine(job.id,route);
 const configFile=path.join(dir,'worker.json');fs.writeFileSync(configFile,JSON.stringify({origin,workerToken:'worker'}));const cli=fileURLToPath(new URL('./workbuddy-cli.mjs',import.meta.url));
 const invoke=(...args)=>promisify(execFile)(process.execPath,[cli,configFile,...args],{windowsHide:true});const first=JSON.parse((await invoke('claim')).stdout);
 const resultFile=path.join(dir,'result.json');fs.writeFileSync(resultFile,JSON.stringify(candidate(first.job)));
 await assert.rejects(invoke('submit-candidate',first.leaseFile,resultFile),/candidate mismatch/);assert.equal(published,0);assert.equal(handler.queue.list()[0].state,'failed');
 const firstLease=fs.readFileSync(first.leaseFile,'utf8');await invoke('retry-routine',first.leaseFile);const second=JSON.parse((await invoke('claim')).stdout);assert.equal(second.job.id,job.id);assert.equal(second.job.attempt,2);assert.notEqual(second.leaseFile,first.leaseFile);assert.equal(fs.readFileSync(first.leaseFile,'utf8'),firstLease);
 failGate=false;fs.writeFileSync(resultFile,JSON.stringify(candidate(second.job)));await invoke('submit-candidate',second.leaseFile,resultFile);assert.equal(published,1);assert.equal(handler.queue.list()[0].state,'ready');assert.equal(handler.queue.list()[0].qualityVerification.manualStatus,'pending');
});

test('automatic publication rechecks authoritative feedback after the gate completes',async t=>{
 const {route,options,input}=fixture(t);let newFeedback=false,published=0;
 const q=createWorkBuddyQueue({...options,routineTrial:{...options.routineTrial,autoReturn:true},publish:()=>published++,assertRoutineEligible:j=>{if(newFeedback)throw Error('用户新增批注');return options.assertRoutineEligible(j);},verifyAutomatic:()=>{newFeedback=true;return automaticReceipt();}});
 const id=q.enqueue(input(1)).id;q.pause(id);q.resumeRoutine(id,route);const j=q.claim('producer');await assert.rejects(q.submitCandidate(id,j.lease,candidate(j)),/新增批注/);
 assert.equal(published,0);assert.equal(q.list()[0].state,'failed');
});

test('verified batch enables ordinary raster auto-return without trial but grants no autonomous retry',async t=>{
 const {route,options,input}=fixture(t),batchHash=route.sourceReview.archive.sha256;let published=0,failGate=false;
 const q=createWorkBuddyQueue({...options,routineTrial:undefined,automaticRasterBatches:[batchHash],publish:()=>published++,verifyAutomatic:()=>{if(failGate)throw Error('gate failed');return automaticReceipt();}});
 q.enqueue({...input(1),batchHash});const first=q.claim('worker');assert.equal(first.returnMode,'automatic-candidate');await q.submitCandidate(first.id,first.lease,candidate(first));assert.equal(published,1);assert.equal(q.list()[0].qualityVerification.manualStatus,'pending');
 q.enqueue({...input(2),batchHash});const second=q.claim('worker');failGate=true;await assert.rejects(q.submitCandidate(second.id,second.lease,candidate(second)),/gate failed/);assert.throws(()=>q.retryRoutine(second.id,second.lease),/仅原执行器/);
});

test('unverified batches, editable PDFs and revisions retain independent review mode',t=>{
 const {route,options,input}=fixture(t),batchHash=route.sourceReview.archive.sha256;
 const q=createWorkBuddyQueue({...options,automaticRasterBatches:[batchHash],verifyAutomatic:()=>{throw Error('must not run');}});
 const pdf=structuredClone(route);pdf.method='editable-pdf';pdf.requirements={format:'pdf',fontCheck:'editable',widthMm:80};
 for(const [n,extra] of [[1,{batchHash:'a'.repeat(64)}],[2,{batchHash,productionRoute:pdf}],[3,{batchHash,kind:'revision'}]]){
  q.enqueue({...input(n),...extra});const j=q.claim('worker');assert.equal(j.returnMode,'independent-review');q.fail(j.id,j.lease,'fixture stopped');
 }
});
