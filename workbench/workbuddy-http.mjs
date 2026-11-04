import {catalogFor,belongsToBatch} from './batch-scope.mjs';
import {timingSafeEqual} from 'node:crypto';
import fs from 'node:fs';
import {digest} from './revision-worker.mjs';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
import {buildFigureTasks} from './workbuddy-plan.mjs';
import {summarizeProduction} from './workbuddy-summary.mjs';
import path from 'node:path';
import {acceptedDirectVersionMatches,recordedDirectVersionMatches} from './workbuddy-candidates.mjs';
import {assertCompleteOutputSet} from './multi-output.mjs';

function inspectDirectPublication(job,result,getState,{qualityPython}={}){
 if(typeof getState!=='function')return 'unknown';
 let target;try{target=getState(structuredClone(job));}catch{return 'unknown';}
 if(!target||typeof target!=='object'||target.then)return 'unknown';
 if(!Array.isArray(target.outputs))return 'unknown';
 if(acceptedDirectVersionMatches(target,result)){
  if(!target.outputs.length)return 'accepted-version';
  const exact=target.outputs.length===result.outputs.length&&result.outputs.every((expected,index)=>{
   const actual=target.outputs[index];if(actual?.number!==expected.number)return false;
   try{const actualPath=actual.path??actual.file?.path??actual.file?.href??actual.file;return typeof actualPath==='string'&&actualPath===expected.path&&digest(actualPath)===expected.sha256&&actual.sha256===expected.sha256;}catch{return false;}
  });
  return exact?'applied':'unknown';
 }
 // A previously published base may be rehydrated after restart even when the
 // user has since left feedback. This path only rebuilds an empty in-memory
 // figure; it never publishes a new result or changes feedback/acceptance.
 let acceptedBeforeFeedback=false;
 if(!target.outputs.length&&target.userAcceptance?.accepted===true&&Number.isSafeInteger(target.feedbackRevision)&&target.feedbackRevision>0){
  for(let revision=0;revision<target.feedbackRevision;revision++){
   if(acceptedDirectVersionMatches({...target,feedbackRevision:revision},result)){acceptedBeforeFeedback=true;break;}
  }
 }
 const withdrawnSameVersion=target.userAcceptance?.accepted===false&&recordedDirectVersionMatches(target,result);
 if(job.state==='ready'&&job.publicationState==='published'&&job.returnMode==='automatic-candidate'&&
    job.qualityVerification?.kind==='automatic-candidate'&&job.qualityVerification?.status==='candidate'&&
    job.qualityVerification?.manualStatus==='pending'&&!target.outputs.length&&
    (target.accepted!==true||acceptedBeforeFeedback)&&target.approved!==true&&(!target.userAcceptance||acceptedBeforeFeedback||withdrawnSameVersion)&&
    target.status!=='终检通过'&&Array.isArray(result?.outputs)&&result.outputs.length>0&&
    Array.isArray(job.outputNumbers)&&job.outputNumbers.length===result.outputs.length&&
    result.outputs.every((output,index)=>output.number===job.outputNumbers[index]&&typeof output.path==='string'&&
      /^[a-f0-9]{64}$/.test(output.sha256||'')&&(()=>{try{return digest(output.path)===output.sha256;}catch{return false;}})())){
  try{if(job.outputNumbers.length>1)assertCompleteOutputSet(job,undefined,{python:qualityPython});return 'published-base';}
  catch{return 'unknown';}
 }
 if(target.feedback||target.userFeedback||target.accepted||target.approved||target.userAcceptance||target.feedbackRevision||target.revisionHistory?.length)return 'unknown';
 if(!target.outputs.length)return target.status==='待制作'?'empty':'unknown';
 if(target.status!=='待终检'||target.outputs.length!==result.outputs?.length)return 'unknown';
 const matches=result.outputs.every((expected,index)=>{
  const actual=target.outputs[index];if(actual?.number!==expected.number)return false;
  try{
   const actualPath=actual.path??actual.file?.path??actual.file?.href??actual.file;
   return typeof actualPath==='string'&&path.resolve(actualPath)===path.resolve(expected.path)&&digest(actualPath)===expected.sha256&&actual.sha256===expected.sha256;
  }catch{return false;}
 });
 return matches?'applied':'unknown';
}

function restoreDirectCandidateSafely(job,result,getState,options){
 return inspectDirectPublication(job,result,getState,options);
}
function legacyPublishedReceiptMatches(root,job,result,{qualityPython}={}){
 try{
  if((job.publicationState!==undefined&&job.publicationState!==null)||job.state!=='ready'||job.executionMode!=='direct'||job.returnMode!=='automatic-candidate'||
     job.qualityVerification?.kind!=='automatic-candidate'||job.qualityVerification?.status!=='candidate'||job.qualityVerification?.manualStatus!=='pending')return false;
  const attemptDir=path.resolve(job.attemptDir),expectedDir=path.resolve(root,job.id,String(job.attempt));
  if(fs.realpathSync(attemptDir)!==fs.realpathSync(expectedDir))return false;
  const events=fs.readFileSync(path.join(root,job.id,'events.jsonl'),'utf8').trim().split(/\r?\n/).filter(Boolean).map(line=>JSON.parse(line));
  const last=events.at(-1),published='自动候选检查通过，已回传待用户终审';
  const lastDirectStart=events.findLastIndex(event=>event.message==='直接批量制作：已绑定来源与隔离目录，无需派单领取');
  if(!last?.message?.startsWith(published)||lastDirectStart<0||Date.parse(events[lastDirectStart].at)>=Date.parse(last.at))return false;
  const eventAt=Date.parse(last.at),updatedAt=Date.parse(job.updatedAt);
  if(!Number.isFinite(eventAt)||!Number.isFinite(updatedAt)||eventAt>updatedAt||updatedAt-eventAt>60000)return false;
  const task=JSON.parse(fs.readFileSync(path.join(attemptDir,'task.json'),'utf8'));
  const submitted=JSON.parse(fs.readFileSync(path.join(attemptDir,'candidate-submission.json'),'utf8'));
  const attemptResult=JSON.parse(fs.readFileSync(path.join(attemptDir,'result.json'),'utf8'));
  if(task.id!==job.id||task.articleId!==job.articleId||String(task.figureNumber)!==String(job.figureNumber)||
     JSON.stringify(task.outputNumbers)!==JSON.stringify(job.outputNumbers)||!Array.isArray(result?.outputs)||
     !Array.isArray(submitted.outputs)||!Array.isArray(attemptResult.outputs)||
      result.outputs.length!==job.outputNumbers?.length||submitted.outputs.length!==result.outputs.length||attemptResult.outputs.length!==result.outputs.length)return false;
  for(let i=0;i<result.outputs.length;i++){
   const output=result.outputs[i],submittedOutput=submitted.outputs[i],attemptOutput=attemptResult.outputs[i];
   if(output.number!==job.outputNumbers[i]||!/^([a-f0-9]{64})$/.test(output.sha256||'')||
      path.resolve(path.dirname(output.path))!==path.resolve(attemptDir,'candidate')||digest(output.path)!==output.sha256||
      submittedOutput.number!==output.number||path.resolve(submittedOutput.path)!==path.resolve(output.path)||submittedOutput.sha256!==output.sha256||
       attemptOutput.number!==output.number||path.resolve(attemptOutput.path)!==path.resolve(output.path)||attemptOutput.sha256!==output.sha256)return false;
  }
  const selfCheck=job.qualityVerification.selfCheck,candidate=job.qualityVerification.candidate;
  if(!selfCheck||!candidate||path.resolve(path.dirname(selfCheck.path))!==path.resolve(attemptDir,'self-checks')||
     path.resolve(candidate.path)!==path.resolve(attemptDir,'candidate','.task-quality','candidate.json')||
     digest(selfCheck.path)!==selfCheck.sha256||digest(candidate.path)!==candidate.sha256||
      attemptResult.selfCheck?.sha256!==selfCheck.sha256)return false;
  const gate=JSON.parse(fs.readFileSync(candidate.path,'utf8'));
  if(gate.status!=='candidate'||gate.manual_status!=='pending'||!Array.isArray(gate.references)||!Array.isArray(gate.previews))return false;
  for(const reference of gate.references)if(!reference?.path||!/^[a-f0-9]{64}$/.test(reference.sha256||'')||digest(reference.path)!==reference.sha256)return false;
  for(const output of result.outputs){
   if(!gate.references.some(reference=>path.resolve(reference.path)===path.resolve(output.path)&&reference.sha256===output.sha256))return false;
   const preview=gate.previews.find(item=>path.resolve(item.path)===path.resolve(output.preview));
   if(!preview||preview.sha256!==output.previewSha256||digest(preview.path)!==preview.sha256)return false;
  }
  if(job.outputNumbers.length>1)assertCompleteOutputSet(job,undefined,{python:qualityPython});
  return true;
 }catch{return false;}
}
export function createWorkBuddyHandler({root,origin,config,publish,restore,restoreAccepted,prepareFigures,verifyQuality,verifyAutomatic,figures=()=>null,getDirectPublicationState,assertRouteEditable,assertRoutineEligible}){
 const queue=createWorkBuddyQueue({root,qualityPython:config.qualityPython,verifyQuality,verifyAutomatic,assertRouteEditable,routineTrial:config.routineTrial,assertRoutineEligible,automaticRasterBatches:config.automaticRasterBatches,directProduction:config.directProduction,publish(job,result){if(job.kind==='inventory'){const tasks=buildFigureTasks(catalogFor(config,job.batchHash),result);for(const task of tasks)for(const source of task.sources)if(digest(source.path)!==source.sha256)throw Error('分组来源已变更，未派发制作');for(const task of tasks)queue.enqueue(task);}else return publish(job,result);}});
 prepareFigures?.(queue.list());
 for(const j of queue.list().filter(j=>j.state==='ready'&&j.result&&!['inventory','revision'].includes(j.kind)).sort((a,b)=>(a.updatedAt||a.createdAt).localeCompare(b.updatedAt||b.createdAt)||a.id.localeCompare(b.id))){
  if(j.executionMode==='direct'||(j.publicationState==='published'&&j.returnMode==='automatic-candidate')){
   const publication=restoreDirectCandidateSafely(j,j.result,getDirectPublicationState,{qualityPython:config.qualityPython});
   if(publication==='applied'){queue.markPublished(j.id);continue;}
   if(publication==='accepted-version'){
    if(typeof restoreAccepted!=='function')continue;
    restoreAccepted(j,j.result);queue.markPublished(j.id);continue;
   }
   if(publication==='published-base'){restore(j,j.result);queue.markPublished(j.id);continue;}
   if(publication==='unknown'&&j.publicationState==null&&legacyPublishedReceiptMatches(root,j,j.result,{qualityPython:config.qualityPython})){
    let target;try{target=getDirectPublicationState(structuredClone(j));}catch{target=null;}
    if(target&&Array.isArray(target.outputs)&&target.outputs.length===0&&target.accepted!==true&&target.approved!==true&&!target.userAcceptance&&target.status!=='终检通过'){
     restore(j,j.result);queue.markPublished(j.id);continue;
    }
   }
   if(publication!=='empty')continue;
  }
  restore(j,j.result);queue.markPublished(j.id);
 }
 const json=(res,status,value)=>res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(value));
 const authorized=(req,token)=>{if(typeof token!=='string'||!token.trim())return false;const a=Buffer.from(req.headers.authorization||''),b=Buffer.from('Bearer '+token);return a.length===b.length&&timingSafeEqual(a,b);};
 return {queue,handle(req,res,url){
  if(!url.pathname.startsWith('/workbuddy/'))return false;
  if(req.method==='GET'&&url.pathname==='/workbuddy/status'){const jobs=queue.list();json(res,200,{executionMode:config.directProduction?.enabled?'direct':'queued',summary:summarizeProduction(jobs,figures()),jobs:jobs.map(({id,key,label,group,state,attempt,message,kind,createdAt,updatedAt,executor,articleId,figureId,figureNumber})=>({id,key,label,group,state,attempt,message,kind,createdAt,updatedAt,executor,articleId,figureId,figureNumber})),worker:queue.worker(),pilot:config.pilot?{key:config.pilot.key,label:config.pilot.label,group:config.pilot.group}:null,inventoryAvailable:!!config.inventory});return true;}
  if(req.method==='GET'&&url.pathname==='/workbuddy/events'){try{json(res,200,{events:queue.events(url.searchParams.get('id'))});}catch(e){json(res,404,{error:e.message});}return true;}
  const workerRoute=url.pathname==='/workbuddy/worker',reviewRoute=url.pathname==='/workbuddy/review-candidate';
  if(req.method!=='POST'||(reviewRoute?!authorized(req,config.reviewerToken):workerRoute?!authorized(req,config.workerToken):req.headers.origin!==origin)){json(res,403,{error:'请求来源未授权'});return true;}
  let bytes=0,chunks=[];req.on('data',c=>{bytes+=c.length;if(bytes<1024*1024)chunks.push(c);});
  req.on('end',async()=>{try{
   if(bytes>=1024*1024)throw Error('请求过大');
   const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));let result={ok:true};
   if(workerRoute){
    const {action,id,lease}=body;
    const batchHash=body.batchHash??(config.catalogs?config.catalog?.batchHash:undefined);
    if(config.catalogs&&!batchHash)throw Error('多批次执行器必须指定批次');
    if(batchHash!==undefined){catalogFor(config,batchHash);if(id&&!belongsToBatch(queue.list().find(j=>j.id===id)||{},batchHash))throw Error('任务不属于请求批次');}
    if(action==='prepare-import'){
     const catalog=catalogFor(config,batchHash),task=body.task,route=body.productionRoute;
     if(!task||!batchHash||task.batchHash!==batchHash)throw Error('候选导入须显式绑定当前批次');
     const article=catalog.articles?.find(value=>value.id===task.articleId);
     if(!article||!article.word||article.word.path!==route?.sourceReview?.word?.path||article.word.sha256!==route?.sourceReview?.word?.sha256||catalog.archive?.path!==route?.sourceReview?.archive?.path||catalog.archive?.sha256!==route?.sourceReview?.archive?.sha256)throw Error('候选导入的文章Word或原包与服务端批次清单不符');
     const registered=figures();
     if(!Array.isArray(registered))throw Error('服务端未提供当前工作台图号清单');
     const paperFigures=registered.filter(figure=>figure.articleId===task.articleId),registeredNumbers=paperFigures.map(figure=>figure.number);
     if(!registeredNumbers.includes(task.figureNumber)||!Array.isArray(task.mainNumbers)||new Set(task.mainNumbers).size!==task.mainNumbers.length||registeredNumbers.length!==task.mainNumbers.length||registeredNumbers.some(number=>!task.mainNumbers.includes(number)))throw Error('候选导入主图号或完整图号集合与工作台权威清单不符');
     const target=paperFigures.find(figure=>figure.number===task.figureNumber);
     const existingPdf=body.existingPdf===true;
     if(existingPdf&&route?.method!=='editable-pdf')throw Error('既有PDF候选必须绑定可编辑PDF路线');
     const importKey='candidate-import:'+batchHash+':'+task.articleId+':'+task.figureNumber+':'+(existingPdf?task.existingPdfManifest?.sha256:(task.outputSetEvidence?.sha256||route?.sourceReview?.selected?.sha256));
     const sameImport=queue.list().find(job=>job.key===importKey||job.candidateImportKey===importKey);
     const pendingReturned=sameImport?.state==='ready'&&sameImport.result&&sameImport.qualityVerification?.manualStatus==='pending'&&
      Array.isArray(sameImport.outputNumbers)&&sameImport.result.outputs?.length===sameImport.outputNumbers.length&&
      sameImport.result.outputs.every((output,index)=>output.number===sameImport.outputNumbers[index]);
     const feedbackPresent=target.feedback||target.accepted||target.approved||target.userAcceptance||target.userFeedback;
     if(feedbackPresent)throw Error('目标图已有批注或验收状态，不能导入覆盖');
     let publicationState;
     if(pendingReturned){
      if(sameImport.publicationState!=='published'){
       publicationState=inspectDirectPublication(sameImport,sameImport.result,getDirectPublicationState);
       if(!['empty','applied'].includes(publicationState))throw Error('待恢复候选缺少可验证的服务端图件状态，拒绝覆盖/重复登记');
      }
     }else if((target.status!==undefined&&target.status!=='待制作')||target.outputs?.length)throw Error('目标图已有成图或状态，不能导入覆盖');
     if((target.pendingReview||target.needsUserDecision)&&sameImport?.state!=='ready')throw Error('目标图已有候选或待用户决定，不能重复导入');
     result=await queue.prepareImport(task,route,batchHash,{publicationState,existingPdf});
    }
    else if(action==='prepare-direct')result=queue.prepareDirect(id,body.productionRoute,body.outputRoutes);
    else if(action==='submit-direct')await queue.submitDirect(id,body.attempt,body.result);
    else if(action==='submit-imported-pdf')result={job:await queue.submitImportedPdf(id,body.attempt,body.input)};
    else if(action==='retry-imported-pdf')result={job:queue.retryImportedPdf(id,body.attempt,body.widths,body.replacementManifest)};
    else if(action==='fail-direct')queue.failDirect(id,body.attempt,body.message);
    else if(action==='claim'){
     const job=queue.claim(body.session||'WorkBuddy',batchHash),jobs=queue.list(),routine=queue.routineOptions();
     routine.paused=routine.paused.filter(j=>belongsToBatch(jobs.find(t=>t.id===j.id)||{},batchHash));
     const queued=jobs.filter(j=>j.state==='queued'&&belongsToBatch(j,batchHash)).length;
     if(!job&&queued){
      const active=jobs.find(j=>['running','pausing','interrupted'].includes(j.state));
      routine.status='waiting_executor';routine.queued=queued;
      routine.reason=`${active&&!belongsToBatch(active,batchHash)?'另一批次':'当前执行任务'}占用全局制作租约，本批 ${queued} 个任务等待领取；保持串行，租约释放后继续领取`;
     }else if(!job&&routine.status==='awaiting_selection'&&!routine.paused.some(j=>j.eligible)){
      routine.status=routine.paused.length?'tool_blocked':'idle';routine.reason=routine.paused.length?'本批暂停任务均不可自主恢复，请查看逐项原因':'本批没有可领取或可自主恢复的任务；不选择其他批次';
     }
     result=job?{job}:{job:null,routine};
    }
    else if(action==='resume-routine')result={job:queue.resumeRoutine(id,body.productionRoute)};
    else if(action==='retry-routine')result={job:queue.retryRoutine(id,lease)};
    else if(action==='heartbeat')result=queue.heartbeat(id,lease);
    else if(action==='progress')queue.progress(id,lease,body.message);
    else if(action==='prepare-route')result={task:queue.prepareRoute(id,lease,body.productionRoute)};
    else if(action==='paused')queue.acknowledgePause(id,lease);
    else if(action==='fail')queue.fail(id,lease,body.message,body.needsInput===true);
    else if(action==='submit-candidate')await queue.submitCandidate(id,lease,body.result);
    else if(action==='complete'){
     if(queue.list().find(j=>j.id===id)?.kind!=='inventory')throw Error('成图须先submit-candidate，独立复核后才能回传终审');
     await queue.complete(id,lease,body.result);
    }
    else throw Error('未知执行操作');
   }else if(reviewRoute){
    if(body.decision==='rejected')queue.rejectCandidate(body.id,body.reason);
    else await queue.reviewCandidate(body.id,body.result);
   }else if(url.pathname==='/workbuddy/start-pilot'){
    if(!config.pilot)throw Error('尚未配置已核对的试跑图件');result={job:queue.enqueue(config.pilot)};
   }else if(url.pathname==='/workbuddy/start-inventory'){
    if(body.batchHash!==undefined){catalogFor(config,body.batchHash);const inventory=config.inventories?.[body.batchHash];if(!inventory||inventory.batchHash!==body.batchHash)throw Error('本批次未配置来源核对任务');result={job:queue.enqueue(inventory)};}else{ if(!config.inventory||!queue.list().some(j=>j.key===config.pilot.key&&j.state==='ready'))throw Error('先完成单图试跑并回传，再进行本批图种分组');result={job:queue.enqueue(config.inventory)};}
   }else if(url.pathname==='/workbuddy/control'){
    if(config.directProduction?.enabled)throw Error('当前使用直接制作，调度控制已停用');
    if(body.action==='retry'&&queue.list().some(j=>j.id===body.id&&j.kind==='revision'))throw Error('终审修订须先由 ChatGPT 排障并更新执行说明，不能直接重跑旧计划');
    if(body.action==='pause')queue.pause(body.id);else if(body.action==='resume')queue.resume(body.id);else if(body.action==='retry')queue.retry(body.id,body.confirmedStopped===true);else throw Error('未知控制操作');
   }else throw Error('未知入口');
   json(res,200,result);
  }catch(e){json(res,409,{error:e.message});}});return true;
 }};
}
