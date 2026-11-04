// Adapt an existing production plan to raster-batch; that entry owns execution.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {runRasterBatch} from './raster-batch.mjs';
import {assertConfirmedRoute,assertDispatchAllowed,bindAuthoritativeSources,productionTaskGroup} from './production-admission.mjs';
import {routeSourceRefs} from './production-route.mjs';
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const ref=p=>({path:path.resolve(p),sha256:createHash('sha256').update(fs.readFileSync(p)).digest('hex')});

export async function prepareRasterProductionItem(config,plan,figure,rows){
 if(figure.status==='终检通过'||figure.outputs?.length)throw Error('existing_candidate: 不重复制作已有候选');
 if(plan.baseVersion!==figure.reviewVersion)throw Error('Plan baseline is stale');
 assertConfirmedRoute(figure,plan);assertDispatchAllowed(config,plan);
 if(plan.outputRoutes.length!==1||plan.outputRoutes[0].number!==figure.number)throw Error('raster_multi_output_requires_explicit_plan');
 const {requestedAt,...stable}=plan,key=createHash('sha256').update(JSON.stringify(stable)).digest('hex');
 const dir=path.join(config.workbenchRoot,'raster-requests',figure.id,key);fs.mkdirSync(dir,{recursive:true});
 const put=(name,value)=>{const p=path.join(dir,name),content=JSON.stringify(value,null,2)+'\n';if(fs.existsSync(p)){if(fs.readFileSync(p,'utf8')!==content)throw Error('Frozen raster input changed: '+name);}else fs.writeFileSync(p,content,{flag:'wx'});return p;};
 const credentials=config.credentialsFile?read(config.credentialsFile):config;
 const routes=structuredClone(plan.outputRoutes);bindAuthoritativeSources(credentials,figure.articleId,routes);
 const register=source=>{
  if(ref(source.path).sha256!==source.sha256)throw Error('Source or evidence changed: '+source.path);
  const p=path.join(dir,source.sha256+path.extname(source.path));
  if(!fs.existsSync(p))fs.copyFileSync(source.path,p,fs.constants.COPYFILE_EXCL);
  if(ref(p).sha256!==source.sha256)throw Error('Registered source changed');return {...source,path:p};
 };
 for(const {productionRoute:r} of routes){
  r.sourceReview.inventory=register(r.sourceReview.inventory);
  r.sourceReview.selected=register(r.sourceReview.selected);
  r.sourceReview.candidates=r.sourceReview.candidates.map(register);
 }
 const route=routes[0].productionRoute;
 const task={kind:'production',figureId:figure.id,articleId:figure.articleId,figureNumber:figure.number,label:figure.author+' 图'+figure.number,
  batchHash:route.sourceReview.archive.sha256,group:productionTaskGroup(figure,plan),mainNumbers:rows.filter(r=>r.articleId===figure.articleId).map(r=>r.number),
  outputNumbers:[figure.number],outputRoutes:routes,sources:routeSourceRefs(route),sourceEvidence:route.sourceReview.basis,articleEvidence:plan.articleEvidence};
 if(plan.classificationEvidence)task.classificationEvidence=plan.classificationEvidence;
 const frozen=put('frozen.json',rows.filter(r=>r.status==='终检通过').flatMap(r=>(r.outputs??[]).map(o=>ref(o.file.path))));
 const targets=path.join(config.workbenchRoot,'review-targets');fs.mkdirSync(targets,{recursive:true});
 const evidence={producer:'public-production-runner',history:{...plan.history,revision_authorization:''},frozen_manifest:ref(frozen),author_roots:[targets],
  delivery_target:path.join(targets,figure.id+'-'+figure.number+'.jpg'),runtime:{python:config.python,font_profile:config.fontProfile},
  allowed_changes:plan.allowedChanges,immutable_content:plan.immutableContent,failure_policy:{max_attempts:2,repair:'local-only',time_budget_seconds:null,cost_budget:null}};
 return {figureId:figure.id,baseVersion:figure.reviewVersion,requestedAt:plan.requestedAt,taskFile:put('task-input.json',task),
  routeFile:put('route.json',route),evidenceFile:put('evidence.json',evidence),outputName:figure.author+'-图'+figure.number+'.jpg',
  autoPlan:plan.rasterAutoPlan??{crop:null},...(plan.classificationEvidence?{classificationEvidence:plan.classificationEvidence}:{}),manifestDirectory:dir};
}

export async function runRasterProductionPlan(config,plan,{onToolEvent=()=>{}}={}){
 if(plan.requestedAt){
  const start=Date.parse(plan.requestedAt);
  if(!Number.isFinite(start)||start>Date.now()+5000)throw Error('invalid_requested_at');
  if(Date.now()-start>=180000)throw Object.assign(Error('three_minute_deadline: preflight'),{code:'three_minute_deadline'});
 }
 const response=await fetch(config.origin+'/data',{signal:AbortSignal.timeout(30000)});if(!response.ok)throw Error('Workbench unavailable');
 const data=await response.json(),figure=data.rows.find(r=>r.id===plan.figureId);if(!figure)throw Error('figure_not_in_workbench');
 const item=await prepareRasterProductionItem(config,plan,figure,data.rows);
 const manifest=path.join(item.manifestDirectory,'batch.json');
 fs.writeFileSync(manifest,JSON.stringify({version:1,concurrency:1,items:[item]},null,2)+'\n');
 const credentials=config.credentialsFile?read(config.credentialsFile):config;
 const result=await runRasterBatch({...config,batchHash:plan.outputRoutes[0].productionRoute.sourceReview.archive.sha256,workerToken:credentials.workerToken},manifest,{onToolEvent});
 const row=result.results[0];return {...row,figureId:plan.figureId,author:figure.author,editor:figure.editor,number:figure.number,
  outputs:row.receipt?.outputs??[],status:row.status==='already_returned'?'returned':row.status,reused:row.status==='already_returned',stage:row.status==='returned'?'visible':row.stage};
}
