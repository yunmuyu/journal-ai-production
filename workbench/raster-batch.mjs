import fs from 'node:fs';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {performance} from 'node:perf_hooks';
import {createHash} from 'node:crypto';
import {randomUUID} from 'node:crypto';
import {processingRequirement} from './processing-evidence.mjs';
import {classifyProductionFailure,verifyProductionDelivery} from './production-observability.mjs';
import {assertDispatchAllowed,assertConfirmedRoute,assertStableRouteDecision} from './production-admission.mjs';
import {prepareRasterPlan} from './raster-preparation.mjs';
import {recordDeliveryCases,recordFailureCase,searchFailureAlternatives} from './figure-case-index.mjs';

const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const run=promisify(execFile),rasterJob=fileURLToPath(new URL('./raster-job.mjs',import.meta.url));
function writeOnce(file,value){
 const bytes=JSON.stringify(value,null,2)+'\n';
 if(fs.existsSync(file)){if(fs.readFileSync(file,'utf8')!==bytes)throw Error('既有批量输入与本次不一致：'+path.basename(file));}
 else fs.writeFileSync(file,bytes,{flag:'wx'});
}

export function acquireDirectRunLock(file,{pid=process.pid,isAlive=processIsAlive}={}){
 const owner={pid,token:randomUUID(),startedAt:new Date().toISOString()},bytes=JSON.stringify(owner);
 try{fs.writeFileSync(file,bytes,{flag:'wx'});return owner;}
 catch(error){if(error.code!=='EEXIST')throw error;}
 let prior,stat;
 const recoveryFile=file+'.recovery.lock',recovery={pid,token:randomUUID(),startedAt:new Date().toISOString()};
 try{fs.writeFileSync(recoveryFile,JSON.stringify(recovery),{flag:'wx'});}catch(error){
  if(error.code!=='EEXIST')throw Error('无法取得直接制作锁恢复互斥：'+error.message);
  let abandoned=false;try{const owner=JSON.parse(fs.readFileSync(recoveryFile,'utf8'));abandoned=Number.isSafeInteger(owner.pid)&&typeof owner.token==='string'&&isAlive(owner.pid)===false;}catch{}
  throw Error(abandoned?'直接制作恢复互斥的所属进程已退出；请确认没有执行者后按运维恢复说明处理该 recovery.lock':'另一个执行者正在恢复直接制作锁或锁身份无法确认；拒绝夺锁');
 }
 try{
 try{prior=fs.readFileSync(file);stat=fs.statSync(file);}catch(error){throw Error('直接制作锁正在变化，不能安全恢复：'+error.message);}
 let incumbent;
 try{incumbent=JSON.parse(prior.toString('utf8'));}catch{throw Error('直接制作锁身份无法确认，拒绝回收');}
 if(!Number.isSafeInteger(incumbent.pid)||incumbent.pid<=0||typeof incumbent.token!=='string'||!incumbent.token)throw Error('直接制作锁身份不完整，拒绝回收');
 if(isAlive(incumbent.pid)!==false)throw Error('直接制作锁所属进程存活或状态无法确认，拒绝夺锁');
 let current,currentStat;
 try{current=fs.readFileSync(file);currentStat=fs.statSync(file);}catch(error){throw Error('直接制作锁恢复竞争失败：'+error.message);}
 if(!current.equals(prior)||currentStat.ino!==stat.ino||currentStat.mtimeMs!==stat.mtimeMs)throw Error('直接制作锁已变化，拒绝回收');
 try{fs.unlinkSync(file);}catch(error){throw Error('直接制作锁回收失败：'+error.message);}
 try{fs.writeFileSync(file,bytes,{flag:'wx'});return owner;}
 catch(error){throw Error('直接制作锁已被其他执行者取得：'+error.message);}
 }finally{
  try{if(JSON.parse(fs.readFileSync(recoveryFile,'utf8')).token===recovery.token)fs.unlinkSync(recoveryFile);}catch{}
 }
}

function processIsAlive(pid){
 try{process.kill(pid,0);return true;}
 catch(error){if(error.code==='ESRCH')return false;return undefined;}
}

export async function runRasterBatch(configPath,manifestPath,{onToolEvent=()=>{},onResult=()=>{}}={}){
 const config=typeof configPath==='string'?read(configPath):configPath,manifest=read(manifestPath),base=path.dirname(path.resolve(manifestPath));
 if(manifest.version!==1||!Array.isArray(manifest.items)||!manifest.items.length||manifest.items.some(item=>!item.id&&!item.figureId)||new Set(manifest.items.map(item=>item.id??item.figureId)).size!==manifest.items.length)throw Error('批量清单须包含不重复的任务或图件ID');
 const concurrency=manifest.concurrency??2;
 if(!Number.isSafeInteger(concurrency)||concurrency<1)throw Error('并行数量须为正安全整数');
 const local=file=>path.resolve(base,file);
 async function api(body){
  const response=await fetch(new URL('/workbuddy/worker',config.origin),{method:'POST',headers:{Authorization:'Bearer '+config.workerToken,'Content-Type':'application/json'},body:JSON.stringify({...body,...(config.batchHash?{batchHash:config.batchHash}:{})}),signal:AbortSignal.timeout(180000)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'工作台回传失败');return value;
 }
 const results=[],startedAt=new Date().toISOString(),measurementCache=new Map();let cursor=0;
 async function processItem(item){
  const started=performance.now();let task,lock,ownsLock=false,stage='preflight',publicationStarted=false,admissionFigure,admissionPlan;
  async function figureForAdmission(id){
   const response=await fetch(new URL('/data',config.origin),{signal:AbortSignal.timeout(30000)});
   if(!response.ok)throw Error('Workbench unavailable');
   const figure=(await response.json()).rows?.find(row=>row.id===id);
   if(!figure)throw Error('figure_not_in_workbench: '+id);
   return figure;
  }
  async function verify(outputs,historical=false){
   stage='verify';
   const result=await verifyProductionDelivery({origin:config.origin,receiptRoot:config.receiptRoot??path.join(config.workbenchRoot??task.attemptDir,'production-receipts')},
    {figureId:task.figureId,articleId:task.articleId,figureNumber:task.figureNumber,outputs,batchHash:task.batchHash,kind:task.kind==='revision'?'revision':'ordinary',historical});
   let caseEvents=[],caseIndexError;
   try{
    const routes=admissionPlan.outputRoutes.length===1&&!admissionPlan.outputRoutes[0].number
     ?outputs.map(o=>({number:o.number,productionRoute:admissionPlan.outputRoutes[0].productionRoute}))
     :admissionPlan.outputRoutes;
    caseEvents=recordDeliveryCases(path.join(config.workbenchRoot??task.attemptDir,'case-events'),{figure:result.figure,plan:{qualityRoute:'raster',outputRoutes:routes},outputs,engineSignature:config.runtimeLock?.engineSignature});
   }catch(error){caseIndexError=error.message;}
   return {id:task.id,label:task.label,status:result.newReceipt&&!result.receipt.historical?'returned':'already_returned',elapsedMs:item.requestedAt?Date.now()-Date.parse(item.requestedAt):performance.now()-started,
    requestStartedAt:item.requestedAt??null,timingScope:item.requestedAt?'from_requested_at':'execution_only',returnedAt:result.receipt.returnedAt,
    figureId:result.figure.id,receipt:result.receipt,receiptCreated:result.newReceipt,caseEvents,...(caseIndexError?{caseIndexError}:{})};
  }
  async function submit(result){
   const latest=await figureForAdmission(task.figureId);assertStableRouteDecision(admissionFigure,latest);assertConfirmedRoute(latest,admissionPlan);
   writeOnce(path.join(task.attemptDir,'delivery-pending.json'),{outputs:result.outputs});stage='publish';publicationStarted=true;
   await api({action:'submit-direct',id:task.id,attempt:task.attempt,result});return verify(result.outputs);
  }
  try{
   const multi=Array.isArray(item.outputs);
   const specs=multi?structuredClone(item.outputs):[{number:null,routeFile:item.routeFile,plan:item.plan,autoPlan:item.autoPlan,outputName:item.outputName,evidenceFile:item.evidenceFile,expectedOutputSha256:item.expectedOutputSha256,observationsFile:item.observationsFile}];
   if(!specs.length||new Set(specs.map(spec=>spec.number)).size!==specs.length)throw Error('多输出批次缺少完整且唯一的逐输出清单');
   for(const spec of specs)if(typeof spec.outputName!=='string'||path.basename(spec.outputName)!==spec.outputName||!spec.outputName.toLowerCase().endsWith('.jpg'))throw Error('每个输出都必须是独立JPG文件名');
   const outputRoutes=multi?specs.map(spec=>({number:spec.number,productionRoute:read(local(spec.routeFile))})):undefined;
   const route=outputRoutes?.[0]?.productionRoute??read(local(item.routeFile));
   for(const entry of outputRoutes??[{productionRoute:route}])processingRequirement(entry.productionRoute);
   const sourceTask=item.taskFile?read(local(item.taskFile)):null;
   let figureId=sourceTask?.figureId??item.figureId;
   if(!figureId){
    const response=await fetch(new URL('/workbuddy/status',config.origin),{signal:AbortSignal.timeout(30000)});
    if(!response.ok)throw Error('Cannot resolve task identity for admission');
    const job=(await response.json()).jobs.find(job=>job.id===item.id);
    figureId=job?.figureId;
    if(!figureId&&job?.articleId&&job?.figureNumber){
     const data=await fetch(new URL('/data',config.origin),{signal:AbortSignal.timeout(30000)});
     if(!data.ok)throw Error('Workbench unavailable');
     const matches=(await data.json()).rows?.filter(row=>row.articleId===job.articleId&&row.number===job.figureNumber)??[];
     if(matches.length===1)figureId=matches[0].id;
    }
    if(!figureId)throw Error('Task figure identity missing for admission');
   }
   admissionPlan={figureId,baseVersion:item.baseVersion,outputRoutes:outputRoutes??[{number:sourceTask?.figureNumber,productionRoute:route}],...(item.classificationEvidence?{classificationEvidence:item.classificationEvidence}:{})};
   assertDispatchAllowed(config,admissionPlan);
   admissionFigure=await figureForAdmission(figureId);assertConfirmedRoute(admissionFigure,admissionPlan);
   for(let index=0;index<specs.length;index++){
    const spec=specs[index];if(spec.autoPlan===undefined)continue;
    if(spec.plan)throw Error('explicit_plan_conflicts_with_auto_plan');
    const evidence=read(local(spec.evidenceFile));
    const preparedPlan=await prepareRasterPlan({route:outputRoutes?.[index]?.productionRoute??route,options:spec.autoPlan,python:evidence.runtime?.python,cache:measurementCache});
    spec.plan=preparedPlan.plan;spec.preparation=preparedPlan;
   }
   if(!multi&&specs[0].autoPlan!==undefined)item={...item,plan:specs[0].plan};
   if(multi&&sourceTask)sourceTask.outputRoutes=outputRoutes;
   stage='prepare';const prepared=item.taskFile
    ? await api({action:'prepare-import',task:sourceTask,productionRoute:route})
    : await api({action:'prepare-direct',id:item.id,productionRoute:route,outputRoutes});
   task=prepared.job;
   if(prepared.alreadyReturned){publicationStarted=true;return await verify(task.result.outputs,!fs.existsSync(path.join(task.attemptDir,'delivery-pending.json')));}
   stage='claim';
   lock=path.join(task.attemptDir,'.direct-run.lock');
   acquireDirectRunLock(lock);
   ownsLock=true;
   async function invoke(args,name,logDir=task.attemptDir){
    stage=args[0]==='self-check'?'check':'render';
    let execution;
    const remaining=item.requestedAt?180000-(Date.now()-Date.parse(item.requestedAt)):180000;
    if(!Number.isFinite(remaining)||remaining<=0)throw Object.assign(Error('three_minute_deadline: '+stage),{code:'three_minute_deadline'});
    onToolEvent(stage,1);
    try{execution=await run(process.execPath,[rasterJob,...args],{windowsHide:true,env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'},timeout:remaining,maxBuffer:4*1024*1024});}
    catch(error){fs.writeFileSync(path.join(logDir,name+'.error.log'),String(error.stderr||error.stdout||error.message));throw error;}
    finally{onToolEvent(stage,-1);}
    fs.writeFileSync(path.join(logDir,name+'.log'),execution.stdout);return JSON.parse(execution.stdout);
   }
   if(multi){
    const aggregated={evidence:'每个子图均已使用冻结来源和公共raster/task_quality重放；未做人内部视觉语义复核，待用户终审。',summary:'多输出灰度JPG候选已逐项回放及自动核验，待用户终审。',outputs:[],quality:{outputChecks:[]}};
    for(let index=0;index<specs.length;index++){
     const spec=specs[index],outputRoute=outputRoutes[index].productionRoute,slug=spec.number.replace(/[^a-zA-Z0-9_-]/g,'_'),outputDir=path.join(task.attemptDir,'outputs',slug);
     fs.mkdirSync(outputDir,{recursive:true});
     if(spec.preparation)writeOnce(path.join(outputDir,'source-preparation.json'),spec.preparation);
     const childTask={...task,id:`${task.id}-${slug}`,parentTaskId:task.id,attemptDir:outputDir,outputNumbers:[spec.number],outputRoutes:[{number:spec.number,productionRoute:outputRoute}],productionRoute:outputRoute};
     const taskPath=path.join(outputDir,'task.json'),planPath=path.join(outputDir,'raster-plan.json'),evidencePath=path.join(outputDir,'evidence.json');
     writeOnce(taskPath,childTask);
     const output=path.join(outputDir,'candidate',spec.outputName),inputs=spec.plan.inputs.map(input=>({...input,path:fs.realpathSync(input.path)}));
     writeOnce(planPath,{...spec.plan,inputs,output});writeOnce(evidencePath,read(local(spec.evidenceFile)));
     const rendered=await invoke([taskPath,planPath,evidencePath],'direct-raster',outputDir),renderedResult=read(rendered.result.path),candidate=renderedResult.outputs[0];
     if(spec.expectedOutputSha256&&(!/^[a-f0-9]{64}$/.test(spec.expectedOutputSha256)||candidate?.sha256!==spec.expectedOutputSha256))throw Error(`公共工具重放结果与图${spec.number}既有候选哈希不一致，拒绝登记`);
     const observationPath=path.join(outputDir,'observations.json');
     const observations=spec.observationsFile?read(local(spec.observationsFile)):{observations:{source_content:'仅完成来源、图号和加工映射核验；未做人内部视觉复核，待用户终审。',readability:'未判定最终物理尺寸可读性，待用户终审。',grayscale_semantics:'灰度像素门禁由task_quality核验；灰度语义未做人内部复核，待用户终审。'}};
     writeOnce(observationPath,observations);
     const checked=await invoke(['self-check',taskPath,observationPath],'direct-pending',outputDir),outputResult=read(checked.result.path);
     if(outputResult.outputs?.length!==1||outputResult.outputs[0].number!==spec.number)throw Error(`图${spec.number}逐项核验没有产出唯一匹配JPG`);
     aggregated.outputs.push(outputResult.outputs[0]);
     aggregated.quality.outputChecks.push({number:spec.number,taskId:childTask.id,task:{path:taskPath,sha256:createHash('sha256').update(fs.readFileSync(taskPath)).digest('hex')},result:{path:checked.result.path,sha256:createHash('sha256').update(fs.readFileSync(checked.result.path)).digest('hex')}});
    }
    const aggregatePath=path.join(task.attemptDir,'multi-output-result.json');writeOnce(aggregatePath,aggregated);
    return await submit(read(aggregatePath));
   }else{
    if(specs[0].preparation)writeOnce(path.join(task.attemptDir,'source-preparation.json'),specs[0].preparation);
    const planPath=path.join(task.attemptDir,'raster-plan.json'),evidencePath=path.join(task.attemptDir,'evidence.json');
    const output=path.join(fs.realpathSync(task.attemptDir),'candidate',item.outputName),inputs=item.plan.inputs.map(input=>({...input,path:fs.realpathSync(input.path)}));
    writeOnce(planPath,{...item.plan,inputs,output});writeOnce(evidencePath,read(local(item.evidenceFile)));
    const taskPath=path.join(task.attemptDir,'task.json'),rendered=await invoke([taskPath,planPath,evidencePath],'direct-raster');
    if(item.expectedOutputSha256){
     const candidate=read(rendered.result.path),expected=item.expectedOutputSha256;
     if(!/^[a-f0-9]{64}$/.test(expected)||candidate.outputs.length!==1||candidate.outputs[0].sha256!==expected)throw Error('公共工具重放结果与既有候选哈希不一致，拒绝登记');
    }
    const observationPath=path.join(task.attemptDir,'observations.json');
    const observations=item.observationsFile?read(local(item.observationsFile)):{observations:{source_content:'来源依据保存在路线及历史证据中；人工内部复核暂停，待用户终审。',readability:'人工内部复核暂停，未判定最终物理尺寸可读性，待用户终审。',grayscale_semantics:'所有图件必须灰度；分类及时间辨识尚待用户核对，不能视为人工通过。'}};
    writeOnce(observationPath,observations);
    const checked=await invoke(['self-check',taskPath,observationPath],'direct-pending');
    return await submit(read(checked.result.path));
   }
  }catch(error){
   const failure=classifyProductionFailure(error,stage);
   let caseFailureEvent,caseIndexError,alternativeSearch;
   try{if(admissionPlan)caseFailureEvent=recordFailureCase(path.join(config.workbenchRoot??task?.attemptDir??base,'case-events'),{figureId:admissionPlan.figureId,plan:{...admissionPlan,qualityRoute:'raster'},error,stage,engineSignature:config.runtimeLock?.engineSignature});}
   catch(caseError){caseIndexError=caseError.message;}
   if(admissionPlan&&['render','check'].includes(stage))try{alternativeSearch=searchFailureAlternatives({registryPath:config.caseIndexPath??fileURLToPath(new URL('../knowledge/figure-cases.json',import.meta.url)),eventDirectory:path.join(config.workbenchRoot??task?.attemptDir??base,'case-events'),error,plan:admissionPlan});}
   catch(caseError){alternativeSearch={status:'search_failed',error:caseError.message};}
   if(task&&ownsLock&&!publicationStarted){
    try{await api({action:'fail-direct',id:task.id,attempt:task.attempt,message:error.message});}
    catch(reportError){return {id:item.id,label:task.label,status:'failed',stage,failure,error:error.message,reportError:reportError.message};}
   }
   return {id:item.id,label:task?.label,status:publicationStarted?'awaiting-verification':'failed',stage,failure,error:error.message,elapsedMs:performance.now()-started,...(caseFailureEvent?{caseFailureEvent}:{}),...(caseIndexError?{caseIndexError}:{}),...(alternativeSearch?{alternativeSearch}:{})};
  }finally{
   if(ownsLock&&fs.existsSync(lock)){
    const owner=read(lock);if(owner.pid===process.pid)fs.unlinkSync(lock);
   }
  }
 }
 await Promise.all(Array.from({length:Math.min(concurrency,manifest.items.length)},async()=>{
  while(cursor<manifest.items.length){const item=manifest.items[cursor++],result=await processItem(item);results.push(result);onResult(result);}
 }));
 const returned=results.filter(r=>r.status==='returned'),failureCounts={};
 for(const r of results)if(r.failure)failureCounts[r.failure.code]=(failureCounts[r.failure.code]??0)+1;
 const report={version:1,startedAt,endedAt:new Date().toISOString(),results,returnedFigures:returned.length,returnedOutputs:returned.reduce((n,r)=>n+r.receipt.outputs.length,0),failureCounts,failed:results.filter(result=>!['returned','already_returned'].includes(result.status)).length};
 const reportPath=path.join(base,path.basename(manifestPath,'.json')+'.'+Date.now()+'.run.json');writeOnce(reportPath,report);
 return {...report,reportPath};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const [config,manifest]=process.argv.slice(2);if(!config||!manifest)throw Error('Usage: node raster-batch.mjs worker-config.json batch-manifest.json');const result=await runRasterBatch(config,manifest);console.log(JSON.stringify(result));if(result.failed)process.exitCode=1;}
 catch(error){console.error(error.message);process.exitCode=1;}
}
