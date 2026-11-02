import {routeFixture,transportQuality,testRef} from './route-test-fixture.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRevisionHandler} from './revision-http.mjs';
import {checkedArtifact} from './revision-worker.mjs';
import {digest,validateResult} from './revision-worker.mjs';
import {atomicJson,createRevisionJobs} from './revision-jobs.mjs';

test('HTTP submit checks origin and version, deduplicates and reports stale results',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'revision-http-'));
 const file=path.join(root,'source.pdf');fs.writeFileSync(file,'%PDF-fixture');
 const figure={productionRoute:routeFixture(root),id:'F1',articleId:'A1',author:'合成测试',number:'1',reviewVersion:'v1',feedback:{revision:1,text:'修改'},outputs:[{number:'1',file:{path:file}}]};
 let handler;
 const server=http.createServer((req,res)=>handler.handle(req,res,new URL(req.url,'http://localhost')));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 handler=createRevisionHandler({root:path.join(root,'jobs'),config:{},origin,rows:[figure],articles:[],refresh(){},activate(){throw Error('stale result must not activate');},run:async()=>{figure.reviewVersion='v2';return {status:'completed',summary:'done',outputs:[]};}});
 t.after(async()=>{handler.close();await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});});
 const send=(version,from=origin)=>fetch(origin+'/revision-jobs/F1',{method:'POST',headers:{origin:from,'content-type':'application/json'},body:JSON.stringify({version})});
 assert.equal((await send('v1','http://evil.invalid')).status,403);
 assert.equal((await send('old')).status,409);
 figure.status='终检通过';assert.equal((await send('v1')).status,409);delete figure.status;
 const first=await (await send('v1')).json(),second=await (await send('v1')).json();assert.equal(first.job.id,second.job.id);
 await handler.queue.drain();
 const {jobs}=await (await fetch(origin+'/revision-jobs')).json();assert.equal(jobs.length,1);assert.equal(jobs[0].state,'failed');assert.match(jobs[0].message,/变化/);
 assert.throws(()=>createRevisionHandler({root:path.join(root,'jobs'),config:{}}),/已有/);
});

test('candidate files cannot escape task directory',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'revision-path-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const dir=path.join(root,'job');fs.mkdirSync(dir);fs.writeFileSync(path.join(root,'outside.pdf'),'%PDF-');
 assert.throws(()=>checkedArtifact(dir,'../outside.pdf',/\.pdf$/),/目录/);
 fs.writeFileSync(path.join(dir,'inside.pdf'),'%PDF-');assert.equal(checkedArtifact(dir,'inside.pdf',/\.pdf$/),path.join(dir,'inside.pdf'));
});

test('restart after publication restores ready instead of rerunning completed work',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'revision-recover-'));let handler;
 t.after(()=>{handler?.close();fs.rmSync(root,{recursive:true,force:true});});
 const queue=createRevisionJobs({root,run(){},publish(){}});
 const input={figureId:'F1',version:'v1',feedback:{revision:1},outputs:[{number:'1',sha256:'old'}]};
 const job=queue.submit(input),dir=path.join(root,job.id);
 const pdf=path.join(dir,'candidate.pdf'),png=path.join(dir,'preview.png');fs.writeFileSync(pdf,'%PDF-1.7 fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 atomicJson(path.join(dir,'job.json'),{...job,state:'running'});
 atomicJson(path.join(dir,'published.json'),{jobId:job.id,at:new Date().toISOString(),figureId:'F1',feedbackRevision:1,result:{status:'completed',summary:'已回传',evidence:'测试恢复',outputs:[{number:'1',path:pdf,preview:png,sha256:digest(pdf)}]}});
 let activated=0;handler=createRevisionHandler({root,config:{},origin:'http://localhost',rows:[],articles:[],refresh(){},activate(){activated++;},run(){throw Error('must not rerun');}});
 assert.equal(activated,1);assert.equal(handler.queue.list()[0].state,'ready');
});

test('Codex completed result uses the same route and independent-review boundary',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'codex-route-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const pdf=path.join(root,'candidate.pdf'),png=path.join(root,'preview.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 const input={id:'job',productionRoute:routeFixture(root,{raster:true}),outputs:[{number:'1',sha256:'old'}]};
 const result={status:'completed',evidence:'executor says passed',outputs:[{number:'1',path:pdf,preview:png,sha256:digest(pdf),fontLabel:''}]};
 assert.throws(()=>validateResult(root,input,result),/JPG/);
 input.productionRoute=routeFixture(root);assert.throws(()=>validateResult(root,input,result),/独立质量/);
});
