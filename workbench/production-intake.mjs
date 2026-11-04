// Admission for the existing runner; never renders, publishes, or approves.
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {buildProductionQueue} from './production-admission.mjs';

const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const exec=promisify(execFile);
const wordCandidates=fileURLToPath(new URL('./word-subfigure-candidates.py',import.meta.url));
const sourceInspector=fileURLToPath(new URL('./inspect-pdf-chart.py',import.meta.url));
const nativeBindings=fileURLToPath(new URL('./native-text-bindings.py',import.meta.url));
const engineRoot=fileURLToPath(new URL('../portable-production/direct-pdf/',import.meta.url));
async function mapLimited(items,limit,fn){let cursor=0;await Promise.all(Array.from({length:Math.min(items.length,Math.max(1,limit))},async()=>{while(cursor<items.length)await fn(items[cursor++]);}));}
export function subfigureCandidateConflicts(candidate,plan){
 if(candidate.status!=='candidate')return false;
 const numbers=candidate.candidates[0].outputs.map(o=>o.number),planned=plan.outputRoutes.map(o=>o.number);
 return JSON.stringify(numbers)!==JSON.stringify(planned);
}
const candidateVerified=row=>row.previewCurrent===true&&Array.isArray(row.outputs)&&row.outputs.length>0&&row.outputs.every(output=>{
 try{return typeof output.file?.path==='string'&&/^[a-f0-9]{64}$/.test(output.file?.meta?.sha256??'')&&createHash('sha256').update(fs.readFileSync(output.file.path)).digest('hex')===output.file.meta.sha256;}catch{return false;}
});
const rowsSelected=(rows,id)=>rows.find(row=>row.id===id)?.productionRoute?.sourceReview?.selected;
const routesFor=row=>/图表|曲线|柱状/.test(row.type??'')
 ?['source-vector-reletter','chart-layout','chart-panels']
 :/流程|结构/.test(row.type??'')?['rebuild']:['raster-preserve','vector-reletter','rebuild'];

export function prepareProductionRequests(config,batch,rows){
 if(!Array.isArray(batch.requests)||!batch.requests.length)throw Error('requests_required');
 if(batch.requests.some(r=>!r.figureId)||new Set(batch.requests.map(r=>r.figureId)).size!==batch.requests.length)throw Error('duplicate_request_or_missing_identity');
 const plans=[...(batch.plans??[])];
 for(const file of batch.planFiles??[]){const value=read(file);plans.push(...(value.plans??[value]));}
 const queue={ready:[],reused:[],held:[]};
 for(const request of batch.requests){
  const requestedAt=request.requestedAt??batch.requestedAt,started=Date.parse(requestedAt);
  if(!Number.isFinite(started)||started>Date.now()+5000)throw Error('invalid_requested_at');
  const row=rows.find(r=>r.id===request.figureId);
  const identity={figureId:request.figureId,requestedAt,author:row?.author,editor:row?.editor,articleId:row?.articleId,number:row?.number};
  const hold=(reason,status='needs_bindings')=>queue.held.push({...identity,status,stage:'intake',reason,elapsedMs:Date.now()-started,routes:row?routesFor(row):[],routeCompatibility:'unverified'});
  if(!row){hold('figure_not_in_workbench');continue;}
  if(row.outputs?.length||row.status==='终检通过'){
   if(candidateVerified(row))queue.reused.push({...identity,reason:'existing_candidate',outputs:row.outputs});
   else hold('candidate_verification_required','blocked');
   continue;
  }
  if(Date.now()-started>=180000){hold('three_minute_deadline: intake','blocked');continue;}
  const candidates=plans.filter(p=>p.figureId===row.id&&p.baseVersion===row.reviewVersion);
  const unique=[...new Map(candidates.map(p=>{const {requestedAt,...content}=p;return [JSON.stringify(content),content];})).values()];
  if(!unique.length){hold(plans.some(p=>p.figureId===row.id)?'saved_plan_stale':'confirmed_plan_missing');continue;}
  if(unique.length!==1){hold('ambiguous_saved_plans');continue;}
  const plan={...unique[0],requestedAt},checked=buildProductionQueue(config,[plan],[row]);
  if(checked.ready.length)queue.ready.push(plan);
  else {const reason=checked.held[0]?.reason??'plan_not_ready';hold(reason,/plan_on_hold|known_fault/.test(reason)?'blocked':'needs_bindings');}
 }
 return queue;
}

export async function runProductionRequests(config,batch,{executeBatch,executeChartRequest,onResult=()=>{}}={}){
 const start=Date.now();
 const response=await fetch(config.origin+'/data',{signal:AbortSignal.timeout(30000)});
 if(!response.ok)throw Error('Workbench unavailable');
 const data=await response.json(),queue=prepareProductionRequests(config,batch,data.rows);
 // Word caption candidates provide output identities, not image-region or semantic bindings.
 const preflight=[...queue.held,...queue.ready.map(plan=>({figureId:plan.figureId,plan}))];
 await mapLimited(preflight,batch.concurrency??5,async item=>{
  const row=data.rows.find(r=>r.id===item.figureId),article=data.articles?.find(a=>a.id===row?.articleId);
  const word=article?.word?.path;
  if(!config.python||!word||!row?.number)return;
  const started=Date.parse(item.requestedAt??item.plan?.requestedAt??batch.requestedAt);
  const remaining=180000-(Date.now()-started);
  if(remaining<=0)return;
  try{
   const {stdout}=await exec(config.python,[wordCandidates,word,String(row.number)],{windowsHide:true,timeout:Math.min(10000,remaining),maxBuffer:1024*1024,env:{...process.env,PYTHONUTF8:'1'}});
   const candidate=JSON.parse(stdout);
   if(item.plan){
    if(subfigureCandidateConflicts(candidate,item.plan)){
     queue.ready.splice(queue.ready.indexOf(item.plan),1);
     queue.held.push({figureId:row.id,articleId:row.articleId,author:row.author,editor:row.editor,number:row.number,requestedAt:item.plan.requestedAt,status:'needs_bindings',stage:'intake',reason:'word_subfigure_candidate_conflict',subfigureCandidates:candidate,elapsedMs:Date.now()-started});
    }
   }else if(!item.plan)item.subfigureCandidates=candidate;
  }catch(error){if(!item.plan)item.subfigureDiscoveryError=error.message;}
 });
 const byId=new Map(batch.requests.map(r=>[r.figureId,r]));
 const sourceInspectionPromise=mapLimited(queue.held,batch.concurrency??5,async item=>{
  const row=data.rows.find(r=>r.id===item.figureId);let source=byId.get(item.figureId)?.source??rowsSelected(data.rows,item.figureId);
  const {isOfficeSource,prepareOfficeSource}=await import('./office-source-preparation.mjs');
  if(item.status==='needs_bindings'&&source?.path&&source.sha256&&isOfficeSource(source.path)&&config.workbenchRoot){
   const available=180000-(Date.now()-Date.parse(item.requestedAt));
   if(available<=0)return;
   const request=byId.get(item.figureId);
   try{item.sourcePreparation=await prepareOfficeSource({source,workbenchRoot:config.workbenchRoot,timeoutMs:available,
       python:config.python,pptxPlan:request?.pptxPlan,pptxDecision:request?.pptxDecision,grayscale:request?.grayscale===true});source=item.sourcePreparation.outputs[0];}
   catch(error){item.sourcePreparationError={stage:'office_conversion',message:error.message,classification:'existing_route_failed_not_missing_source'};return;}
   if(/图表|曲线|柱状/.test(row?.type??'')&&typeof executeChartRequest==='function'&&!/\.docx?$/i.test(item.sourcePreparation.source.path)){
    try{Object.assign(item,await executeChartRequest(config,{...request,source,requestedAt:item.requestedAt}));}
    catch(error){item.sourceInspectionError=error.message;}
    return;
   }
  }
  if(!config.python||item.status!=='needs_bindings'||/图表|曲线|柱状/.test(row?.type??'')||!source?.path||!source.sha256||!/[.](pdf|svg)$/i.test(source.path))return;
  const remaining=180000-(Date.now()-Date.parse(item.requestedAt));if(remaining<=0)return;
  try{
   if(createHash('sha256').update(fs.readFileSync(source.path)).digest('hex')!==source.sha256)throw Error('source_changed');
   const {stdout}=await exec(config.python,[sourceInspector,source.path],{windowsHide:true,timeout:Math.min(10000,remaining),maxBuffer:4*1024*1024,env:{...process.env,PYTHONUTF8:'1'}});
   item.sourceObjectCandidates={sourceSha256:source.sha256,facts:JSON.parse(stdout),warning:'来源对象仅为候选，须核对图号、区域、文字和连接关系'};
   if(item.sourcePreparation&&/\.docx?$/i.test(item.sourcePreparation.source.path)){
    item.sourceObjectCandidates.requiresFigureRegion=true;
    item.sourceObjectCandidates.warning='整篇Word已转PDF；先绑定本图页与裁区，不对全文自动建立本图文字方案';
    return;
   }
   if(/[.]pdf$/i.test(source.path)){
    const available=180000-(Date.now()-Date.parse(item.requestedAt));
    if(available>0){
     try{
      const generated=await exec(config.python,[nativeBindings,source.path,engineRoot],{windowsHide:true,timeout:Math.min(10000,available),maxBuffer:4*1024*1024,env:{...process.env,PYTHONUTF8:'1'}});
      const bindings=JSON.parse(generated.stdout);
      if(bindings.sourceSha256!==source.sha256)throw Error('source_changed_during_binding');
      item.nativeTextBindings=bindings;
     }catch(error){item.nativeTextBindingError=error.message;}
    }
   }
  }catch(error){item.sourceInspectionError=error.message;}
 });
 const discoverable=queue.held.filter(item=>{
  const request=byId.get(item.figureId),source=request?.source??rowsSelected(data.rows,item.figureId);
  const row=data.rows.find(r=>r.id===item.figureId),format=source?.path?.toLowerCase()??'';
  return typeof executeChartRequest==='function'&&item.status==='needs_bindings'&&['confirmed_plan_missing','saved_plan_stale'].includes(item.reason)&&/图表|曲线|柱状/.test(row?.type??'')&&['.pdf','.svg','.jpg','.jpeg','.png'].some(ext=>format.endsWith(ext));
 });
 const pending=new Set(discoverable.map(x=>x.figureId));
 for(const item of queue.reused)onResult(item);
 if(queue.ready.length&&typeof executeBatch!=='function')throw Error('production_executor_required');
 const executePromise=queue.ready.length?executeBatch(config,queue.ready,{concurrency:batch.concurrency??5,onResult})
  :Promise.resolve({returnedFigures:0,returnedOutputs:0,peakToolProcesses:{render:0,check:0},results:[]});
 let cursor=0;const limit=Math.max(1,batch.concurrency??5);
 const discoveryPromise=Promise.all(Array.from({length:Math.min(limit,discoverable.length)},async()=>{
  while(cursor<discoverable.length){const item=discoverable[cursor++],request=byId.get(item.figureId),source=request.source??rowsSelected(data.rows,item.figureId);
   let value;try{value=await executeChartRequest(config,{...request,source,requestedAt:item.requestedAt});}
   catch(error){value={status:'failed',stage:'route_discovery',error:error.message};}
   Object.assign(item,value);onResult(item);
  }
 }));
 const [result]=await Promise.all([executePromise,discoveryPromise,sourceInspectionPromise]);
 for(const item of queue.held.filter(x=>!pending.has(x.figureId)))onResult(item);
 return {...result,requestedFigures:batch.requests.length,admission:{ready:queue.ready.map(p=>p.figureId),reused:queue.reused,held:queue.held},intakeAndExecutionMs:Date.now()-start};
}
