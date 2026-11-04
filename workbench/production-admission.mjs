// Shared dispatch boundary only; production-runner/raster-batch retain execution ownership.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {catalogFor} from './batch-scope.mjs';
import {assertCompleteOutputSet} from './multi-output.mjs';
import {processingRequirement} from './processing-evidence.mjs';
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const checked=r=>{if(!r?.path||hash(r.path)!==r.sha256)throw Error('Source or evidence changed: '+r?.path);return read(r.path);};

export function effectiveProductionType(figure,plan){
 if(!plan.classificationEvidence)return figure?.type??'';
 const evidence=checked(plan.classificationEvidence);
 if(evidence.version!==1||evidence.figureId!==figure.id||evidence.baseVersion!==figure.reviewVersion||
    evidence.review!=='agent-semantic-review'||!['diagram','chart'].includes(evidence.kind)||
    typeof evidence.basis!=='string'||!evidence.basis.trim()||
    !Array.isArray(evidence.outputs)||evidence.outputs.length!==plan.outputRoutes?.length)
  throw Error('classification_evidence_invalid: 分类纠错须绑定当前图稿、语义依据和完整输出');
 for(const route of plan.outputRoutes){
  const source=route.productionRoute?.sourceReview,output=evidence.outputs.find(item=>item.number===route.number);
  if(!output||!['archive','word','selected'].every(key=>output[key]===source?.[key]?.sha256))
   throw Error('classification_source_conflict: 分类证据与当前图源不符');
  for(const key of ['archive','word','selected']){
   if(hash(source[key].path)!==source[key].sha256)throw Error('classification_source_changed: '+key);
  }
 }
 // An agent may correct an old heuristic classification, never a current user decision.
 const decision=figure.decision,kind=decision?.attributes?.kind;
 if(kind?.state==='confirmed'){
  const confirmedChart=/统计|曲线|波形|频谱/.test(kind.value);
  const confirmedDiagram=['流程/算法图','系统/模块框图','网络/拓扑图','电路/接线图','结构/原理示意'].includes(kind.value);
  if(decision.stale||!(confirmedChart&&evidence.kind==='chart'||confirmedDiagram&&evidence.kind==='diagram'))throw Error('classification_confirmed_conflict');
 }
 return evidence.kind==='chart'?'统计图表':'流程与结构图';
}

export function prepareClassificationEvidence(figure,plan,{kind,basis},target){
 const evidence={version:1,figureId:figure.id,baseVersion:figure.reviewVersion,kind,basis,review:'agent-semantic-review',
  outputs:plan.outputRoutes.map(route=>({number:route.number,...Object.fromEntries(['archive','word','selected'].map(key=>[key,route.productionRoute.sourceReview[key].sha256]))}))};
 fs.writeFileSync(target,JSON.stringify(evidence,null,2)+'\n',{flag:'wx',encoding:'utf8'});
 const ref={path:path.resolve(target),sha256:hash(target)};
 try{effectiveProductionType(figure,{...plan,classificationEvidence:ref});}
 catch(error){fs.unlinkSync(target);throw error;}
 return ref;
}

export function productionTaskGroup(figure,plan){
 const type=effectiveProductionType(figure,plan);
 if(!plan.classificationEvidence)return figure.type;
 return /图表|曲线|柱状|散点|折线/.test(type)?'统计曲线图 / 保留图形换字':'流程与结构图 / 保留语义重排';
}

export function assertConfirmedRoute(figure,plan){
 // The live workbench classification is independent of the submitted plan.
 // An executor cannot turn a chart into a photo by choosing a raster contract.
 const type=effectiveProductionType(figure,plan);
 if(/图表|曲线|柱状|散点|折线/.test(type)&&plan.outputRoutes?.some(entry=>entry.productionRoute?.method==='raster-preserve'||entry.productionRoute?.processing?.operation==='preserve'))
  throw Error('chart_preserve_conflict: 工作台图表不得作为普通位图原样保留；先核对图表加工路线');
 if(/图表|曲线|柱状|散点|折线/.test(type)&&plan.outputRoutes?.some(entry=>entry.productionRoute?.processing?.operation!=='chart-redraw'))
  throw Error('chart_processing_conflict: 工作台图表必须绑定图表加工及数据保留检查');
 if(plan.qualityRoute==='source-preserving-chart'&&plan.outputRoutes?.some(entry=>entry.productionRoute?.processing?.operation!=='chart-redraw'))
  throw Error('chart_route_conflict: 保留原矢量图表须使用图表加工和布局规则');
 const decision=figure?.decision,method=decision?.attributes?.method;
 if(method?.state!=='confirmed'||method.value!=='完整重绘')return;
 if(decision.stale)throw Error('confirmed_route_stale: 制作决定已过期，需重新核对');
 if(!plan.outputRoutes?.length||plan.outputRoutes.some(entry=>entry.productionRoute?.processing?.operation!=='rebuild'))
  throw Error('confirmed_route_conflict: 已确认完整重绘，不能改用保留或换字路线');
 if(decision.sourceBinding&&plan.outputRoutes.some(entry=>{
  const s=entry.productionRoute?.sourceReview,b=decision.sourceBinding;
  return s?.archive?.sha256!==b.archive||s?.word?.sha256!==b.word||s?.selected?.sha256!==b.selected;
 }))throw Error('confirmed_route_source_conflict: 制作决定绑定的来源不一致');
}

export function assertStableRouteDecision(previous,current){
 const binding=figure=>{const d=figure?.decision,m=d?.attributes?.method;return m?.state==='confirmed'?{value:m.value,stale:!!d.stale,revision:d.revision??null,sourceBinding:d.sourceBinding??null}:null;};
 if(JSON.stringify(binding(previous))!==JSON.stringify(binding(current)))throw Error('route_decision_changed: 制作期间已确认路线发生变化，需重新准备');
}

export function bindAuthoritativeSources(config,articleId,routes){
 if(!config.catalog&&!config.catalogs)return;
 for(const entry of routes){
  const source=entry.productionRoute.sourceReview,catalog=catalogFor(config,source.archive.sha256),word=catalog.articles?.find(a=>a.id===articleId)?.word;
  for(const [key,authority] of [['archive',catalog.archive],['word',word]]){
   const supplied=source[key];
   if(!authority?.path||supplied.sha256!==authority.sha256||path.relative(fs.realpathSync(path.resolve(supplied.path)),fs.realpathSync(authority.path))!==''||hash(authority.path)!==authority.sha256)throw Error('authoritative_source_mismatch: '+key);
   source[key]={...supplied,path:authority.path};
  }
 }
}

export function assertDispatchAllowed(config,plan){
 if(['held','blocked','suspended'].includes(plan.state)||plan.doNotRunUntilBlockerResolved===true)throw Error('plan_on_hold: '+(plan.holdReason??plan.figureId));
 if(plan.qualityRoute!==undefined&&!['diagram','circuit','source-preserving-chart','raster'].includes(plan.qualityRoute))throw Error('unsupported_quality_route: '+plan.qualityRoute);
 const defaultFile=config.workbenchRoot&&path.join(config.workbenchRoot,'production-known-faults.json');
 const file=config.knownFaultsFile??(defaultFile&&fs.existsSync(defaultFile)?defaultFile:null);
 if(!file)return;
 const registry=read(file),matches=[];
 if(registry.version!==1||!Array.isArray(registry.faults))throw Error('invalid_fault_registry');
 const routes=(plan.outputRoutes??[]).map(r=>r.productionRoute),sources=routes.flatMap(r=>[r.sourceReview?.selected,...(r.sourceReview?.additionalSelected??[])]).filter(Boolean).map(s=>s.sha256);
 const specs=Array.isArray(plan.render)?plan.render:plan.rendered?.processingEvidence??[];
 const values={figureIds:[plan.figureId],sourceHashes:sources,specHashes:specs.map(s=>s.spec?.sha256),operations:routes.map(r=>r.processing?.operation),methods:routes.map(r=>r.method)};
 for(const fault of registry.faults){
  if(!fault.id||!fault.reason||!['open','resolved'].includes(fault.status)||!fault.scope||!Object.keys(fault.scope).length||!(fault.engineSignature===null||typeof fault.engineSignature==='string'&&fault.engineSignature))throw Error('invalid_fault_registry');
  for(const [key,items] of Object.entries(fault.scope)){
   if(key==='outputCountAtLeast'){if(!Number.isSafeInteger(items)||items<2)throw Error('invalid_fault_scope');}
   else if(!Object.hasOwn(values,key)||!Array.isArray(items)||!items.length||items.some(v=>typeof v!=='string'||!v))throw Error('invalid_fault_scope');
  }
  if(fault.status!=='open'||fault.engineSignature!==null&&fault.engineSignature!==config.runtimeLock?.engineSignature)continue;
  if(!Object.entries(fault.scope).every(([key,items])=>key==='outputCountAtLeast'?routes.length>=items:items.some(v=>values[key].includes(v))))continue;
  if(!fault.evidence?.path||hash(fault.evidence.path)!==fault.evidence.sha256)throw Error('fault_evidence_changed: '+fault.id);
  if(fault.id==='pdf-multi-output-evidence'&&plan.outputSetEvidence&&plan.articleId&&plan.figureNumber&&config.python){
   try{
    assertCompleteOutputSet({articleId:plan.articleId,figureNumber:plan.figureNumber,outputNumbers:plan.outputRoutes.map(r=>r.number),outputRoutes:plan.outputRoutes,productionRoute:plan.outputRoutes[0].productionRoute,outputSetEvidence:plan.outputSetEvidence},plan.outputRoutes,{python:config.python});
    continue;
   }catch{/* A missing, changed, or incomplete Word/source binding keeps the known-fault guard active. */}
  }
  matches.push(fault);
 }
 if(matches.length){const error=Error('known_fault: '+matches.map(f=>f.id+': '+f.reason).join('; '));error.code='known_fault';error.faultIds=matches.map(f=>f.id);error.failureAction=matches.every(f=>f.scope.specHashes)?'correct_plan':'wait_for_verified_fix';throw error;}
}

export function buildProductionQueue(config,plans,rows){
 const byId=new Map();for(const plan of plans){if(byId.has(plan.figureId))throw Error('duplicate_plan: '+plan.figureId);byId.set(plan.figureId,plan);}
 const queue={ready:[],reused:[],held:[]};
 for(const row of rows){
  const identity={figureId:row.id,editor:row.editor,author:row.author,articleId:row.articleId,number:row.number};
  if(row.status==='终检通过'||row.outputs?.length&&!row.feedback?.revision){queue.reused.push({...identity,reason:row.status==='终检通过'?'accepted':'candidate_awaiting_review'});continue;}
  const plan=byId.get(row.id);
  try{
   assertDispatchAllowed(config,plan??{figureId:row.id,outputRoutes:[]});
   if(!plan&&/图表|曲线|柱状/.test(row.type??''))throw Error('chart_route_discovery_required');
   if(!plan)throw Error('plan_not_prepared');
   if(plan.baseVersion!==row.reviewVersion)throw Error('Plan baseline is stale');
   assertConfirmedRoute(row,plan);
   if(!plan.outputRoutes?.length||!plan.qualityRoute||!plan.articleEvidence||!plan.allowedChanges?.length||!plan.immutableContent?.length)throw Error('plan_incomplete');
   const history=checked(plan.history?.evidence);if(!history.checked||history.conclusion!==plan.history.conclusion||history.reusable!==plan.history.reusable)throw Error('history_not_verified');
   const numbers=plan.outputRoutes.map(r=>r.number),items=plan.render??plan.rendered?.processingEvidence;
   const raster=plan.outputRoutes.every(r=>r.productionRoute.method==='raster-preserve');
   if(raster){
    if(plan.qualityRoute!=='raster'||numbers.length!==1||numbers[0]!==row.number)throw Error('raster_multi_output_requires_explicit_plan');
   }else if(!items?.length||new Set(numbers).size!==numbers.length||items.length!==numbers.length||!numbers.every(n=>items.some(x=>x.number===n)))throw Error('output_set_incomplete');
   for(const route of plan.outputRoutes){
    if(!['editable-pdf','raster-preserve'].includes(route.productionRoute.method))throw Error('unsupported_plan_route');
    processingRequirement(route.productionRoute);
    const source=route.productionRoute.sourceReview;
    for(const r of [source?.archive,source?.word,source?.selected])if(!r?.path||hash(r.path)!==r.sha256)throw Error('source_not_ready');
   }
   for(const item of items??[]){checked(item.spec);if(item.report)checked(item.report);}
   for(const output of plan.rendered?.outputs??[])if(hash(output.path)!==output.sha256)throw Error('candidate_changed');
   queue.ready.push(plan);
  }catch(error){queue.held.push({...identity,reason:error.message,faultIds:error.faultIds??[]});}
 }
 for(const plan of plans)if(!rows.some(r=>r.id===plan.figureId))queue.held.push({figureId:plan.figureId,reason:'figure_not_in_workbench'});
 return queue;
}
