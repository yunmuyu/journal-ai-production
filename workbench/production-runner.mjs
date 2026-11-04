// Coordinator-owned entry: semantic decisions in, verified workbench receipt out.
import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {acquireDirectRunLock} from './raster-batch.mjs';
import {atomicJson} from './revision-jobs.mjs';
import {routeSourceRefs,assertOutputRoutes} from './production-route.mjs';
import {processingRequirement,assertRebuildLayout} from './processing-evidence.mjs';
import {classifyProductionFailure,verifyProductionDelivery} from './production-observability.mjs';
import {fixedProductionRuntime,assertRenderedBoundary,assertPlanSources} from './fixed-production-runtime.mjs';
import {assertDispatchAllowed,assertConfirmedRoute,assertStableRouteDecision,bindAuthoritativeSources,effectiveProductionType,productionTaskGroup} from './production-admission.mjs';
import {discoverPdfChart,loadBoundChartPlan,saveBoundChartPlan} from './chart-route-discovery.mjs';
import {recordFailureCase,recordDeliveryCases,searchFailureAlternatives} from './figure-case-index.mjs';
import {materializeConfirmedSeries} from './chart-binding-adapter.mjs';
import {extractToolDiagnostic} from './tool-diagnostics.mjs';
import {verifyImportedPdfCandidate} from './imported-pdf.mjs';

const exec=promisify(execFile),read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const ref=p=>({path:fs.realpathSync(p),sha256:hash(p)});
function checked(r){if(!r?.path||hash(r.path)!==r.sha256)throw Error('Source or evidence changed: '+r?.path);return r;}
const safe=value=>{if(!/^[\w.-]+$/.test(value))throw Error('Invalid task identity');return value;};

export function rebindOutputSetEvidence(evidence,originalRoutes,registeredRoutes){
 const output=structuredClone(evidence);
 if(!Array.isArray(output.outputs)||!Array.isArray(originalRoutes)||originalRoutes.length!==registeredRoutes.length)throw Error('输出集合来源不完整');
 for(let i=0;i<originalRoutes.length;i++){
  const old=originalRoutes[i],current=registeredRoutes[i],item=output.outputs.find(x=>x.number===old.number);
  const a=old.productionRoute.sourceReview.selected,b=current.productionRoute.sourceReview.selected;
  if(!item||current.number!==old.number||item.source?.sha256!==a.sha256||path.resolve(item.source.path)!==path.resolve(a.path)||b.sha256!==a.sha256)throw Error('输出集合来源与已注册源件不符');
  item.source={...b};
 }
 return output;
}

export async function runProduction(config,plan,{onToolEvent=()=>{}}={}){
 if(plan.outputRoutes?.length&&plan.outputRoutes.every(entry=>entry.productionRoute?.method==='raster-preserve')){
  const {runRasterProductionPlan}=await import('./raster-production-plan.mjs');
  try{return await runRasterProductionPlan(config,plan,{onToolEvent});}
  catch(error){return {figureId:plan.figureId,status:'failed',stage:'preflight',error:error.message,diagnostic:extractToolDiagnostic(error),failure:classifyProductionFailure(error,'preflight')};}
 }
 let requestedAt=plan.requestedAt??new Date().toISOString(),started=Date.parse(requestedAt);
 if(!Number.isFinite(started)||started>Date.now()+5000)throw Error('invalid_requested_at');
 let deadline=started+180000;
 const timeLeft=stage=>{const remaining=deadline-Date.now();if(remaining<=0){const error=Error('three_minute_deadline: '+stage);error.code='three_minute_deadline';throw error;}return remaining;};
 const root=path.join(fs.realpathSync(config.workbenchRoot),'production-runs',safe(plan.figureId));fs.mkdirSync(root,{recursive:true});
 const lock=path.join(root,'.run.lock'),owner=acquireDirectRunLock(lock);
 const {requestedAt:requestClock,...executionPlan}=plan;
 const key=createHash('sha256').update(JSON.stringify(executionPlan)).digest('hex');
 const legacy=path.join(root,createHash('sha256').update(JSON.stringify(plan)).digest('hex'));
 const dir=fs.existsSync(path.join(root,key))?path.join(root,key):fs.existsSync(legacy)?legacy:path.join(root,key);fs.mkdirSync(dir,{recursive:true});
 const statePath=path.join(dir,'state.json');let state=fs.existsSync(statePath)?read(statePath):{version:1,figureId:plan.figureId,startedAt:new Date().toISOString()};
 // Retrying an identical plan keeps its original end-to-end clock.
 const originalStart=Date.parse(state.requestStartedAt);
 if(config.retryFailed===true&&Number.isFinite(originalStart)&&originalStart<started){
  requestedAt=state.requestStartedAt;started=originalStart;deadline=started+180000;
 }
 const save=changes=>{state={...state,...changes,requestStartedAt:requestedAt,timingScope:plan.requestedAt?'from_requested_at':'execution_only',elapsedMs:Date.now()-started};atomicJson(statePath,state);};
 const write=(name,value)=>{const p=path.join(dir,name);if(fs.existsSync(p)){if(JSON.stringify(read(p))!==JSON.stringify(value))throw Error('Frozen input changed: '+name);}else atomicJson(p,value);return ref(p);};
 let credentials;const origin=config.origin;
 const api=async(endpoint,body,review=false)=>{
  const response=await fetch(origin+endpoint,{method:'POST',headers:{Origin:origin,Authorization:'Bearer '+credentials[review?'reviewerToken':'workerToken'],'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(Math.max(1,Math.min(120000,timeLeft(state.stage??'request'))))});
  const value=await response.json();if(!response.ok)throw Error(value.error??JSON.stringify(value));return value;
 };
 const getData=async()=>{const response=await fetch(origin+'/data',{signal:AbortSignal.timeout(Math.max(1,Math.min(30000,timeLeft(state.stage??'preflight'))))});if(!response.ok)throw Error('Workbench unavailable');return response.json();};
 const runTool=async(stage,args)=>{
  const started=Date.now();onToolEvent(stage,1);
  try{return await exec(process.execPath,args,{windowsHide:true,timeout:timeLeft(stage),maxBuffer:4*1024*1024});}
  finally{onToolEvent(stage,-1);save({toolTimings:[...(state.toolTimings??[]),{stage,elapsedMs:Date.now()-started}]});}
 };
 const verifyVisible=async(expected)=>{
  const result=await verifyProductionDelivery({origin,receiptRoot:config.receiptRoot??path.join(config.workbenchRoot,'production-receipts')},
   {figureId:plan.figureId,outputs:expected,batchHash:plan.outputRoutes[0].productionRoute.sourceReview.archive.sha256,kind:state.prepared?.kind??'ordinary',historical:state.status==='returned'&&!state.receipt});
  save({receipt:result.receipt,receiptCreated:result.newReceipt});return result.figure;
 };
 try{
  credentials=read(config.credentialsFile);
  if(state.status==='returned'||state.status==='awaiting-verification'){
   const reused=state.status==='returned';
   let verifiedFigure;
   try{verifiedFigure=await verifyVisible(state.outputs);}catch(error){
    const figure=(await getData()).rows.find(r=>r.id===plan.figureId);
    const visible=figure?.outputs?.length===state.outputs.length&&state.outputs.every(o=>figure.outputs.some(a=>a.number===o.number&&a.file?.meta?.sha256===o.sha256));
    if(reused||visible||state.stage!=='publish'||!state.candidate)throw error;
    if(!figure)throw Error('figure_not_in_workbench: '+plan.figureId);
    if(Object.hasOwn(state,'decisionSnapshot'))assertStableRouteDecision({decision:state.decisionSnapshot},figure);
    assertConfirmedRoute(figure,plan);
    checked(state.candidate);const candidate=read(state.candidate.path),prepared=state.prepared,task=read(prepared.task);
    if(prepared.kind==='revision')await api('/review-triage/import-candidate',{id:prepared.id,candidate},true);
    else{
     const response=await fetch(origin+'/workbuddy/status',{signal:AbortSignal.timeout(30000)});if(!response.ok)throw error;
     const job=(await response.json()).jobs.find(j=>j.id===prepared.id);
     if(job?.attempt!==task.attempt)throw Error('Publication attempt changed; cannot replay');
     if(job.state==='running')await api('/workbuddy/worker',{action:'submit-imported-pdf',id:prepared.id,batchHash:prepared.batchHash,attempt:task.attempt,input:candidate});
     else if(job.state==='ready'){
      const input=Object.fromEntries(['kind','label','group','articleId','figureId','figureNumber','mainNumbers','outputNumbers','outputRoutes','outputSetEvidence','batchHash','sources','sourceEvidence','articleEvidence'].map(k=>[k,task[k]]));
      input.existingPdfManifest=task.importOrigins.manifest;
      await api('/workbuddy/worker',{action:'prepare-import',batchHash:prepared.batchHash,task:input,productionRoute:task.productionRoute,existingPdf:true});
     }else if(job.state==='failed'&&config.retryFailed===true){
      if(figure.reviewVersion!==state.baseline||figure.outputs?.length)throw Error('Publication baseline changed; cannot retry');
      await fixedProductionRuntime(config);
      // A repaired checker must validate the unchanged candidate before a new
      // isolated import attempt is allowed. Never rerender or weaken its checks.
      verifyImportedPdfCandidate(task,candidate,{python:config.python});
      const retried=await api('/workbuddy/worker',{action:'retry-imported-pdf',id:prepared.id,batchHash:prepared.batchHash,attempt:task.attempt,widths:Object.fromEntries(task.outputRoutes.map(r=>[r.number,r.productionRoute.requirements.widthMm]))});
      const nextTask=path.join(retried.job.attemptDir,'task.json');
      const wrapped=await runTool('check',[fileURLToPath(new URL('./pdf-candidate.mjs',import.meta.url)),nextTask,path.join(dir,'rendered-input.json'),path.join(dir,'context.json')]);
      const nextRef=JSON.parse(wrapped.stdout).candidate,nextCandidate=read(checked(nextRef).path);
      save({prepared:{...prepared,task:nextTask},candidate:nextRef,outputs:nextCandidate.outputs,stage:'publish'});
      await api('/workbuddy/worker',{action:'submit-imported-pdf',id:prepared.id,batchHash:prepared.batchHash,attempt:retried.job.attempt,input:nextCandidate});
     }else throw Error('Publication blocked at server: '+job?.state+'; '+job?.message);
    }
    verifiedFigure=await verifyVisible(state.outputs);
   }
   if(state.status!=='returned')save({status:'returned',stage:'visible',returnedAt:new Date().toISOString(),error:null,failure:null});
   else if(state.error||state.failure)save({error:null,failure:null});
   try{save({caseEvents:recordDeliveryCases(path.join(config.workbenchRoot,'case-events'),{figure:verifiedFigure,plan,outputs:state.outputs,discovery:state.routeDiscovery,engineSignature:config.runtimeLock?.engineSignature})});}catch(error){save({caseIndexError:error.message});}
   return {...state,reused};
  }
  try{assertDispatchAllowed(config,plan);}catch(error){save({stage:'preflight'});throw error;}
  if(state.status==='failed'){
   if(!config.retryFailed)return {...state,retryBlocked:true};
   save({failures:[...(state.failures??[]),{stage:state.stage,error:state.error,failure:state.failure,diagnostic:state.diagnostic,at:state.failedAt}],status:'retrying',error:null,failure:null,diagnostic:null,failedAt:null});
  }
  timeLeft('preflight');
  const data=await getData(),figure=data.rows.find(r=>r.id===plan.figureId);
  if(!figure||figure.status==='终检通过')throw Error('Missing or already accepted figure');
  if(figure.outputs?.length&&!plan.correctionReason)throw Error('existing_candidate: 已有候选，未指定制作侧更正');
  timeLeft('preflight');
  if(plan.baseVersion!==figure.reviewVersion)throw Error('Plan baseline is stale');
  assertConfirmedRoute(figure,plan);
  plan=materializeConfirmedSeries(plan,write);
  assertDispatchAllowed(config,plan);
  save({stage:'preflight',author:figure.author,editor:figure.editor,articleId:figure.articleId,number:figure.number});
  const runtime=await fixedProductionRuntime(config);
  if(plan.qualityRoute==='source-preserving-chart'||/图表|曲线|柱状/.test(effectiveProductionType(figure,plan))){
   const selected=plan.outputRoutes?.[0]?.productionRoute?.sourceReview?.selected;
   if(selected?.path&&path.extname(selected.path).toLowerCase()==='.pdf'){
    save({stage:'route_discovery'});timeLeft('route_discovery');
    const discovery=await discoverPdfChart({caseIndexPath:config.caseIndexPath,figure,article:data.articles?.find(a=>a.id===figure.articleId),source:selected,python:config.python,plan,engineSignature:runtime.signature,rows:data.rows,eventDirectory:path.join(config.workbenchRoot,'case-events'),allowExistingCandidate:Boolean(plan.correctionReason),timeoutMs:timeLeft('route_discovery')});
    if(state.routeDiscovery?.planBinding&&JSON.stringify(state.routeDiscovery.planBinding)!==JSON.stringify(discovery.planBinding))throw Error('chart_plan_binding_changed');
    save({routeDiscovery:discovery,requestedAt});
    if(discovery.status==='blocked_known_failure'){const error=Error('known_fault: 已有同源、同版本、同范围的失败证据');error.code='known_fault';error.faultIds=discovery.blockedIdenticalAttempts.map(x=>x.id);error.failureAction='correct_plan';throw error;}
    if(discovery.status!=='ready')throw Error('chart_route_'+discovery.status+': '+JSON.stringify(discovery.routes));
    save({chartPlanRecord:saveBoundChartPlan(path.join(root,'chart-plans'),{figure,source:selected,discovery,plan})});
   }
  }
  timeLeft('route_discovery');
  checked(plan.history.evidence);
  const history=read(plan.history.evidence.path);
  if(Object.keys(history).sort().join(',')!=='checked,conclusion,observation,reusable'||history.checked!==true||!['reuse','new'].includes(history.conclusion)||history.conclusion!==plan.history.conclusion||history.reusable!==plan.history.reusable||typeof history.observation!=='string'||!history.observation.trim())throw Error('History evidence requires checked/conclusion/reusable/observation matching the plan; conclusion must be reuse or new');
  const revision=Boolean(figure.outputs?.length||figure.feedback?.revision);
  const routes=structuredClone(plan.outputRoutes);
  bindAuthoritativeSources(credentials,figure.articleId,routes);
  if(!routes?.length||routes.some(r=>r.productionRoute.method!=='editable-pdf'))throw Error('PDF plan requires editable output routes; use existing raster batch for preserve jobs');
  routes.forEach(entry=>processingRequirement(entry.productionRoute));
  // Register byte-identical derived sources inside the authoritative workbench space.
  const sourceDir=path.join(dir,'sources');fs.mkdirSync(sourceDir,{recursive:true});
  for(const entry of routes){
   const s=entry.productionRoute.sourceReview;
   const register=source=>{
    checked(source);const dest=path.join(sourceDir,source.sha256+path.extname(source.path));
    if(!fs.existsSync(dest))fs.copyFileSync(source.path,dest,fs.constants.COPYFILE_EXCL);
    if(hash(dest)!==source.sha256)throw Error('Registered source changed');return {...source,path:fs.realpathSync(dest)};
   };
   if(!revision)s.inventory=register(s.inventory);
   s.selected=register(s.selected);s.candidates=s.candidates.map(register);
   if(s.additionalSelected)s.additionalSelected=s.additionalSelected.map(register);
  }
  const numbers=routes.map(r=>r.number),route=routes[0].productionRoute;
  assertOutputRoutes({figureNumber:figure.number,outputNumbers:numbers,productionRoute:route},routes);
  let outputSetEvidence;
  if(numbers.length>1||numbers[0]!==figure.number){
   checked(plan.outputSetEvidence);
   outputSetEvidence=write('output-set-evidence.json',rebindOutputSetEvidence(read(plan.outputSetEvidence.path),plan.outputRoutes,routes));
  }
  save({status:'processing',stage:'preflight',baseline:figure.reviewVersion,decisionSnapshot:figure.decision??null});
  let rendered=plan.rendered??(fs.existsSync(path.join(dir,'rendered-input.json'))?read(path.join(dir,'rendered-input.json')):null);
  if(!rendered){
   rendered={outputs:[],processingEvidence:[],summary:plan.summary};
   for(const item of plan.render){
    save({stage:'preflight'});
    checked(item.spec);const spec=read(item.spec.path),out=path.join(dir,'render',safe(item.number));fs.mkdirSync(out,{recursive:true});
    assertPlanSources(spec,item.sourceRoot,out);
    const snapshot=path.join(out,'input.spec.json');if(!fs.existsSync(snapshot))fs.copyFileSync(item.spec.path,snapshot,fs.constants.COPYFILE_EXCL);checked({...item.spec,path:snapshot});
    const command=[fileURLToPath(new URL('./run-public-pdf.mjs',import.meta.url)),config.python,'render',snapshot,'--source-root',item.sourceRoot,'--profile',config.fontProfile,'--output',out];
    save({stage:'render'});
    const result=await runTool('render',command);fs.writeFileSync(path.join(out,'execution.log'),result.stdout+'\n'+result.stderr);
    save({stage:'check'});
    const folder=path.join(out,spec.author,spec.id),report=read(path.join(folder,'report.json'));
    const pdfs=fs.readdirSync(folder).filter(n=>n.endsWith('.pdf'));if(pdfs.length!==1)throw Error('Renderer output is ambiguous');
    rendered.outputs.push({number:item.number,...ref(path.join(folder,pdfs[0]))});
    rendered.processingEvidence.push({number:item.number,report:ref(path.join(folder,'report.json')),spec:ref(path.join(folder,'figure.spec.json')),sourceRoot:item.sourceRoot});
    if(report.status!=='candidate-rendered')throw Error('Renderer did not produce a candidate');
   }
  }
  // Physical width comes from the bound renderer report, never the Word display width.
  save({stage:'check'});
  for(const entry of routes){const evidence=rendered.processingEvidence.find(e=>e.number===entry.number),output=rendered.outputs.find(o=>o.number===entry.number);checked(evidence.report);checked(output);const report=read(evidence.report.path);entry.productionRoute.requirements.widthMm=assertRenderedBoundary(report,output,entry.productionRoute,runtime.signature);if(entry.productionRoute.processing.operation==='rebuild')assertRebuildLayout(report);}
  const input=write('rendered-input.json',rendered);
  const latest=(await getData()).rows.find(r=>r.id===plan.figureId);if(latest.reviewVersion!==figure.reviewVersion)throw Error('Figure changed during processing');
  assertStableRouteDecision(figure,latest);assertConfirmedRoute(latest,plan);
  await fixedProductionRuntime(config);
  save({stage:'prepare'});
  let prepared=state.prepared;
  let existing=config.preparedTasks?.[figure.id];
  if(!prepared&&!existing){
   const response=await fetch(origin+'/workbuddy/status',{signal:AbortSignal.timeout(30000)});if(!response.ok)throw Error('Cannot inspect prior imported task');
   const jobs=(await response.json()).jobs.filter(j=>j.figureId===figure.id&&(j.state==='running'||config.retryFailed===true&&j.state==='failed')&&/^[a-f0-9-]{36}$/.test(j.id)&&Number.isSafeInteger(j.attempt));
   const candidates=jobs.map(j=>path.join(config.workbenchRoot,'workbuddy-jobs',j.id,String(j.attempt),'task.json')).filter(p=>fs.existsSync(p)&&read(p).executionMode==='imported-pdf');
   if(candidates.length>1)throw Error('Multiple prior imported tasks require reconciliation');
   if(candidates.length===1)existing=ref(candidates[0]);
  }
  if(!prepared&&existing){
   checked(existing);const prior=read(existing.path);
   const response=await fetch(origin+'/workbuddy/status',{signal:AbortSignal.timeout(30000)});if(!response.ok)throw Error('Cannot verify prepared task');
   const live=(await response.json()).jobs.find(j=>j.id===prior.id);
   if(revision||prior.figureId!==figure.id||prior.executionMode!=='imported-pdf'||!(live?.state==='running'||config.retryFailed===true&&live?.state==='failed')||live.attempt!==prior.attempt)throw Error('Prepared task is not resumable');
   if(JSON.stringify(prior.outputNumbers)!==JSON.stringify(numbers)||!['archive','word','selected'].every(k=>prior.productionRoute.sourceReview[k].sha256===route.sourceReview[k].sha256))throw Error('Prepared source or output identity differs');
   let widthChanged=false,outputChanged=false;
   for(const entry of routes){
    const previous=prior.outputRoutes.find(r=>r.number===entry.number),output=rendered.outputs.find(o=>o.number===entry.number),staged=prior.existingPdf.outputs.find(o=>o.number===entry.number)?.staged;
    if(!previous||JSON.stringify(previous.productionRoute.processing)!==JSON.stringify(entry.productionRoute.processing))throw Error('Prepared processing plan differs; do not overwrite it');
    outputChanged ||= staged?.sha256!==output?.sha256;
    const before={...previous.productionRoute.requirements},after={...entry.productionRoute.requirements};delete before.widthMm;delete after.widthMm;
    if(JSON.stringify(before)!==JSON.stringify(after)||!['archive','word','selected'].every(k=>previous.productionRoute.sourceReview[k].sha256===entry.productionRoute.sourceReview[k].sha256))throw Error('Prepared output source or publication rules differ');
    widthChanged ||= Math.abs(previous.productionRoute.requirements.widthMm-entry.productionRoute.requirements.widthMm)>.01;
   }
   const replacementManifest=outputChanged?write('replacement-pdf-manifest.json',{version:1,articleId:figure.articleId,figureNumber:figure.number,outputs:rendered.outputs}):undefined;
   const adopted=widthChanged||outputChanged||live.state==='failed'?(await api('/workbuddy/worker',{action:'retry-imported-pdf',id:prior.id,batchHash:prior.batchHash,attempt:prior.attempt,widths:Object.fromEntries(routes.map(r=>[r.number,r.productionRoute.requirements.widthMm])),replacementManifest})).job:prior;
   prepared={kind:'ordinary',id:adopted.id,task:path.join(adopted.attemptDir,'task.json'),batchHash:adopted.batchHash};save({prepared});
  }
  if(!prepared){
   if(revision){
    const submitted=await api('/revision-jobs/'+figure.id,{version:figure.reviewVersion,reason:plan.correctionReason??''},true);
    const result=await api('/review-triage/prepare-candidate',{id:submitted.job.id,productionRoute:route,outputRoutes:routes},true);
    prepared={kind:'revision',id:submitted.job.id,task:result.job.commonCandidate.task.path};
   }else{
    const manifest=write('pdf-manifest.json',{version:1,articleId:figure.articleId,figureNumber:figure.number,outputs:rendered.outputs});
    const task={kind:'production',articleId:figure.articleId,figureId:figure.id,figureNumber:figure.number,batchHash:route.sourceReview.archive.sha256,group:productionTaskGroup(figure,plan),label:figure.author+' 图'+figure.number,mainNumbers:data.rows.filter(r=>r.articleId===figure.articleId).map(r=>r.number),outputNumbers:numbers,outputRoutes:routes,...(outputSetEvidence?{outputSetEvidence}:{}),sources:routes.flatMap(r=>routeSourceRefs(r.productionRoute)),existingPdfManifest:manifest,sourceEvidence:route.sourceReview.basis,articleEvidence:plan.articleEvidence};
    const result=await api('/workbuddy/worker',{action:'prepare-import',batchHash:task.batchHash,task,productionRoute:route,existingPdf:true});
    prepared={kind:'ordinary',id:result.job.id,task:path.join(result.job.attemptDir,'task.json'),batchHash:task.batchHash};
   }
   save({prepared});
  }
  let task=read(prepared.task);
  const partial=path.join(task.attemptDir,'pdf-candidate');
  if(config.retryFailed&&prepared.kind==='ordinary'&&fs.existsSync(partial)&&!fs.existsSync(path.join(partial,'candidate.json'))){
   const retried=await api('/workbuddy/worker',{action:'retry-imported-pdf',id:prepared.id,batchHash:prepared.batchHash,attempt:task.attempt,widths:Object.fromEntries(routes.map(r=>[r.number,r.productionRoute.requirements.widthMm]))});
   prepared={...prepared,task:path.join(retried.job.attemptDir,'task.json')};save({prepared});task=read(prepared.task);
  }
  if(config.retryFailed&&prepared.kind==='revision'&&fs.existsSync(partial)&&!fs.existsSync(path.join(partial,'candidate.json'))){
   const retried=await api('/review-triage/prepare-candidate',{id:prepared.id,productionRoute:route,outputRoutes:routes,newAttempt:true},true);
   prepared={...prepared,task:retried.job.commonCandidate.task.path};save({prepared});task=read(prepared.task);
  }
  const targets=path.join(config.workbenchRoot,'review-targets');fs.mkdirSync(targets,{recursive:true});
  const frozen=write('frozen.json',data.rows.filter(r=>r.status==='终检通过').flatMap(r=>r.outputs.map(o=>ref(o.file.path))));
  const context=write('context.json',{producer:'public-production-runner',qualityRoute:plan.qualityRoute,history:{...plan.history,revision_authorization:figure.feedback?.text??''},frozen_manifest:frozen,author_roots:[targets],delivery_targets:Object.fromEntries(numbers.map(n=>[n,path.join(targets,figure.id+'-'+safe(n)+'.pdf')])),runtime:{python:ref(config.python),font_profile:ref(config.fontProfile)},allowed_changes:plan.allowedChanges,immutable_content:plan.immutableContent,failure_policy:{max_attempts:2,repair:'local-only',time_budget_seconds:null,cost_budget:null}});
  save({stage:'check'});
  const wrapping=await runTool('check',[fileURLToPath(new URL('./pdf-candidate.mjs',import.meta.url)),prepared.task,input.path,context.path]);
  fs.writeFileSync(path.join(dir,'candidate-check.log'),wrapping.stdout+'\n'+wrapping.stderr);
  const wrapped=JSON.parse(wrapping.stdout),candidate=read(wrapped.candidate.path);
  save({status:'awaiting-verification',stage:'publish',candidate:wrapped.candidate,outputs:candidate.outputs});
  timeLeft('publish');
  const beforePublish=(await getData()).rows.find(r=>r.id===plan.figureId);
  if(!beforePublish||beforePublish.reviewVersion!==figure.reviewVersion)throw Error('Figure changed during processing');
  assertStableRouteDecision(figure,beforePublish);assertConfirmedRoute(beforePublish,plan);timeLeft('publish');
  if(prepared.kind==='revision')await api('/review-triage/import-candidate',{id:prepared.id,candidate},true);
  else await api('/workbuddy/worker',{action:'submit-imported-pdf',id:prepared.id,batchHash:prepared.batchHash,attempt:task.attempt,input:candidate});
  const visible=await verifyVisible(candidate.outputs);
  save({status:'returned',stage:'visible',returnedAt:new Date().toISOString(),author:visible.author,editor:visible.editor,number:visible.number,outputs:candidate.outputs,error:null,failure:null,diagnostic:null});
  try{save({caseEvents:recordDeliveryCases(path.join(config.workbenchRoot,'case-events'),{figure:visible,plan,outputs:candidate.outputs,discovery:state.routeDiscovery,engineSignature:config.runtimeLock?.engineSignature})});}catch(error){save({caseIndexError:error.message});}
  return state;
 }catch(error){
  if(Date.now()>=deadline&&(error.killed||error.name==='TimeoutError'||error.name==='AbortError')){const timeout=Error('three_minute_deadline: '+state.stage);timeout.code='three_minute_deadline';error=timeout;}
  if(error.stdout||error.stderr)fs.writeFileSync(path.join(dir,'failure.log'),String(error.stdout??'')+'\n'+String(error.stderr??''));
  save({status:state.status==='awaiting-verification'||state.status==='returned'?'awaiting-verification':error.code==='known_fault'?'blocked':'failed',error:error.message,
        diagnostic:extractToolDiagnostic(error),failure:classifyProductionFailure(error,state.stage),failedAt:new Date().toISOString()});
  try{const event=recordFailureCase(path.join(config.workbenchRoot,'case-events'),{figureId:plan.figureId,plan,error,stage:state.stage,engineSignature:config.runtimeLock?.engineSignature});if(event)save({caseFailureEvent:event});}catch(caseError){save({caseIndexError:caseError.message});}
  if(['render','check'].includes(state.stage))try{
   const alternatives=searchFailureAlternatives({registryPath:config.caseIndexPath??fileURLToPath(new URL('../knowledge/figure-cases.json',import.meta.url)),eventDirectory:path.join(config.workbenchRoot,'case-events'),error,plan,features:state.routeDiscovery?.featureCandidates??{}});
   save({alternativeSearch:alternatives});
  }catch(caseError){save({alternativeSearch:{status:'search_failed',error:caseError.message}});}
  return state;
 }
 finally{if(fs.existsSync(lock)&&read(lock).token===owner.token)fs.unlinkSync(lock);}
}

// User-facing PDF-chart admission: discovery is mandatory even when a plan is not ready.
export async function runChartRequest(config,request){
 const start=Date.parse(request.requestedAt);if(!Number.isFinite(start)||start>Date.now()+5000)throw Error('invalid_requested_at');
 const elapsed=()=>Date.now()-start;
 const root=path.join(fs.realpathSync(config.workbenchRoot),'production-runs',safe(request.figureId),'route-discovery');fs.mkdirSync(root,{recursive:true});
 const key=createHash('sha256').update(JSON.stringify(request)).digest('hex'),recordPath=path.join(root,key+'.'+randomUUID()+'.json');
 const saveRecord=value=>{const record={requestedAt:request.requestedAt,elapsedMs:elapsed(),...value};atomicJson(recordPath,record);return {...record,recordPath};};
 let stage='preflight';
 try{
 if(elapsed()>=180000)return saveRecord({figureId:request.figureId,status:'deadline_exceeded',stage});
 const response=await fetch(config.origin+'/data',{signal:AbortSignal.timeout(Math.max(1,Math.min(30000,180000-elapsed())))});
 if(!response.ok)throw Error('Workbench unavailable');
 const data=await response.json(),figure=data.rows.find(r=>r.id===request.figureId);if(!figure)throw Error('figure_not_in_workbench');
 if(figure.outputs?.length&&!request.allowExistingCandidate){
  const discovery=await discoverPdfChart({caseIndexPath:config.caseIndexPath,figure,allowExistingCandidate:false});
  return saveRecord({...discovery,stage:'existing_candidate'});
 }
 stage='runtime';const runtime=await fixedProductionRuntime(config);
 if(elapsed()>=180000)return saveRecord({figureId:request.figureId,status:'deadline_exceeded',stage});
 const planDirectory=path.join(path.dirname(root),'chart-plans');
 const plan=request.plan??loadBoundChartPlan(planDirectory,{figure,source:request.source,engineSignature:runtime.signature,requirements:request.requirements});
 stage='route_discovery';const discovery=await discoverPdfChart({caseIndexPath:config.caseIndexPath,figure,article:data.articles?.find(a=>a.id===figure.articleId),source:request.source,python:config.python,plan,engineSignature:runtime.signature,rows:data.rows,errorCode:request.errorCode,eventDirectory:path.join(config.workbenchRoot,'case-events'),allowExistingCandidate:request.allowExistingCandidate===true,timeoutMs:Math.max(1,180000-elapsed())});
 if(elapsed()>=180000)return saveRecord({...discovery,status:'deadline_exceeded',stage:'route_discovery'});
 if(discovery.status!=='ready')return saveRecord({...discovery,stage:'route_discovery'});
 assertConfirmedRoute(figure,plan);
 const planRecord=plan.render?.some(item=>item.seriesBinding)?null:saveBoundChartPlan(planDirectory,{figure,source:request.source,discovery,plan});
 const result=await runProduction(config,{...plan,requestedAt:request.requestedAt});
 return saveRecord({...discovery,planRecord:result.chartPlanRecord??planRecord,status:result.status,stage:result.stage,delivery:result});
 }catch(error){return saveRecord({figureId:request.figureId,status:elapsed()>=180000?'deadline_exceeded':'failed',stage,error:error.message});}
}

export async function runProductionBatch(config,plans,{concurrency=3,onResult=()=>{}}={}){
 if(!Array.isArray(plans)||!plans.length||!Number.isSafeInteger(concurrency)||concurrency<1)throw Error('Invalid production batch');
 if(new Set(plans.map(p=>p.figureId)).size!==plans.length)throw Error('A batch cannot own the same figure twice');
 let cursor=0;const results=new Array(plans.length),startedAt=new Date().toISOString(),active={render:0,check:0},peak={render:0,check:0};
 const onToolEvent=(stage,change)=>{active[stage]+=change;peak[stage]=Math.max(peak[stage],active[stage]);};
 await Promise.all(Array.from({length:Math.min(concurrency,plans.length)},async()=>{
  while(cursor<plans.length){const index=cursor++;try{results[index]=await runProduction(config,plans[index],{onToolEvent});}catch(error){results[index]={figureId:plans[index].figureId,status:'blocked',stage:'claim',error:error.message,failure:classifyProductionFailure(error,'claim')};}onResult(results[index]);}
 }));
 const endedAt=new Date().toISOString(),returned=results.filter(r=>r.status==='returned'&&!r.reused&&r.receiptCreated&&!r.receipt.historical);
 const failures={};for(const r of results)if(r.status!=='returned'){const code=r.failure?.code??'unknown';failures[code]=(failures[code]??0)+1;}
 return {startedAt,endedAt,concurrency,peakToolProcesses:peak,returnedFigures:returned.length,returnedOutputs:returned.reduce((n,r)=>n+r.outputs.length,0),failureCounts:failures,results};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const [config,plan]=process.argv.slice(2);if(!config||!plan){console.error('Usage: node production-runner.mjs machine-config.json plan.json');process.exitCode=2;}
 else {const value=read(plan),machine=read(config);let result;if(value.requests){const {runProductionRequests}=await import('./production-intake.mjs');result=await runProductionRequests(machine,value,{executeBatch:runProductionBatch,executeChartRequest:runChartRequest,onResult:r=>console.error(JSON.stringify({figureId:r.figureId,status:r.status??r.reason,stage:r.stage}))});}else if(value.chartRequests){const items=value.chartRequests,limit=value.concurrency??3;if(!Array.isArray(items)||!items.length||!Number.isSafeInteger(limit)||limit<1||new Set(items.map(x=>x.figureId)).size!==items.length)throw Error('Invalid chart request batch');let cursor=0,results=new Array(items.length);await Promise.all(Array.from({length:Math.min(limit,items.length)},async()=>{while(cursor<items.length){const i=cursor++;try{results[i]=await runChartRequest(machine,items[i]);}catch(error){results[i]={figureId:items[i].figureId,status:'failed',stage:'route_discovery',error:error.message};}}}));result={results};}else if(value.chartRequest)result=await runChartRequest(machine,value.chartRequest);else result=value.plans?await runProductionBatch(machine,value.plans,{concurrency:value.concurrency??3}):await runProduction(machine,value);console.log(JSON.stringify(result));if(value.requests?result.admission.held.length||result.results.some(r=>r.status!=='returned'):value.chartRequests?result.results.some(r=>r.status!=='returned'&&r.status!=='existing_candidate'):value.chartRequest?!['returned','existing_candidate'].includes(result.status):value.plans?result.results.some(r=>r.status!=='returned'):result.status!=='returned')process.exitCode=1;}
}
