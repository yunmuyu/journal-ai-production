import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {createWorkBuddyHandler} from './workbuddy-http.mjs';
import {createReviewTriage} from './review-triage.mjs';
import {renderedFixture} from './processing-test-fixture.mjs';
import {testRef} from './route-test-fixture.mjs';
import {runProduction,runProductionBatch,rebindOutputSetEvidence} from './production-runner.mjs';
import {productionReport} from './production-observability.mjs';
import {runProductionRequests} from './production-intake.mjs';

test('multi-output evidence follows registered sources without changing figure or source identity',()=>{
 const route=(number,p)=>({number,productionRoute:{sourceReview:{selected:{path:p,sha256:'a'.repeat(64)}}}});
 const before=[route('6.1','old-1.pdf'),route('6.2','old-2.pdf')],after=[route('6.1','new-1.pdf'),route('6.2','new-2.pdf')];
 const input={version:1,outputs:before.map(r=>({number:r.number,source:{...r.productionRoute.sourceReview.selected}}))};
 const result=rebindOutputSetEvidence(input,before,after);
 assert.equal(result.outputs[1].source.path,'new-2.pdf');assert.equal(input.outputs[1].source.path,'old-2.pdf');
 input.outputs[0].source.sha256='b'.repeat(64);assert.throws(()=>rebindOutputSetEvidence(input,before,after),/来源/);
});

test('one entry renders concurrent ordinary and revision jobs, publishes real PDFs and deduplicates',{skip:!process.env.WORKSPACE_TEST_PYTHON||!process.env.JFW_TEST_FONT_PROFILE},async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'production-entry-'));let handler,review,origin,published=0,previewFailure=true,submitFailure=true;
 const rows=[],articles=[],files=new Map(),rendered=[];
 for(let i=0;i<6;i++){
  const r=renderedFixture(path.join(root,'fixture-'+i),'raster-reletter');rendered.push(r);
  articles.push({id:'A'+i,word:r.task.productionRoute.sourceReview.word});
  rows.push({id:'A'+i+'-F1',articleId:'A'+i,author:'fixture'+i,number:'1',editor:'fixture',type:'graph',status:'待制作',outputs:[],reviewVersion:'baseline',productionRoute:r.task.productionRoute});
 }
 const old=path.join(root,'old.pdf');fs.writeFileSync(old,'%PDF old');rows[2].outputs=[{number:'1',file:{path:old}}];rows[2].feedback={revision:1,text:'replace source lettering'};rows[2].status='异常';
 const producerOld=path.join(root,'producer-old.pdf');fs.writeFileSync(producerOld,'%PDF producer old');rows[3].outputs=[{number:'1',file:{path:producerOld}}];rows[3].status='待终检';
 const batch=rendered[0].task.productionRoute.sourceReview.archive.sha256;
 for(const r of rendered)r.task.productionRoute.sourceReview.archive=rendered[0].task.productionRoute.sourceReview.archive;
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,origin);
  if(url.pathname==='/data'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify({rows,articles}));}
  if(previewFailure&&url.pathname==='/preview/A0-F1-1'){previewFailure=false;return res.writeHead(503).end();}
  if(url.pathname.startsWith('/file/')||url.pathname.startsWith('/preview/')){const file=files.get(url.pathname);if(!file)return res.writeHead(404).end();return res.end(fs.readFileSync(file));}
  if(!handler.handle(req,res,url)&&!review.handle(req,res,url))res.writeHead(404).end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
 t.after(async()=>{await new Promise(resolve=>server.close(resolve));fs.rmSync(root,{recursive:true,force:true});});
 const install=(figure,result)=>{published++;figure.outputs=result.outputs.map(o=>{const token=figure.id+'-'+o.number;files.set('/file/'+token,o.path);files.set('/preview/'+token,o.preview);return {number:o.number,file:{path:o.path,token,meta:{sha256:o.sha256,previewPath:o.preview}}};});figure.status='待终检';figure.reviewVersion='returned';};
 const wbConfig={origin,workerToken:'worker-fixture',reviewerToken:'review-fixture',qualityPython:process.env.WORKSPACE_TEST_PYTHON,directProduction:{enabled:true,batchHashes:[batch],groups:['graph']},catalog:{batchHash:batch,archive:rendered[0].task.productionRoute.sourceReview.archive,articles}};
 handler=createWorkBuddyHandler({root:path.join(root,'workbuddy-jobs'),origin,config:wbConfig,figures:()=>rows,assertRoutineEligible:(job,route)=>({archive:route.sourceReview.archive,word:route.sourceReview.word}),publish:(job,result)=>install(rows.find(r=>r.id===job.figureId),result),getDirectPublicationState:job=>rows.find(r=>r.id===job.figureId)});
 review=createReviewTriage({root:path.join(root,'reviews'),origin,token:wbConfig.reviewerToken,queue:handler.queue,rows,articles,refresh:()=>{},qualityPython:wbConfig.qualityPython,activate:record=>install(rows.find(r=>r.id===record.figureId),record.result),getAcceptance:()=>null});
 const credentialsFile=path.join(root,'config.json');fs.writeFileSync(credentialsFile,JSON.stringify(wbConfig));
 const config={origin,workbenchRoot:root,credentialsFile,python:wbConfig.qualityPython,fontProfile:process.env.JFW_TEST_FONT_PROFILE};
 config.runtimeLock={python:testRef(config.python),fontProfile:testRef(config.fontProfile),engineSignature:JSON.parse(fs.readFileSync(rendered[0].evidence[0].report.path)).engine_signature};
 const realFetch=globalThis.fetch;t.after(()=>{globalThis.fetch=realFetch;});
 globalThis.fetch=async(url,options)=>{
  const body=options?.body&&JSON.parse(options.body);
  if(submitFailure&&body?.action==='submit-imported-pdf'&&handler.queue.list().find(j=>j.id===body.id)?.figureId==='A1-F1'){
   submitFailure=false;throw Error('simulated connection lost before submission');
  }
  const response=await realFetch(url,options);
  if(body?.action==='prepare-import'&&body.task?.figureId==='A4-F1'){
   const value=await response.clone().json();
   const partial=path.join(value.job.attemptDir,'pdf-candidate');fs.mkdirSync(partial);fs.writeFileSync(path.join(partial,'request.json'),'[]');
  }
  if(String(url).endsWith('/review-triage/prepare-candidate')&&response.ok&&body?.newAttempt!==true){
   const value=await response.clone().json(),task=JSON.parse(fs.readFileSync(value.job.commonCandidate.task.path));
   if(task.figureId==='A2-F1'){const partial=path.join(task.attemptDir,'pdf-candidate');fs.mkdirSync(partial);fs.writeFileSync(path.join(partial,'request.json'),'[]');}
  }
  return response;
 };
 const plans=rendered.map((r,i)=>{
  const hp=path.join(root,'history-'+i+'.json');fs.writeFileSync(hp,JSON.stringify({checked:true,conclusion:'new',reusable:false,observation:'Synthetic current source and previous output checked'}));
  return {...(i===2||i===3?{correctionReason:'Explicitly authorized fixture correction'}:{}),figureId:rows[i].id,baseVersion:'baseline',outputRoutes:[{number:'1',productionRoute:r.task.productionRoute}],history:{evidence:testRef(hp),conclusion:'new',reusable:false},qualityRoute:'diagram',allowedChanges:['lettering'],immutableContent:['source geometry'],articleEvidence:'Synthetic Word identity checked',render:[{number:'1',spec:r.evidence[0].spec,sourceRoot:path.join(root,'fixture-'+i,'source')}]};
 });
 const already=await runProduction(config,{...plans[3],correctionReason:undefined,regression:'existing-candidate'});
 assert.equal(already.status,'failed');assert.match(already.error,/existing_candidate/);assert.equal(handler.queue.list().length,0);
 const expired=await runProduction(config,{...plans[0],requestedAt:new Date(Date.now()-181000).toISOString(),regression:'deadline'});
 assert.equal(expired.status,'failed');assert.equal(expired.failure.code,'deadline_exceeded');assert.equal(expired.timingScope,'from_requested_at');assert.equal(handler.queue.list().length,0);
 const invalidHistory=path.join(root,'invalid-history.json');fs.writeFileSync(invalidHistory,JSON.stringify({...JSON.parse(fs.readFileSync(plans[0].history.evidence.path)),unexpected:'field'}));
 const faultFile=path.join(root,'faults.json');fs.writeFileSync(faultFile,JSON.stringify({version:1,faults:[{id:'confirmed-fixture-defect',status:'open',engineSignature:config.runtimeLock.engineSignature,scope:{figureIds:['A0-F1']},evidence:testRef(invalidHistory),reason:'Confirmed fixture defect'}]}));
 const held=await runProduction({...config,knownFaultsFile:faultFile},{...plans[0],regression:'known-fault'});
 assert.equal(held.status,'blocked');assert.equal(held.failure.code,'known_fault');assert.equal(held.toolTimings,undefined);assert.equal(handler.queue.list().length,0);
 const wrongEngine=await runProduction({...config,runtimeLock:{...config.runtimeLock,engineSignature:'wrong'}},{...plans[0],regression:'wrong-engine'});
 assert.equal(wrongEngine.status,'failed');assert.match(wrongEngine.error,/engine_version_mismatch/);assert.equal(handler.queue.list().length,0);
 const changedFont=await runProduction({...config,runtimeLock:{...config.runtimeLock,fontProfile:{...config.runtimeLock.fontProfile,sha256:'0'.repeat(64)}}},{...plans[0],regression:'changed-font'});
 assert.equal(changedFont.status,'failed');assert.match(changedFont.error,/runtime_artifact_hash_changed/);assert.equal(handler.queue.list().length,0);
 const outside=await runProduction(config,{...plans[0],render:[{...plans[0].render[0],sourceRoot:path.join(root,'fixture-1','source')}],regression:'wrong-source-root'});
 assert.equal(outside.status,'failed');assert.equal(outside.toolTimings,undefined);assert.equal(handler.queue.list().length,0);
 assert.equal(outside.failure.code,'plan_rejected','bad input paths are not renderer capability failures');
 const tooWide={...plans[0],render:undefined,rendered:{outputs:rendered[0].outputs,processingEvidence:rendered[0].evidence},outputRoutes:structuredClone(plans[0].outputRoutes),regression:'wide'};
 tooWide.outputRoutes[0].productionRoute.requirements.widthMm=1;
 const wide=await runProduction(config,tooWide);assert.equal(wide.status,'failed');assert.match(wide.error,/rendered_width_exceeds_plan/);assert.equal(handler.queue.list().length,0);
 const invalid=await runProduction(config,{...plans[0],history:{...plans[0].history,evidence:testRef(invalidHistory)}});
 assert.equal(invalid.status,'failed');assert.equal(invalid.stage,'preflight');assert.equal(handler.queue.list().length,0);
 const repeatedFailure=await runProduction(config,{...plans[0],history:{...plans[0].history,evidence:testRef(invalidHistory)}});
 assert.equal(repeatedFailure.retryBlocked,true);assert.equal(repeatedFailure.error,invalid.error);assert.deepEqual(repeatedFailure.failure,invalid.failure);
 const failedPlan=plans[5],failedRoute=failedPlan.outputRoutes[0].productionRoute;
 const failedManifest=path.join(root,'failed-import.json');fs.writeFileSync(failedManifest,JSON.stringify({version:1,articleId:'A5',figureNumber:'1',outputs:rendered[5].outputs}));
 const priorFailed=await handler.queue.prepareImport({kind:'production',label:'fixture5',group:'graph',articleId:'A5',figureId:'A5-F1',figureNumber:'1',mainNumbers:['1'],outputNumbers:['1'],outputRoutes:failedPlan.outputRoutes,batchHash:batch,sources:[failedRoute.sourceReview.archive,failedRoute.sourceReview.word],existingPdfManifest:testRef(failedManifest),sourceEvidence:'Source identity checked',articleEvidence:'Synthetic Word checked'},failedRoute,batch,{existingPdf:true});
 await assert.rejects(()=>handler.queue.submitImportedPdf(priorFailed.job.id,priorFailed.job.attempt,{}));
 assert.equal(handler.queue.list().find(j=>j.id===priorFailed.job.id).state,'failed');
 const completed=[];
 let retryAllowed;
 const intake=await runProductionRequests({...config,retryFailed:true},
  {requestedAt:new Date().toISOString(),plans:[failedPlan],requests:[{figureId:failedPlan.figureId}]},
  {executeBatch:async effective=>{retryAllowed=effective.retryFailed;return {returnedFigures:0,returnedOutputs:0,results:[]};}});
 assert.deepEqual(intake.admission.ready,[failedPlan.figureId]);assert.equal(retryAllowed,true);
 const batchResult=await runProductionBatch({...config,retryFailed:true},plans,{concurrency:6,onResult:r=>completed.push(r.figureId)}),results=batchResult.results;
 assert.equal(batchResult.peakToolProcesses.render,6,'six actual renderer processes must overlap');
 assert.equal(new Set(completed).size,6);
 assert.ok(batchResult.peakToolProcesses.check>=2,'candidate checks must not block the coordinator');
 assert.deepEqual(results.map(r=>r.status),['awaiting-verification','awaiting-verification','returned','returned','returned','returned'],JSON.stringify(results));assert.equal(published,5);
 const recovered=await runProduction(config,plans[0]);assert.equal(recovered.status,'returned');assert.equal(published,5);
 const failedPublish=handler.queue.list().find(j=>j.figureId==='A1-F1');
 await assert.rejects(()=>handler.queue.submitImportedPdf(failedPublish.id,failedPublish.attempt,{}));
 const resumed=await runProduction({...config,retryFailed:true},plans[1]);assert.equal(resumed.status,'returned',JSON.stringify(resumed));assert.equal(published,6);
 assert.equal(handler.queue.list().find(j=>j.id===failedPublish.id).attempt,failedPublish.attempt+1);
 assert.deepEqual(resumed.outputs.map(o=>o.sha256),results[1].outputs.map(o=>o.sha256),'publication retry preserves PDFs without rerender');
 assert.equal(resumed.error,null);assert.equal(resumed.failure,null);
 assert.ok(rows.every(r=>r.status==='待终检'));assert.deepEqual(rows[2].feedback,{revision:1,text:'replace source lettering'});
 const again=await runProduction(config,plans[0]);assert.equal(again.reused,true);assert.equal(published,6);
 assert.equal(again.receipt.id,recovered.receipt.id);assert.equal(again.receiptCreated,false);
 const machineFile=path.join(root,'machine.json'),requestFile=path.join(root,'request.json');
 fs.writeFileSync(machineFile,JSON.stringify(config));fs.writeFileSync(requestFile,JSON.stringify({plans:[plans[0]]}));
 const cli=await promisify(execFile)(process.execPath,[fileURLToPath(new URL('../journal.mjs',import.meta.url)),'produce','--config',machineFile,'--request',requestFile],{windowsHide:true,timeout:60000});
 assert.equal(JSON.parse(cli.stdout).results[0].reused,true,'canonical CLI must reuse the existing receipt');
 assert.equal(published,6,'canonical entry must not create another candidate');
 const counts=productionReport({receiptRoots:[path.join(root,'production-receipts')],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'});
 assert.equal(rows[3].feedback,undefined,'producer correction must not invent user feedback');
 assert.equal(counts.deliveredFigures,6);assert.equal(counts.deliveredOutputs,6);assert.equal(counts.revisionDeliveries,2);
 assert.equal(fs.readdirSync(path.join(root,'case-events')).filter(n=>n.endsWith('.json')).length,6,'visible deliveries create one case event each, including recovered requests');
 assert.equal(batchResult.returnedFigures,4);assert.equal(batchResult.failureCounts.visibility_unavailable,1);
 await assert.rejects(()=>runProductionBatch(config,[plans[0],plans[0]]),/same figure/);
 assert.equal(new Set(results.map(r=>r.outputs[0].path)).size,6);
 assert.equal(handler.queue.list().find(j=>j.figureId==='A4-F1').attempt,2,'incomplete wrapping must create a new attempt, preserving the first');
 assert.equal(handler.queue.list().find(j=>j.figureId==='A5-F1').attempt,2,'failed imported job must resume through a new attempt rather than a duplicate import');
 assert.equal(review.list().find(j=>j.figureId==='A2-F1').commonCandidate.attempt,2,'revision wrapping failure must preserve the first attempt and retry through the common revision entry');
});
