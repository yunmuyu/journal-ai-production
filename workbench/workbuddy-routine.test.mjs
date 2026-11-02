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
