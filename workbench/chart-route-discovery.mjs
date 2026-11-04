import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {recommendCases,loadCaseIndex,loadCaseEvents,shouldBlockIdenticalAttempt,sourceBindingFingerprint,matchesSourceVectorAsset} from './figure-case-index.mjs';
const exec=promisify(execFile),hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const routeToolSignature=()=>createHash('sha256').update([import.meta.url,'./inspect-pdf-chart.py','./chart_object_candidates.py','./chart-binding-adapter.mjs','./figure-case-index.mjs'].map(u=>hash(fileURLToPath(new URL(u,import.meta.url)))).join('\n')).digest('hex');

export function classifyChartRoutes(facts,{hasPlan=false}={}){
 const vector=facts.vectorPaths>0,images=facts.images>0;
 const routes=[
  {id:'source-vector-reletter',entryAvailable:true,sourceCompatible:vector?'unverified':'no_vector',missing:vector?['原文字对象与清除范围','曲线身份及保留证据','灰度后系列辨识']:['未发现原生矢量路径']},
  {id:'chart-layout',entryAvailable:true,sourceCompatible:vector?'unverified':'no_vector',missing:vector?['坐标轴、刻度、图例与系列绑定','数据路径和图内文字完整性']:['未发现原生矢量路径']},
  {id:'chart-panels',entryAvailable:true,sourceCompatible:vector||images?'unverified':'no_graphics',missing:vector||images?['面板范围及每面板坐标、曲线和图例归属']:['未发现面板图形对象']},
 ];
 return {status:hasPlan?'ready':facts.unsupportedVerified===true?'unsupported':'needs_bindings',facts,routes};
}

export async function discoverPdfChart({figure,article,source,python,plan,engineSignature,allowExistingCandidate=false,timeoutMs=30000,inspect,rows=[],errorCode,caseIndexPath,eventDirectory}){
 if(!figure?.id)throw Error('figure_identity_missing');
 if(figure.outputs?.length&&!allowExistingCandidate){
  const verified=figure.previewCurrent===true&&figure.outputs.every(o=>{try{return o.file?.path&&o.file?.meta?.sha256===hash(o.file.path);}catch{return false;}});
  return {status:'existing_candidate',candidateVerification:verified?'current_hash_verified':'verification_required',figureId:figure.id,outputs:figure.outputs};
 }
 if(!source?.path||!source.sha256||hash(source.path)!==source.sha256)throw Error('source_changed');
 if(!['.pdf','.svg','.jpg','.jpeg','.png'].includes(path.extname(source.path).toLowerCase()))throw Error('source_format_not_inspected');
 const script=fileURLToPath(new URL('./inspect-pdf-chart.py',import.meta.url));
 const facts=inspect?await inspect(source.path):JSON.parse((await exec(python,[script,source.path],{windowsHide:true,timeout:Math.min(30000,timeoutMs),maxBuffer:4*1024*1024,env:{...process.env,PYTHONUTF8:'1'}})).stdout);
 const routes=plan?.outputRoutes??[];
 const sourceMatched=routes.some(r=>r.productionRoute?.sourceReview?.selected?.sha256===source.sha256);
 const specs=plan?.render??plan?.rendered?.processingEvidence??[];
 const validRef=r=>Boolean(r?.path&&r.sha256&&fs.existsSync(r.path)&&hash(r.path)===r.sha256);
 const isChartSpec=r=>{try{const x=JSON.parse(fs.readFileSync(r.spec.path,'utf8').replace(/^\uFEFF/,''));return x.kind==='chart'||(x.kind==='scene'&&Boolean(x.chart_vector_layout));}catch{return false;}};
 const historyValid=()=>{try{const h=JSON.parse(fs.readFileSync(plan.history.evidence.path,'utf8'));return h.checked===true&&h.conclusion===plan.history.conclusion&&h.reusable===plan.history.reusable&&typeof h.observation==='string'&&Boolean(h.observation.trim());}catch{return false;}};
 const authoritative=Boolean(article&&article.id===figure.articleId&&article.word?.path&&fs.existsSync(article.word.path)&&routes.length&&routes.every(r=>r.productionRoute?.sourceReview?.word?.sha256===hash(article.word.path)&&r.productionRoute?.sourceReview?.archive?.sha256===article.archiveHash));
 const hasPlan=Boolean(authoritative&&plan&&plan.figureId===figure.id&&plan.baseVersion===figure.reviewVersion&&sourceMatched&&engineSignature&&plan.articleEvidence&&plan.allowedChanges?.length&&plan.immutableContent?.length&&validRef(plan.history?.evidence)&&historyValid()&&routes.length&&routes.every(r=>r.number&&r.productionRoute?.processing?.basis&&r.productionRoute?.requirements&&validRef(r.productionRoute?.sourceReview?.archive)&&validRef(r.productionRoute?.sourceReview?.word)&&validRef(r.productionRoute?.sourceReview?.selected))&&specs.length===routes.length&&specs.every(s=>validRef(s.spec)&&isChartSpec(s)&&routes.some(r=>r.number===s.number)));
 const registryPath=caseIndexPath??fileURLToPath(new URL('../knowledge/figure-cases.json',import.meta.url));
 const panelCandidates=facts.pages?.reduce((n,p)=>n+(p.panelCandidates?.length??0),0)??0,legendCandidates=facts.pages?.reduce((n,p)=>n+(p.legendCandidates?.length??0),0)??0;
 const page=facts.pages?.[0],ratio=page?.pageWidth/page?.pageHeight;
 const features={kind:'chart',format:facts.format??'pdf',...(facts.pixelTextRecognition==='not_performed'?{}:{nativeText:facts.textSpans>0}),vector:facts.vectorPaths>0,color:Boolean(facts.pages?.some(p=>p.coloredPaths?.length||p.colorSample)),...(panelCandidates?{panels:panelCandidates}:{}),...(legendCandidates?{legend:true}:{}),...(Number.isFinite(ratio)?{layout:ratio>1.25?'wide':ratio<.8?'tall':'square'}:{}),...(errorCode?{errorCode}:{})};
 const recommendations=recommendCases({registryPath,eventDirectory,rows,features});
 let blocked=[];
 if(hasPlan){
  const cases=[...loadCaseIndex(registryPath,rows).cases,...loadCaseEvents(eventDirectory,rows).cases];
  for(const spec of specs){
   const value=JSON.parse(fs.readFileSync(spec.spec.path,'utf8').replace(/^\uFEFF/,''));
   for(const asset of value.assets??[]){if(!matchesSourceVectorAsset(asset,spec.sourceRoot,source.sha256))continue;
    const attempt={sourceSha256:source.sha256,engineSignature,operation:'source-vector-reletter',bindingSha256:sourceBindingFingerprint(asset)};
    blocked.push(...cases.filter(c=>shouldBlockIdenticalAttempt(c,attempt)).map(c=>({id:c.id,errorCode:c.errorCode,evidence:c.evidence,reason:c.result})));
   }
  }
 }
 const missingBindings=hasPlan?[]:(facts.pages??[]).flatMap((p,index)=>{
  const items=[{page:index+1,kind:'text_roles',objects:(p.textObjects??[]).map(x=>x.id),reason:'原文字需要绑定轴、刻度或其他语义'}];
  if(p.coloredPaths?.length)items.push({page:index+1,kind:'series',objects:p.coloredPaths.map(x=>x.id),reason:'候选路径需要绑定系列、曲线及灰度辨识'});
  if(p.objectCandidates?.panels?.length)items.push({page:index+1,kind:'geometric_panels',objects:p.objectCandidates.panels.map(x=>({id:x.id,bbox:x.bbox,frameDrawingIndices:x.frameDrawingIndices})),reason:'源几何提出绘图区候选，标题、曲线、坐标及共享图例仍须结合当前图绑定'});
  if(p.objectCandidates?.unassignedColoredPathIndices?.length)items.push({page:index+1,kind:'unassigned_curve_paths',objects:p.objectCandidates.unassignedColoredPathIndices,reason:'这些源彩色路径未能可靠归属到候选绘图区'});
  items.push({page:index+1,kind:'panels',objects:(p.panelCandidates??[]).map(x=>x.text),reason:'面板候选须绑定真实区域、坐标与曲线'});
  items.push({page:index+1,kind:'legend',objects:(p.legendCandidates??[]).map(x=>x.text),reason:'图例候选须核对系列对应及作用范围；无候选不代表无图例'});
  return items;
 });
 const classification=classifyChartRoutes(facts,{hasPlan});if(blocked.length)classification.status='blocked_known_failure';
 return {...classification,missingBindings,figureId:figure.id,articleId:figure.articleId,number:figure.number,sourceSha256:source.sha256,engineSignature,
  featureCandidates:features,featureWarning:'面板与图例为候选，须按当前图核对；案例不能复制对象或数据绑定',caseRecommendations:recommendations,blockedIdenticalAttempts:blocked,
  planBinding:hasPlan?{engineSignature,routeToolSignature:routeToolSignature(),wordSha256:routes[0].productionRoute.sourceReview.word?.sha256,archiveSha256:routes[0].productionRoute.sourceReview.archive?.sha256,requirements:routes.map(r=>r.productionRoute.requirements),specs:specs.map(s=>s.spec.sha256)}:null};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const [configPath,requestPath]=process.argv.slice(2);
 if(!configPath||!requestPath){console.error('Usage: node chart-route-discovery.mjs machine.json request.json');process.exitCode=2;}
 else try{
  const config=JSON.parse(fs.readFileSync(configPath,'utf8').replace(/^\uFEFF/,''));
  const request=JSON.parse(fs.readFileSync(requestPath,'utf8').replace(/^\uFEFF/,''));
  const submitted=Date.parse(request.requestedAt);if(!Number.isFinite(submitted)||submitted>Date.now()+5000)throw Error('invalid_requested_at');
  if(Date.now()-submitted>=180000)throw Error('three_minute_deadline: route_discovery');
  const response=await fetch(config.origin+'/data',{signal:AbortSignal.timeout(Math.min(30000,180000-(Date.now()-submitted)))});
  if(!response.ok)throw Error('workbench_unavailable');
  const data=await response.json(),figure=data.rows.find(r=>r.id===request.figureId);
  if(!figure)throw Error('figure_not_in_workbench');
  const plan=request.planPath?JSON.parse(fs.readFileSync(request.planPath,'utf8')):undefined;
  const {fixedProductionRuntime}=await import('./fixed-production-runtime.mjs');
  const runtime=await fixedProductionRuntime(config);
  const result=await discoverPdfChart({figure,article:data.articles.find(a=>a.id===figure.articleId),source:request.source,python:config.python,plan,engineSignature:runtime.signature,rows:data.rows,errorCode:request.errorCode,eventDirectory:config.workbenchRoot?path.join(config.workbenchRoot,'case-events'):undefined,allowExistingCandidate:request.allowExistingCandidate===true,timeoutMs:Math.max(1,180000-(Date.now()-submitted))});
  const elapsed=Date.now()-submitted;
  const record={requestedAt:request.requestedAt,stage:'route_discovery',elapsedMs:elapsed,overThreeMinutes:elapsed>=180000,...result};
  if(request.resultPath)fs.writeFileSync(request.resultPath,JSON.stringify(record,null,2)+'\n');
  console.log(JSON.stringify(record));
 }catch(error){console.error(error.message);process.exitCode=1;}
}

// Reuse only when the caller explicitly supplies the same processing requirements.
export function loadBoundChartPlan(directory,{figure,source,engineSignature,requirements}){
 if(!Array.isArray(requirements)||!fs.existsSync(directory))return null;
 const records=fs.readdirSync(directory).filter(n=>n.endsWith('.json')).map(n=>JSON.parse(fs.readFileSync(path.join(directory,n),'utf8')));
 const matches=records.filter(r=>r.figureId===figure.id&&r.articleId===figure.articleId&&r.number===figure.number&&r.reviewVersion===figure.reviewVersion&&r.sourceSha256===source?.sha256&&r.binding?.engineSignature===engineSignature&&r.binding?.routeToolSignature===routeToolSignature()&&JSON.stringify(r.binding.requirements)===JSON.stringify(requirements));
 if(matches.length>1&&new Set(matches.map(r=>JSON.stringify(r.plan))).size>1)throw Error('ambiguous_confirmed_chart_plans');
 return matches[0]?.plan??null;
}

export function saveBoundChartPlan(directory,{figure,source,discovery,plan}){
 if(discovery.status!=='ready'||!discovery.planBinding)throw Error('unverified_chart_plan');
 fs.mkdirSync(directory,{recursive:true});
 const {requestedAt:ignoredRequestedAt,...durablePlan}=plan;
 const record={version:1,figureId:figure.id,articleId:figure.articleId,number:figure.number,reviewVersion:figure.reviewVersion,sourceSha256:source.sha256,binding:discovery.planBinding,plan:durablePlan};
 const key=createHash('sha256').update(JSON.stringify(record)).digest('hex'),file=path.join(directory,key+'.json');
 try{fs.writeFileSync(file,JSON.stringify(record,null,2)+'\n',{flag:'wx'});}catch(error){if(error.code!=='EEXIST'||JSON.stringify(JSON.parse(fs.readFileSync(file,'utf8')))!==JSON.stringify(record))throw error;}
 return file;
}
