import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {testRef} from './route-test-fixture.mjs';
import {createWorkBuddyHandler} from './workbuddy-http.mjs';
import {productionReport} from './production-observability.mjs';
import {runProductionBatch} from './production-runner.mjs';
import {runProductionRequests} from './production-intake.mjs';

test('real batch CLI returns two gray candidates without dispatch, keeps feedback state and deduplicates repeats',{skip:!process.env.WORKSPACE_TEST_PYTHON},async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'raster-direct-e2e-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const write=(name,value)=>{const p=path.join(root,name);fs.writeFileSync(p,typeof value==='string'||Buffer.isBuffer(value)?value:JSON.stringify(value));return p;};
 const source=testRef(write('source.png',Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=','base64')));
 const archive=testRef(write('archive.zip','fixture archive')),word=testRef(write('word.docx','fixture word')),inventory=testRef(write('inventory.json','{}'));
 const route={version:1,method:'raster-preserve',processing:{operation:'preserve',basis:'Synthetic pixel fixture has no lettering to replace'},sourceReview:{archive,word,inventory,selected:source,candidates:[{...source,kind:'raster',decision:'selected',reason:'Synthetic photo'}],basis:'Synthetic matched source',rasterReason:'Synthetic photo'},requirements:{format:'jpg',fontCheck:'none',widthMm:80}};
 const routeFile=write('route.json',route),history=write('history.json',{checked:true,conclusion:'new',reusable:false,observation:'Synthetic test has no prior outputs'}),frozen=write('frozen.json','[]'),fonts=write('fonts.json','{}');
 const authorRoot=path.join(root,'delivery'),rows=[1,2].map(number=>({id:'F'+number,articleId:'article',number:String(number),author:'fixture',status:'待制作',outputs:[]})),files=new Map();let handler,returned=0,previewFailure=true;
 const server=http.createServer((req,res)=>{
  if(req.url==='/data')return res.end(JSON.stringify({rows}));
  if(req.url==='/preview/F1'&&previewFailure){previewFailure=false;return res.writeHead(503).end();}
  if(files.has(req.url))return res.end(fs.readFileSync(files.get(req.url)));
  handler.handle(req,res,new URL(req.url,origin))||res.writeHead(404).end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;t.after(()=>server.close());
 const config={workerToken:'fixture-only',qualityPython:process.env.WORKSPACE_TEST_PYTHON,catalog:{batchHash:archive.sha256,archive,articles:[{id:'article',word}]},directProduction:{enabled:true,batchHashes:[archive.sha256],groups:['raster']}};
 handler=createWorkBuddyHandler({root:path.join(root,'jobs'),origin,config,figures:()=>rows,assertRoutineEligible:()=>({archive,word}),publish:(job,result)=>{
  returned++;const id='F'+job.figureNumber;files.set('/file/'+id,result.outputs[0].path);files.set('/preview/'+id,result.outputs[0].preview);
  Object.assign(rows.find(row=>row.id===id),{status:'待终检',outputs:result.outputs.map(o=>({number:o.number,file:{token:id,meta:{sha256:o.sha256}}}))});
 },restore(){}});
 const items=[1,2].map(number=>{
  const job=handler.queue.enqueue({key:'fixture-'+number,batchHash:archive.sha256,articleId:'article',figureId:'F'+number,figureNumber:String(number),mainNumbers:['1','2'],outputNumbers:[String(number)],group:'raster',label:'fixture '+number,sources:[archive,word],productionRoute:route});handler.queue.pause(job.id);
  const evidenceFile=write('evidence-'+number+'.json',{producer:'fixture',history:{evidence:history,conclusion:'new',reusable:false,revision_authorization:''},frozen_manifest:frozen,author_roots:[authorRoot],delivery_target:path.join(authorRoot,number+'.jpg'),runtime:{python:process.env.WORKSPACE_TEST_PYTHON,font_profile:fonts},allowed_changes:['grayscale'],immutable_content:['content'],failure_policy:{max_attempts:2,repair:'local-only',time_budget_seconds:null,cost_budget:null}});
  return {id:job.id,routeFile,evidenceFile,outputName:number+'.jpg',plan:{version:1,inputs:[{...source,crop:null}],layout:{mode:'single',gap_px:0},width_mm:80,quality:95}};
 });
 const manifest=write('batch.json',{version:1,items,concurrency:6}),connection=write('worker.json',{origin,workerToken:'fixture-only',workbenchRoot:root});
 const cli=fileURLToPath(new URL('./raster-batch.mjs',import.meta.url));
 let stdout;try{stdout=(await promisify(execFile)(process.execPath,[cli,connection,manifest],{windowsHide:true,timeout:120000})).stdout;}
 catch(error){assert.equal(error.code,1);stdout=error.stdout;}
 const report=JSON.parse(stdout.trim().split('\n').at(-1));assert.equal(report.failed,1);assert.equal(returned,2);
 assert.equal(report.returnedFigures,1);assert.equal(report.failureCounts.visibility_unavailable,1);
 for(const job of handler.queue.list()){
  assert.equal(job.state,'ready');assert.equal(job.lease,undefined);assert.equal(job.qualityVerification.manualStatus,'pending');assert.equal(job.qualityVerification.measurements.nonneutral_pixels,0);
  assert.equal(job.accepted,undefined);assert.ok(fs.existsSync(job.result.outputs[0].preview));
 }
 assert.equal(fs.existsSync(authorRoot),false);
 const repeated=await promisify(execFile)(process.execPath,[cli,connection,manifest],{windowsHide:true,timeout:30000});
 const resumed=JSON.parse(repeated.stdout.trim().split('\n').at(-1));assert.equal(resumed.returnedFigures,1);assert.equal(resumed.failed,0);assert.equal(returned,2);
 const third=await promisify(execFile)(process.execPath,[cli,connection,manifest],{windowsHide:true,timeout:30000});
 assert.ok(JSON.parse(third.stdout.trim().split('\n').at(-1)).results.every(item=>item.status==='already_returned'));assert.equal(returned,2);
 assert.equal(fs.readdirSync(path.join(root,'case-events')).filter(n=>n.endsWith('.json')).length,2,'each visible JPEG creates a deduplicated case event');
 const counts=productionReport({receiptRoots:[path.join(root,'production-receipts')],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'});
 assert.equal(counts.deliveredFigures,2);assert.equal(counts.deliveredOutputs,2);
 rows.push({id:'F3',articleId:'article',number:'3',author:'fixture',type:'raster',reviewVersion:'base',status:'待制作',outputs:[]});
 const rasterPlan={figureId:'F3',baseVersion:'base',requestedAt:new Date().toISOString(),outputRoutes:[{number:'3',productionRoute:route}],
  history:{evidence:testRef(history),conclusion:'new',reusable:false},allowedChanges:['grayscale'],immutableContent:['content'],articleEvidence:'Source fixture has one complete third figure',qualityRoute:'raster'};
 const routedBatch=await runProductionRequests({...config,origin,workbenchRoot:root,python:process.env.WORKSPACE_TEST_PYTHON,fontProfile:fonts},
  {requestedAt:rasterPlan.requestedAt,plans:[rasterPlan],requests:[{figureId:'F3'}]},{executeBatch:runProductionBatch});
 assert.deepEqual(routedBatch.admission.ready,['F3']);
 const created=routedBatch.results[0];assert.equal(routedBatch.returnedFigures,1);assert.equal(routedBatch.returnedOutputs,1);assert.ok(routedBatch.peakToolProcesses.render>=1);
 assert.equal(created.status,'returned',JSON.stringify(created));assert.equal(created.figureId,'F3');assert.equal(returned,3);
 assert.equal(created.deliveryState.stage,'workbench-candidate');assert.equal(created.deliveryState.workbenchReturned,true);assert.equal(created.deliveryState.userAccepted,false);
 assert.equal(handler.queue.list().filter(j=>j.figureId==='F3').length,1);
 const control=await fetch(origin+'/workbuddy/control',{method:'POST',headers:{Origin:origin},body:JSON.stringify({action:'resume',id:items[0].id})});assert.equal(control.status,409);
 const unauthorized=await fetch(origin+'/workbuddy/worker',{method:'POST',body:JSON.stringify({action:'prepare-direct',id:items[0].id,productionRoute:route})});assert.equal(unauthorized.status,403);
 const invalidRoute=structuredClone(route);delete invalidRoute.processing;
 const missing=write('missing-processing.json',invalidRoute),invalid=write('invalid-batch.json',{version:1,items:[{...items[0],routeFile:missing}]});
 const before=JSON.stringify(handler.queue.list());
 await assert.rejects(()=>promisify(execFile)(process.execPath,[cli,connection,invalid],{windowsHide:true,timeout:30000}),error=>error.stdout.includes('加工要求'));
 assert.equal(JSON.stringify(handler.queue.list()),before,'invalid plan must fail before touching a task');
 const faults=write('production-known-faults.json',{version:1,faults:[{id:'fixture-hold',status:'open',engineSignature:null,scope:{sourceHashes:[source.sha256]},evidence:testRef(history),reason:'Confirmed source fixture hold'}]});
 const blockedManifest=write('blocked.json',{version:1,items:[{...items[0],figureId:'F1'}]});
 await assert.rejects(()=>promisify(execFile)(process.execPath,[cli,connection,blockedManifest],{windowsHide:true,timeout:30000}),error=>error.stdout.includes('known_fault'));
 assert.equal(JSON.stringify(handler.queue.list()),before,'known defect must not change server task or start tools');
});
