import {routeFixture,transportQuality,testRef} from './route-test-fixture.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createWorkBuddyHandler} from './workbuddy-http.mjs';
test('HTTP browser start → executor CLI command log → artifact callback; auth and restart',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'wb-http-test-'));let handler,published=0,restored=0;const server=http.createServer((req,res)=>{if(!handler.handle(req,res,new URL(req.url,origin)))res.writeHead(404).end();});await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 t.after(()=>{server.close();fs.rmSync(root,{recursive:true,force:true});});
 const config={workerToken:'test-only',reviewerToken:'review-only',origin,pilot:{key:'pilot',label:'fixture',group:'structure',sources:[],outputNumbers:['1'],productionRoute:routeFixture(root)}},options={root:path.join(root,'jobs'),origin,config,publish:()=>published++,restore:()=>restored++,verifyQuality:transportQuality};handler=createWorkBuddyHandler(options);
 let response=await fetch(origin+'/workbuddy/start-pilot',{method:'POST',headers:{Origin:'http://other'},body:'{}'});assert.equal(response.status,403);
 response=await fetch(origin+'/workbuddy/start-pilot',{method:'POST',headers:{Origin:origin},body:'{}'});assert.equal(response.status,200);
 response=await fetch(origin+'/workbuddy/worker',{method:'POST',body:'{"action":"claim"}'});assert.equal(response.status,403);
 const configPath=path.join(root,'config.json');fs.writeFileSync(configPath,JSON.stringify({origin,workerToken:config.workerToken}));const cli=fileURLToPath(new URL('./workbuddy-cli.mjs',import.meta.url));
 const invoke=(...args)=>promisify(execFile)(process.execPath,[cli,configPath,...args],{windowsHide:true});
 const claim=JSON.parse((await invoke('claim')).stdout);assert.ok(claim.job);await invoke('run',claim.leaseFile,process.execPath,'-e','console.log("fixture tool executed")');
 response=await fetch(origin+'/workbuddy/events?id='+claim.job.id);assert.match(JSON.stringify(await response.json()),/fixture tool executed/);
 const pdf=path.join(claim.job.attemptDir,'fixture.pdf'),png=path.join(claim.job.attemptDir,'fixture.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));const result=path.join(root,'result.json');fs.writeFileSync(result,JSON.stringify({quality:{contract:{sha256:'transport-only'}},evidence:'transport fixture, not production artwork',outputs:[{number:'1',path:pdf,preview:png,sha256:createHash('sha256').update(fs.readFileSync(pdf)).digest('hex')}]}));
 await assert.rejects(invoke('complete',claim.leaseFile,result),/submit-candidate/);
 await invoke('submit-candidate',claim.leaseFile,result);assert.equal(published,0);assert.equal(handler.queue.list()[0].state,'review_pending');
 const reviewBody=JSON.stringify({id:claim.job.id,result:JSON.parse(fs.readFileSync(result,'utf8'))});
 response=await fetch(origin+'/workbuddy/review-candidate',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:reviewBody});assert.equal(response.status,403);
 response=await fetch(origin+'/workbuddy/review-candidate',{method:'POST',headers:{Authorization:'Bearer '+config.workerToken,'Content-Type':'application/json'},body:reviewBody});assert.equal(response.status,403);
 response=await fetch(origin+'/workbuddy/review-candidate',{method:'POST',headers:{Authorization:'Bearer '+config.reviewerToken,'Content-Type':'application/json'},body:reviewBody});assert.equal(response.status,200);
 assert.equal(published,1);handler=createWorkBuddyHandler(options);assert.equal(restored,1);assert.equal(handler.queue.list()[0].state,'ready');
 handler.queue.enqueue({...config.pilot,key:'revision-fixture',kind:'revision'});const revision=handler.queue.claim('fixture');handler.queue.fail(revision.id,revision.lease,'requires tool repair');
 response=await fetch(origin+'/workbuddy/control',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({id:revision.id,action:'retry'})});
 assert.equal(response.status,409);assert.equal(handler.queue.list().find(j=>j.id===revision.id).state,'failed');
});
test('partial inventory recheck dispatches only newly unblocked figures',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'wb-inventory-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const productionRoute=routeFixture(root);const asset=productionRoute.sourceReview.selected;
 const config={workerToken:'fixture',catalog:{batchHash:'batch',articles:[{id:'a',author:'A',word:asset}],archive:asset,groups:['graph'],completedKeys:[],productionInstructions:''}};
 const {queue}=createWorkBuddyHandler({root:path.join(root,'jobs'),origin:'http://127.0.0.1',config,publish:()=>{},restore:()=>{}});
 queue.enqueue({key:'inventory',kind:'inventory',group:'00-inventory',sources:[asset]});
 const first=queue.claim('fixture'),figure={number:'1',group:'graph',outputNumbers:['1'],productionRoute,evidence:'paired'};
 await queue.complete(first.id,first.lease,{evidence:'checked',articles:[{articleId:'a',evidence:'captions',figures:[figure,{number:'2',blocked:true,problem:'missing source',evidence:'caption exists'}]}]});
 assert.equal(queue.list().find(j=>j.kind==='inventory').state,'needs_input');assert.equal(queue.list().filter(j=>j.figureNumber).length,1);
 queue.retry(first.id);const second=queue.claim('fixture');
 await queue.complete(second.id,second.lease,{evidence:'checked again',articles:[{articleId:'a',evidence:'captions',figures:[figure,{...figure,number:'2',outputNumbers:['2']}]}]});
 assert.deepEqual(queue.list().filter(j=>j.figureNumber).map(j=>j.figureNumber).sort(),['1','2']);
});

test('restoration uses publication time rather than UUID directory order',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'wb-restore-order-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 for(const [id,updatedAt,label] of [['ffffffff-ffff-ffff-ffff-ffffffffffff','2026-01-01T00:00:00.000Z','old'],['00000000-0000-0000-0000-000000000000','2026-01-02T00:00:00.000Z','corrected']]){
  fs.mkdirSync(path.join(root,id));fs.writeFileSync(path.join(root,id,'job.json'),JSON.stringify({id,label,updatedAt,createdAt:updatedAt,state:'ready',result:{outputs:[]}}));
 }
 const restored=[];createWorkBuddyHandler({root,origin:'http://127.0.0.1',config:{workerToken:'fixture'},publish:()=>{},restore:j=>restored.push(j.label)});
 assert.deepEqual(restored,['old','corrected']);
});
