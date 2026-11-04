import {belongsToBatch} from './batch-scope.mjs';
import {dispatchInstructions} from './production-dispatch.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import {atomicJson} from './revision-jobs.mjs';
import {digest,checkedArtifact} from './revision-worker.mjs';
import {assertOutputRoutes,assertProductionRoute,productionInstructions,verifyProductionResult,routeSourceRefs} from './production-route.mjs';
import * as routeQuality from './production-route.mjs';
import {prepareDirectProduction} from './direct-production.mjs';
import {assertCompleteOutputSet} from './multi-output.mjs';
import {verifyImportedPdfCandidate} from './imported-pdf.mjs';
export function createWorkBuddyQueue({root,publish,now=()=>Date.now(),qualityPython,verifyQuality=verifyProductionResult,verifyAutomatic=(...args)=>routeQuality.verifyAutomaticCandidate(...args),assertRouteEditable=()=>{},routineTrial,assertRoutineEligible,automaticRasterBatches=[],directProduction}){
 fs.mkdirSync(root,{recursive:true});
 const jobs=fs.readdirSync(root).filter(n=>/^[a-f0-9-]{36}$/.test(n)).map(id=>JSON.parse(fs.readFileSync(path.join(root,id,'job.json'),'utf8')));
 let worker=null;
 const completing=new Set();
 const leaseHash=lease=>createHash('sha256').update(String(lease)).digest('hex');
 const hasEntries=value=>Array.isArray(value)?value.length>0:value&&typeof value==='object'?Object.keys(value).length>0:Boolean(value);
 const hasFeedback=value=>Boolean(value&&(value.text?.trim()||hasEntries(value.annotations)||hasEntries(value.points)||hasEntries(value.attachments)||value.revision>0));
 const automaticTrial=j=>trialEnabled()&&routineTrial.autoReturn===true&&j.routineTrialId===routineTrial.id;
 const automatic=j=>typeof assertRoutineEligible==='function'&&(!j.kind||j.kind==='production')&&j.productionRoute?.method==='raster-preserve'&&(automaticTrial(j)||Array.isArray(automaticRasterBatches)&&automaticRasterBatches.some(hash=>typeof hash==='string'&&/^[a-f0-9]{64}$/.test(hash)&&belongsToBatch(j,hash)));
 function routeSealed(dir){
  for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
   if(entry.name==='.task-quality-owner.json'||entry.name==='candidate-submission.json')return true;
   if(entry.isDirectory()&&(entry.name==='.task-quality'||routeSealed(path.join(dir,entry.name))))return true;
  }
  return false;
 }
 const save=j=>{j.updatedAt=new Date(now()).toISOString();atomicJson(path.join(root,j.id,'job.json'),j);};
 const event=(j,message)=>{fs.appendFileSync(path.join(root,j.id,'events.jsonl'),JSON.stringify({at:new Date(now()).toISOString(),message:String(message).slice(0,16000)})+'\n');j.message=String(message).slice(0,250);save(j);};
 const get=id=>{const j=jobs.find(j=>j.id===id);if(!j)throw Error('任务不存在');return j;};
 const trialFile=path.join(root,'routine-trials.json');
 const trials=fs.existsSync(trialFile)?JSON.parse(fs.readFileSync(trialFile,'utf8')):{};
 const trialEnabled=()=>routineTrial&&typeof routineTrial.id==='string'&&/^[a-zA-Z0-9_-]{1,80}$/.test(routineTrial.id)&&Number.isInteger(routineTrial.maxTasks)&&routineTrial.maxTasks>0&&routineTrial.maxTasks<=500&&Array.isArray(routineTrial.groups)&&routineTrial.groups.length>0&&typeof assertRoutineEligible==='function';
 const trialUsed=()=>new Set([...(trials[routineTrial?.id]||[]).map(r=>r.id),...jobs.filter(j=>j.routineTrialId===routineTrial?.id&&j.routineTrialId).map(j=>j.id)]).size;
 const sameRef=(a,b)=>a&&b&&path.resolve(a.path)===path.resolve(b.path)&&a.sha256===b.sha256;
 function routineEligibility(j,route=null){
  if(!trialEnabled())throw Error('未启用常规图试运行授权及权威状态检查');
  if(j.state!=='paused'||j.attempt!==0||j.kind&&j.kind!=='production'||j.result||j.candidateResult||j.accepted||j.approved||hasFeedback(j.feedback)||j.feedbackRevision||j.revisionHistory?.length)throw Error('仅未生产、无反馈且未批准的暂停常规图可自主恢复');
  if(!j.articleId||!j.figureNumber||!routineTrial.groups.includes(j.group)||j.productionRoute&&j.productionRoute.method!=='raster-preserve')throw Error('任务不在本次常规位图授权范围');
  if(jobs.some(other=>other.id!==j.id&&other.articleId===j.articleId&&other.figureNumber===j.figureNumber&&(other.state!=='paused'||other.attempt>0||other.result||other.candidateResult)))throw Error('同图已有新版或其他执行任务，不得重复恢复');
  const anchors=assertRoutineEligible(structuredClone(j),route&&structuredClone(route));
  if(!anchors||anchors.then||!['archive','word'].every(k=>anchors[k]&&j.sources.some(s=>sameRef(s,anchors[k]))))throw Error('权威检查须返回原任务已登记的原包及Word身份');
  if(route){
   for(const s of j.sources)if(digest(s.path)!==s.sha256)throw Error('任务来源已变化');
   assertProductionRoute({...j,legacyProductionInstructions:undefined,productionRoute:route});
   if(route.method!=='raster-preserve'||!['archive','word'].every(k=>sameRef(anchors[k],route.sourceReview[k])))throw Error('自主路线必须绑定原任务的原包及Word且为常规位图');
  }
  return anchors;
 }
 const claimed=(id,lease)=>{const j=get(id);if(!['running','pausing','interrupted'].includes(j.state)||!lease||j.lease!==lease)throw Error('任务租约已失效，不能回传');if(j.state==='interrupted'){j.state=j.pauseRequested?'pausing':'running';event(j,'原 WorkBuddy 会话重新连接，继续同一尝试');}return j;};
 function expire(){for(const j of jobs)if(!['direct','imported-pdf'].includes(j.executionMode)&&['running','pausing'].includes(j.state)&&now()-j.heartbeatAt>120000){j.state='interrupted';event(j,'超过2分钟没有进度心跳，执行状态待核实；原会话可续接，不自动重做');}}
 function inspectCandidate(j,result){
  if(j.kind==='inventory')throw Error('来源清单不使用成图候选入口');
  const route=assertProductionRoute(j),raster=route.method==='raster-preserve';
  if(j.outputNumbers.length>1){assertCompleteOutputSet(j,undefined,{python:qualityPython});assertOutputRoutes(j);}
  for(const s of j.sources)if(digest(s.path)!==s.sha256)throw Error('源件已变更，不能回传');
  if(!result.evidence?.trim()||!Array.isArray(result.outputs)||!result.outputs.length)throw Error('缺少产物或原图/最终图核对证据');
  const seen=new Set();
  for(const o of result.outputs){
   if(!/^\d+(?:[.-]\d+)*$/.test(o.number)||seen.has(o.number)||!j.outputNumbers.includes(o.number))throw Error('输出图号与已核对任务不符');seen.add(o.number);
   o.path=checkedArtifact(j.attemptDir,o.path,/^\.(pdf|jpg|jpeg)$/i);o.preview=checkedArtifact(j.attemptDir,o.preview,/^\.png$/i);
   if(digest(o.path)!==o.sha256)throw Error('产物哈希不一致');
   const bytes=fs.readFileSync(o.path),png=fs.readFileSync(o.preview),pdf=path.extname(o.path).toLowerCase()==='.pdf';
   if(raster?pdf:!pdf)throw Error(raster?'位图保留路线必须交付JPG':'可编辑路线必须交付PDF');
   if(pdf?!bytes.subarray(0,5).equals(Buffer.from('%PDF-')):bytes[0]!==255||bytes[1]!==216)throw Error('产物格式无效');
   if(raster&&o.fontLabel!=='')throw Error('位图内部字号不得作为交付标签');
   if(!png.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))throw Error('预览格式无效');
   o.previewSha256=digest(o.preview);
  }
  if(j.outputNumbers.some(n=>!seen.has(n)))throw Error('本任务导出项未齐备');
 }
 async function publishReviewed(j,result){
  j.qualityVerification=await verifyQuality(j,result,{python:qualityPython});
  atomicJson(path.join(j.attemptDir,'result.json'),result);
  await publish(j,result);j.result=result;j.state='ready';delete j.lease;event(j,'成图已回传，等待终审；未自动验收');
 }
 async function submitAutomatic(j,candidate,lease){
  completing.add(j.id);
  try{
   if(j.outputNumbers.length>1)assertCompleteOutputSet(j,undefined,{python:qualityPython});
   atomicJson(path.join(j.attemptDir,'candidate-submission.json'),candidate);
   inspectCandidate(j,candidate);
   const receipt=await verifyAutomatic(j,candidate,{python:qualityPython});
   if(receipt?.kind!=='automatic-candidate'||receipt.status!=='candidate'||(receipt.manualStatus??receipt.manual_status)!=='pending')throw Error('自动候选门禁未返回明确待人工终审状态');
   j.qualityVerification={...receipt,manualStatus:'pending'};
   if(j.outputNumbers.length>1)assertCompleteOutputSet(j,undefined,{python:qualityPython});
   atomicJson(path.join(j.attemptDir,'result.json'),candidate);
   const current=assertRoutineEligible(structuredClone(j),structuredClone(j.productionRoute));
   if(!current||current.then||!['archive','word'].every(k=>sameRef(current[k],j.productionRoute.sourceReview[k])))throw Error('回传前权威来源身份不一致');
   j.result=candidate;j.state='ready';j.publicationState='pending';delete j.lease;delete j.retryLeaseHash;
   event(j,'自动候选检查通过，完整输出集合已封存，等待工作台原子登记；尚未验收');
   await publish(j,candidate);
   j.publicationState='published';event(j,'多输出候选已原子登记，等待用户终审；人工终审未完成、未自动验收');
  }catch(error){
   if(j.state==='ready'&&j.result===candidate){j.publicationState='pending';event(j,'候选质量已通过且已持久化；工作台登记待恢复：'+error.message);throw error;}
   atomicJson(path.join(j.attemptDir,'candidate-error.json'),{at:new Date(now()).toISOString(),error:error.message});
   j.state='failed';if(lease)j.retryLeaseHash=leaseHash(lease);delete j.lease;event(j,'自动候选回传阻断：'+error.message);throw error;
  }finally{completing.delete(j.id);}
 }
 for(const j of jobs)if(!['direct','imported-pdf'].includes(j.executionMode)&&['running','pausing'].includes(j.state)){j.state='interrupted';event(j,'工作台重启，等待原 WorkBuddy 会话续接；未启动重复制作');}
 return {
  prepareDirect(id,route,outputRoutes){
   const j=get(id),result=prepareDirectProduction(j,route,{root,jobs,config:directProduction,assertCurrent:assertRoutineEligible,outputRoutes});
   if(!result.alreadyReturned&&!result.resumed){event(j,'直接批量制作：已绑定来源与隔离目录，无需派单领取');atomicJson(path.join(j.attemptDir,'task.json'),j);}
   return result;
  },
  markPublished(id){
   const j=get(id);if(j.state!=='ready'||!j.result)throw Error('只有已持久化候选可以登记完成');
   if(j.publicationState!=='published'){j.publicationState='published';event(j,'已从持久化候选恢复工作台登记；仍待用户终审');}
   return structuredClone(j);
  },
  async prepareImport(input,route,batchHash,{publicationState,existingPdf=false}={}){
   if(!directProduction?.enabled||typeof assertRoutineEligible!=='function')throw Error('未启用受控候选导入及权威状态核验');
   if(!input||input.batchHash!==batchHash||!directProduction.batchHashes?.includes(batchHash))throw Error('候选导入批次或图种不在服务端授权范围');
   const pdfImportKey=existingPdf&&input.existingPdfManifest?.sha256?'candidate-import:'+batchHash+':'+input.articleId+':'+input.figureNumber+':'+input.existingPdfManifest.sha256:null;
   const samePdfImport=pdfImportKey&&jobs.some(job=>job.key===pdfImportKey||job.candidateImportKey===pdfImportKey);
   const pausedLegacy=existingPdf&&jobs.some(job=>job.articleId===input.articleId&&job.figureNumber===input.figureNumber&&job.group===input.group&&job.state==='paused'&&job.attempt===0&&!job.result&&!job.candidateResult&&!job.approved&&!job.accepted&&!job.userAcceptance&&!hasFeedback(job.feedback)&&!job.feedbackRevision&&!job.revisionHistory?.length);
   if(!directProduction.groups?.includes(input.group)&&!samePdfImport&&!pausedLegacy)throw Error('候选导入批次或图种不在服务端授权范围');
   if(input.kind&&input.kind!=='production'||input.id||input.result||input.candidateResult||input.accepted||input.approved||hasFeedback(input.feedback)||input.feedbackRevision||input.revisionHistory?.length||input.userAcceptance)throw Error('候选导入不能带入既有结果、反馈或验收状态');
   if(!Array.isArray(input.outputNumbers)||!input.outputNumbers.length)throw Error('受控导入缺少输出集合');
   let importedManifest=null,importedOutputs=[];
   if(existingPdf){
    if(route.method!=='editable-pdf'||!input.existingPdfManifest)throw Error('既有候选导入必须绑定可编辑PDF路线及输出清单');
    const manifestRef=input.existingPdfManifest;
    if(!/^[a-f0-9]{64}$/.test(manifestRef.sha256||'')||digest(manifestRef.path)!==manifestRef.sha256)throw Error('既有PDF候选清单哈希不符');
    const manifest=JSON.parse(fs.readFileSync(manifestRef.path,'utf8'));
    if(manifest.version!==1||manifest.articleId!==input.articleId||String(manifest.figureNumber)!==String(input.figureNumber)||!Array.isArray(manifest.outputs)||manifest.outputs.length!==input.outputNumbers.length)throw Error('既有PDF清单稿件身份或输出集合不符');
    const numbers=new Set();
    importedOutputs=manifest.outputs.map(output=>{
     if(typeof output.number!=='string'||!input.outputNumbers.includes(output.number)||numbers.has(output.number)||!output.path||path.extname(output.path).toLowerCase()!=='.pdf'||digest(output.path)!==output.sha256)throw Error('既有PDF清单含重复图号、非PDF或哈希不符');
     numbers.add(output.number);return {number:output.number,source:{path:path.resolve(output.path),sha256:output.sha256}};
    });
    if(input.outputNumbers.some(number=>!numbers.has(number)))throw Error('既有PDF清单未覆盖完整任务图号集合');
    importedManifest={path:path.resolve(manifestRef.path),sha256:manifestRef.sha256};
   }
   const routes=input.outputRoutes??[{number:input.outputNumbers[0],productionRoute:route}];
   const task={key:'candidate-import:'+batchHash+':'+input.articleId+':'+input.figureNumber+':'+(existingPdf?importedManifest.sha256:(input.outputSetEvidence?.sha256||route?.sourceReview?.selected?.sha256)),
    label:input.label,group:input.group,articleId:input.articleId,figureId:input.figureId,figureNumber:input.figureNumber,
    mainNumbers:input.mainNumbers,outputNumbers:input.outputNumbers,outputRoutes:routes,outputSetEvidence:input.outputSetEvidence,batchHash,productionRoute:route,
    sources:[...new Map([...(input.sources||[]),...routes.flatMap(entry=>routeSourceRefs(entry.productionRoute)),...(input.outputSetEvidence?[input.outputSetEvidence]:[]),...(existingPdf?[importedManifest,...importedOutputs.map(output=>output.source)]:[])].map(source=>[path.resolve(source.path),source])).values()],
    sourceEvidence:input.sourceEvidence,articleEvidence:input.articleEvidence,kind:'production'};
   if(typeof task.articleId!=='string'||!task.articleId||typeof task.label!=='string'||!task.label||!Array.isArray(task.mainNumbers)||!task.mainNumbers.includes(task.figureNumber))throw Error('候选导入缺少文章身份、主图号或核对说明');
   assertOutputRoutes(task,routes);
   if(input.outputNumbers.length===1&&input.outputNumbers[0]===input.figureNumber){
    if(routes.length!==1||JSON.stringify(routes[0].productionRoute)!==JSON.stringify(route))throw Error('单输出路线必须与任务路线一致');
   }else assertCompleteOutputSet(task,routes,{python:qualityPython});
   const old=jobs.find(job=>job.key===task.key||job.candidateImportKey===task.key);
   let added,reusedLegacy=false;
   if(!old){
    const conflicts=jobs.filter(job=>job.articleId===task.articleId&&job.figureNumber===task.figureNumber);
    if(conflicts.length){
     const legacy=conflicts[0],legacyKey=`${batchHash}:${task.articleId}:${task.figureNumber}`;
     const reusableOutputs=Array.isArray(legacy.outputNumbers)&&(
      legacy.outputNumbers.length===1&&legacy.outputNumbers[0]===legacy.figureNumber||
      JSON.stringify(legacy.outputNumbers)===JSON.stringify(task.outputNumbers));
     const hasLegacyRoute=Boolean(legacy.productionRoute);
     const legacySourcesMatch=['archive','word'].every(key=>legacy.sources?.some(source=>sameRef(source,route.sourceReview?.[key])));
     const legacyRouteMatches=existingPdf
      ? !legacy.outputRoutes&&!legacy.outputSetEvidence&&legacySourcesMatch
      : hasLegacyRoute
       ? legacy.productionRoute.method==='raster-preserve'&&['archive','word'].every(key=>sameRef(legacy.productionRoute.sourceReview?.[key],route.sourceReview?.[key])&&legacySourcesMatch)
       : !legacy.outputRoutes&&!legacy.outputSetEvidence&&legacySourcesMatch&&JSON.stringify(legacy.outputNumbers)===JSON.stringify(task.outputNumbers);
     const reusable=conflicts.length===1&&legacy.id&&legacy.key===legacyKey&&legacy.group===task.group&&legacy.state==='paused'&&legacy.attempt===0&&
      (!legacy.kind||legacy.kind==='production')&&!legacy.executionMode&&!legacy.attemptDir&&!legacy.lease&&!legacy.result&&!legacy.candidateResult&&
      !legacy.approved&&!legacy.accepted&&!legacy.userAcceptance&&!hasFeedback(legacy.feedback)&&!legacy.feedbackRevision&&!legacy.revisionHistory?.length&&
      !legacy.qualityVerification&&!legacy.publicationState&&reusableOutputs&&Array.isArray(legacy.sources)&&legacyRouteMatches&&
      Array.isArray(legacy.mainNumbers)&&JSON.stringify(legacy.mainNumbers)===JSON.stringify(task.mainNumbers);
     if(!reusable)throw Error('已有同图任务，不能重复导入或覆盖');
     for(const source of legacy.sources)if(digest(source.path)!==source.sha256)throw Error('暂停旧任务来源已变化，不能安全重用');
     const anchors=assertRoutineEligible(structuredClone(task),structuredClone(route));
     if(!anchors||anchors.then||!['archive','word'].every(key=>sameRef(anchors[key],route.sourceReview[key])&&task.sources.some(source=>sameRef(source,anchors[key]))))throw Error('暂停旧任务须经权威状态核验确认无反馈、无输出且原包及Word身份一致');
     assertProductionRoute(task);
     for(const source of task.sources)if(digest(source.path)!==source.sha256)throw Error('候选导入来源哈希变化');
     const prior={kind:'paused-legacy-import',key:legacy.key,figureId:legacy.figureId??null,mainNumbers:legacy.mainNumbers,outputNumbers:legacy.outputNumbers,
      outputRoutes:legacy.outputRoutes??null,outputSetEvidence:legacy.outputSetEvidence??null,productionRoute:legacy.productionRoute??null,instructions:legacy.instructions,sources:legacy.sources};
     Object.assign(legacy,{label:task.label,group:task.group,articleId:task.articleId,figureId:task.figureId,figureNumber:task.figureNumber,mainNumbers:task.mainNumbers,
      outputNumbers:task.outputNumbers,outputRoutes:task.outputRoutes,outputSetEvidence:task.outputSetEvidence,batchHash:task.batchHash,productionRoute:task.productionRoute,
      sources:[...new Map([...legacy.sources,...task.sources].map(source=>[path.resolve(source.path),source])).values()],sourceEvidence:task.sourceEvidence,articleEvidence:task.articleEvidence,
      candidateImportKey:task.key,directPrevious:prior});
     added=legacy;reusedLegacy=true;
    }else{
     const anchors=assertRoutineEligible(structuredClone(task),structuredClone(route));
     if(!anchors||anchors.then||!['archive','word'].every(key=>sameRef(anchors[key],route.sourceReview?.[key])&&task.sources.some(source=>sameRef(source,anchors[key]))))throw Error('权威来源及当前反馈检查未确认原包和Word');
     assertProductionRoute(task);
     for(const source of task.sources)if(digest(source.path)!==source.sha256)throw Error('候选导入来源哈希变化');
     added=this.enqueue(task);
    }
   }
   if(old){
    if(JSON.stringify(old.productionRoute)!==JSON.stringify(route)||JSON.stringify(old.outputNumbers)!==JSON.stringify(task.outputNumbers)||JSON.stringify(old.outputRoutes)!==JSON.stringify(task.outputRoutes)||old.outputSetEvidence?.sha256!==task.outputSetEvidence?.sha256)throw Error('同图已有候选导入任务，路线或输出集合不同');
    if(existingPdf){
     if(old.existingPdf?.manifestSha256!==importedManifest.sha256)throw Error('同图既有PDF候选版本不同，不能覆盖');
     if(old.state==='running'&&old.executionMode==='imported-pdf')return {resumed:true,job:structuredClone(old)};
     if(old.state==='ready'&&old.result&&old.qualityVerification?.kind==='automatic-candidate'&&old.qualityVerification.manualStatus==='pending'){
      if(old.publicationState!=='published'){
       if(publicationState==='applied'){old.publicationState='published';event(old,'工作台图件哈希与既有PDF候选一致，恢复登记状态；仍待用户终审');}
       else if(publicationState==='empty'){await publish(old,old.result);old.publicationState='published';event(old,'已恢复登记既有PDF候选；仍待用户终审');}
       else throw Error('工作台当前图件状态不能证明可安全恢复PDF候选登记');
      }
      return {alreadyReturned:true,job:structuredClone(old)};
     }
     throw Error('该既有PDF导入任务已进入其他状态，不能重复准备或覆盖');
    }
    if(old.state==='ready'&&old.result){
     const receipt=old.qualityVerification;
     if(receipt?.kind!=='automatic-candidate'||receipt.manualStatus!=='pending'||!Array.isArray(old.result.outputs)||old.result.outputs.length!==task.outputNumbers.length||old.result.outputs.some(output=>!task.outputNumbers.includes(output.number)||digest(output.path)!==output.sha256))throw Error('已有回传候选或自动核验回执已变化');
     if(old.publicationState!=='published'){
      if(publicationState==='applied'){old.publicationState='published';event(old,'服务端状态已与持久化完整候选哈希一致，恢复登记标记；仍待用户终审');}
      else if(publicationState==='empty'){await publish(old,old.result);old.publicationState='published';event(old,'已重试原子登记持久化候选；仍待用户终审');}
      else throw Error('服务端当前图件状态未通过精确哈希核对，不能恢复发布');
     }
     return {alreadyReturned:true,job:structuredClone(old)};
    }
    return this.prepareDirect(old.id,route,routes);
   }
   if(existingPdf)return {job:this.prepareImportedPdf(get(added.id),task,route,routes,importedManifest,importedOutputs)};
   const prepared=this.prepareDirect(added.id,route,routes);
   if(task.outputNumbers.length>1){
    const evidencePath=path.join(prepared.job.attemptDir,'output-set-evidence.json');
    if(fs.existsSync(evidencePath)){if(digest(evidencePath)!==task.outputSetEvidence.sha256)throw Error('既有输出集合快照哈希变化');}
    else fs.copyFileSync(task.outputSetEvidence.path,evidencePath,fs.constants.COPYFILE_EXCL);
    const stored=get(added.id),evidence={path:evidencePath,sha256:digest(evidencePath)};
    stored.outputSetEvidence=evidence;
    stored.sources=[...new Map([...stored.sources,evidence].map(source=>[path.resolve(source.path),source])).values()];
    atomicJson(path.join(stored.attemptDir,'task.json'),stored);save(stored);
   }
   event(get(added.id),reusedLegacy?'受控候选导入：安全复用暂停的零尝试旧任务；保留旧任务身份及路线历史，按完整Word输出集合创建新隔离attempt':'受控候选导入：原始候选不覆盖；新隔离attempt将按公共计划重放并独立自动核验');
   return {...prepared,job:structuredClone(get(added.id))};
  },
  retryImportedPdf(id,attempt,widths,replacementManifest){
   const job=get(id);
   if(!directProduction?.enabled||job.executionMode!=='imported-pdf'||!['running','failed'].includes(job.state)||job.attempt!==attempt||completing.has(id)||job.result||job.candidateResult||job.approved||job.accepted||hasFeedback(job.feedback)||job.feedbackRevision||job.revisionHistory?.length)throw Error('既有PDF重试已失效或已有候选/反馈');
   if(fs.existsSync(path.join(job.attemptDir,'.direct-run.lock')))throw Error('旧尝试仍有执行锁，不能重试');
   if(!widths||Object.keys(widths).length!==job.outputNumbers.length||job.outputNumbers.some(n=>!Object.hasOwn(widths,n)))throw Error('重试须提供完整输出宽度');
   const task=structuredClone(job),routes=task.outputRoutes;
   for(const entry of routes){
    const width=widths[entry.number],old=entry.productionRoute.requirements.widthMm;
    if(!Number.isFinite(width)||width<=0||width>old)throw Error('重试只能缩小至已验证PDF的实际宽度');
    entry.productionRoute.requirements.widthMm=width;
   }
   task.productionRoute=routes[0].productionRoute;
   let manifest=job.importOrigins.manifest,outputs=job.importOrigins.outputs;
   if(replacementManifest){
    if(!/^[a-f0-9]{64}$/.test(replacementManifest.sha256||'')||digest(replacementManifest.path)!==replacementManifest.sha256)throw Error('新候选清单哈希不符');
    const value=JSON.parse(fs.readFileSync(replacementManifest.path,'utf8'));
    if(value.version!==1||value.articleId!==job.articleId||String(value.figureNumber)!==String(job.figureNumber)||!Array.isArray(value.outputs)||value.outputs.length!==job.outputNumbers.length)throw Error('新候选清单身份或输出集合不符');
    const numbers=new Set();
    outputs=value.outputs.map(output=>{
     if(typeof output.number!=='string'||!job.outputNumbers.includes(output.number)||numbers.has(output.number)||!output.path||path.extname(output.path).toLowerCase()!=='.pdf'||digest(output.path)!==output.sha256)throw Error('新候选输出图号或哈希不符');
     numbers.add(output.number);return {number:output.number,source:{path:path.resolve(output.path),sha256:output.sha256}};
    });
    manifest={path:path.resolve(replacementManifest.path),sha256:replacementManifest.sha256};
   }
   return this.prepareImportedPdf(job,task,task.productionRoute,routes,manifest,outputs,{retry:true});
  },
  prepareImportedPdf(job,task,route,routes,manifest,outputs,{retry=false}={}){
   if(!retry&&job.executionMode==='imported-pdf'&&job.state==='running')return structuredClone(job);
   if(!retry&&(!['paused','queued'].includes(job.state)||job.attempt!==0||job.result||job.candidateResult||job.approved||job.accepted||hasFeedback(job.feedback)||job.feedbackRevision||job.revisionHistory?.length))throw Error('既有PDF只能导入到未执行且无反馈的任务');
   if(route.method!=='editable-pdf')throw Error('既有PDF只能绑定可编辑PDF路线');
   assertProductionRoute(task);assertOutputRoutes(task,routes);
   const anchors=assertRoutineEligible(structuredClone(task),structuredClone(route));
   if(!anchors||anchors.then||!['archive','word'].every(key=>sameRef(anchors[key],route.sourceReview[key])&&task.sources.some(source=>sameRef(source,anchors[key]))))throw Error('既有PDF导入未通过权威原包及Word身份核对');
   for(const source of task.sources)if(digest(source.path)!==source.sha256)throw Error('既有PDF导入来源哈希已变化');
   const previous=job.state==='paused'?{kind:'paused-legacy-import',key:job.key,productionRoute:job.productionRoute||null,instructions:job.instructions,outputNumbers:job.outputNumbers||[],sources:job.sources||[]}:null;
   if(digest(manifest.path)!==manifest.sha256||outputs.some(output=>digest(output.source.path)!==output.source.sha256))throw Error('既有PDF来源或清单哈希已变化');
   const attempt=retry?job.attempt+1:1,attemptDir=path.join(root,job.id,String(attempt)),candidateDir=path.join(attemptDir,'imported-pdf');
   fs.mkdirSync(candidateDir,{recursive:true});
   try{
    const manifestPath=path.join(candidateDir,'origin-manifest.json');fs.copyFileSync(manifest.path,manifestPath,fs.constants.COPYFILE_EXCL);
    if(digest(manifestPath)!==manifest.sha256)throw Error('既有PDF候选清单复制后哈希不符');
    const staged=[];
    for(const [index,output] of outputs.entries()){
     const target=path.join(candidateDir,`candidate-${index+1}.pdf`);fs.copyFileSync(output.source.path,target,fs.constants.COPYFILE_EXCL);
     if(digest(target)!==output.source.sha256)throw Error('既有PDF候选复制后哈希不符');
     staged.push({number:output.number,source:output.source,staged:{path:target,sha256:digest(target)}});
    }
    const routeRefs=routes.flatMap(entry=>routeSourceRefs(entry.productionRoute));
    Object.assign(job,{...task,existingPdf:{manifestSha256:manifest.sha256,manifest:{path:manifestPath,sha256:digest(manifestPath)},outputs:staged},importOrigins:{manifest,outputs},directPrevious:previous||job.directPrevious,
     sources:[...new Map([...routeRefs,{path:manifestPath,sha256:digest(manifestPath)},...staged.map(output=>output.staged)].map(source=>[path.resolve(source.path),source])).values()],attempt,attemptDir,executionMode:'imported-pdf',returnMode:'automatic-candidate',state:'running',pauseRequested:false});
    atomicJson(path.join(attemptDir,'task.json'),job);event(job,'既有PDF已复制至独立尝试；等待预检task-quality契约及自动核验');return structuredClone(job);
   }catch(error){job.attempt=attempt;job.attemptDir=attemptDir;job.state='failed';job.executionMode='imported-pdf';event(job,'既有PDF隔离副本准备失败：'+error.message);throw error;}
  },
  async submitImportedPdf(id,attempt,input){
   const job=get(id);
   if(!directProduction?.enabled||job.executionMode!=='imported-pdf'||job.state!=='running'||job.attempt!==attempt||completing.has(id))throw Error('既有PDF候选导入尝试已失效');
   completing.add(id);
   try{
    for(const source of job.sources)if(digest(source.path)!==source.sha256)throw Error('导入尝试来源已变化，不能回传');
    const checked=verifyImportedPdfCandidate(job,input,{python:qualityPython}),candidate=checked.result;
    inspectCandidate(job,candidate);
    if(job.outputNumbers.some(number=>!candidate.outputs.some(output=>output.number===number)))throw Error('导入PDF回传未覆盖完整输出集合');
    const current=assertRoutineEligible(structuredClone(job),structuredClone(job.productionRoute));
    if(!current||current.then||!['archive','word'].every(key=>sameRef(current[key],job.productionRoute.sourceReview[key])))throw Error('回传前权威原包及Word身份已变化');
    job.qualityVerification=checked.qualityVerification;
    atomicJson(path.join(job.attemptDir,'result.json'),candidate);job.result=candidate;job.state='ready';job.publicationState='pending';delete job.lease;
    event(job,'既有PDF候选机械检查通过，等待工作台登记及用户终审；未自动验收');
    await publish(job,candidate);job.publicationState='published';event(job,'既有PDF候选已登记，仍待用户终审；未自动验收');
    return structuredClone(job);
   }catch(error){
    if(job.state==='ready'&&job.result){job.publicationState='pending';event(job,'既有PDF候选自动核验已持久化；登记待恢复：'+error.message);throw error;}
    atomicJson(path.join(job.attemptDir,'candidate-error.json'),{at:new Date(now()).toISOString(),error:error.message});job.state='failed';delete job.lease;event(job,'既有PDF候选自动核验阻断：'+error.message);throw error;
   }finally{completing.delete(id);}
  },
  submitDirect(id,attempt,result){
   const j=get(id);
   if(!directProduction?.enabled||j.executionMode!=='direct'||j.state!=='running'||j.attempt!==attempt||completing.has(id))throw Error('直接制作尝试失效或正在回传');
   if(j.priorCandidateResult){const prior=j.priorCandidateResult.outputs;if(!Array.isArray(result.outputs)||result.outputs.length!==prior.length||result.outputs.some(o=>!prior.some(p=>p.number===o.number&&p.sha256===o.sha256)))throw Error('重放结果与原候选哈希不一致');}
   return submitAutomatic(j,structuredClone(result));
  },
  failDirect(id,attempt,message){
   const j=get(id);if(j.executionMode!=='direct'||j.state!=='running'||j.attempt!==attempt||completing.has(id))throw Error('直接制作尝试失效');
   j.state='failed';event(j,message);
  },
  list(){expire();return jobs.map(({lease,...j})=>structuredClone(j));},
  worker:()=>worker&&{...worker,online:now()-worker.seenAt<120000},
  routineOptions(){
   const enabled=!!trialEnabled(),used=enabled?trialUsed():0;
   const options={enabled,trialId:enabled?routineTrial.id:null,remaining:enabled?Math.max(0,routineTrial.maxTasks-used):0,status:!enabled?'tool_blocked':used>=routineTrial.maxTasks?'trial_complete':'awaiting_selection',reason:!enabled?'工具阻塞：常规图自主恢复入口未获授权或缺少权威状态检查':used>=routineTrial.maxTasks?'本次自主试运行累计名额已满，不再恢复任务':'待自主选任务：核对现有暂停图件并提交来源绑定路线；无需循环空领',action:'resume-routine <job-id> <productionRoute.json>',paused:jobs.filter(j=>j.state==='paused').map(j=>{
    try{routineEligibility(j);return {id:j.id,label:j.label,group:j.group,eligible:used<routineTrial.maxTasks,reason:used<routineTrial.maxTasks?'自行核对来源并提交路线后可恢复':'本次试运行名额已用完',articleId:j.articleId,figureNumber:j.figureNumber,outputNumbers:j.outputNumbers,sources:j.sources,sourceEvidence:j.sourceEvidence,articleEvidence:j.articleEvidence};}
    catch(error){return {id:j.id,label:j.label,group:j.group,eligible:false,reason:error.message};}
   })};
   if(enabled&&used<routineTrial.maxTasks&&!options.paused.some(j=>j.eligible)){options.status='tool_blocked';options.reason='工具阻塞：当前授权范围内没有可自主恢复的未生产常规图，请查看逐项暂停原因；不扩大范围或循环空领';}
   return options;
  },
  resumeRoutine(id,productionRoute){
   if(directProduction?.enabled)throw Error('已使用直接制作，无需逐图恢复');
   const j=get(id);routineEligibility(j,productionRoute);
   if(trialUsed()>=routineTrial.maxTasks)throw Error('本次常规图试运行累计名额已用完');
   const record={id:j.id,at:new Date(now()).toISOString(),previousInstructions:j.instructions,previousRoute:j.productionRoute||null};
   // Reserve first: an interrupted write consumes a slot rather than exceeding authorization.
   trials[routineTrial.id]=[...(trials[routineTrial.id]||[]),record];atomicJson(trialFile,trials);
   j.routineTrialId=routineTrial.id;j.productionRoute=structuredClone(productionRoute);j.instructions=productionInstructions(productionRoute);
   j.sources=[...new Map([...j.sources,...routeSourceRefs(productionRoute)].map(s=>[path.resolve(s.path),s])).values()];
   j.state='queued';j.pauseRequested=false;event(j,`试运行 ${routineTrial.id}：执行器自主核对常规位图路线后恢复原任务；未开始制作、未验收`);
   return structuredClone(j);
  },
  retryRoutine(id,lease){
   const j=get(id),limit=Math.min(3,Math.max(1,routineTrial?.maxAttempts||3));
   if(!automaticTrial(j)||!automatic(j)||j.state!=='failed'||completing.has(id)||!lease||j.retryLeaseHash!==leaseHash(lease)||j.accepted||j.approved||j.result)throw Error('仅原执行器可重试本轮已停止且未批准的失败任务');
   if(j.attempt>=limit)throw Error('本轮同任务尝试次数已达上限，需报告工具问题');
   assertRouteEditable(j,j.productionRoute);assertRoutineEligible(structuredClone(j),structuredClone(j.productionRoute));
   if(jobs.some(other=>other.id!==j.id&&other.articleId===j.articleId&&other.figureNumber===j.figureNumber&&(other.state!=='paused'||other.attempt>0||other.result)))throw Error('同图已有其他任务，不能重复执行');
   dispatchInstructions(j);for(const source of j.sources)if(digest(source.path)!==source.sha256)throw Error('来源已变化，不能自主重试');
   j.state='queued';j.pauseRequested=false;delete j.retryLeaseHash;event(j,`试运行 ${routineTrial.id}：原执行器重试同任务，将使用新尝试目录并保留旧候选`);
   return structuredClone(j);
  },
  enqueue(input){
   if(input.kind!=='inventory')input={...input,instructions:dispatchInstructions(input),executionProtocol:'instructions 是由 productionRoute 生成的唯一格式、字号范围与尺寸要求。必须逐项读取 feedback（含位置批注及截图）、coordinatorDecision 和 revisionNotes 的真实修订要求，读取 sourceEvidence/articleEvidence 的来源事实。既有明确用户约束不可覆盖；常规来源核对后可通过当前租约 prepare-route 更新制作路线（不更换文章来源身份），以返回的 task.json 冻结质量证据。未知含义或工具缺陷回报，不丢弃原始批注。使用公共工具，候选送独立复核后待用户终审，不自动验收。'};
   const old=jobs.findLast(j=>j.key===input.key);if(old)return {...old,lease:undefined};
   for(const s of input.sources)if(digest(s.path)!==s.sha256)throw Error('任务源件已变化，需要重新核对');
   const j={id:randomUUID(),...structuredClone(input),executor:typeof input.executor==='string'&&input.executor.trim()?input.executor.trim().slice(0,100):'WorkBuddy',state:'queued',attempt:0,createdAt:new Date(now()).toISOString()};
   fs.mkdirSync(path.join(root,j.id));jobs.push(j);event(j,'工作台已派单，等待执行器领取');return {...j};
  },
  claim(session,batchHash){
   if(directProduction?.enabled)return null;
   expire();worker={session:String(session).slice(0,100),seenAt:now()};
   if(jobs.some(j=>['running','pausing','interrupted'].includes(j.state)&&j.lease))return null;
   // Group by verified kind/method; article is an identity, never a scheduling bucket.
   let j,instructions;
   for(const candidate of jobs.filter(j=>j.state==='queued'&&belongsToBatch(j,batchHash)).sort((a,b)=>(a.priority??10)-(b.priority??10)||a.group.localeCompare(b.group)||a.createdAt.localeCompare(b.createdAt))){
    try{if(candidate.kind!=='inventory')instructions=dispatchInstructions(candidate);j=candidate;break;}
    catch(error){candidate.state='needs_input';event(candidate,'派单前路线检查阻断：'+error.message);}
   }
   if(!j)return null;
   for(const s of j.sources)if(digest(s.path)!==s.sha256){j.state='failed';event(j,'源件哈希变化，领取已阻止');return null;}
   if(j.kind!=='inventory'&&j.instructions!==instructions){
    j.previousGeneratedInstructions??=j.instructions;
    j.instructions=instructions;
   }
   j.returnMode=automatic(j)?'automatic-candidate':'independent-review';
   j.attempt++;j.state='running';j.session=session;j.lease=randomUUID();j.heartbeatAt=now();j.attemptDir=path.join(root,j.id,String(j.attempt));fs.mkdirSync(j.attemptDir,{recursive:true});event(j,'执行器已领取（'+j.executor+'）：'+j.group);return structuredClone(j);
  },
  heartbeat(id,lease){const j=claimed(id,lease);j.heartbeatAt=now();worker={session:j.session,seenAt:now()};save(j);return {pauseRequested:j.state==='pausing'};},
  progress(id,lease,message){const j=claimed(id,lease);j.heartbeatAt=now();event(j,message);},
  prepareRoute(id,lease,productionRoute){
   const j=get(id);
   if(j.state!=='running'||!lease||lease!==j.lease||j.pauseRequested||completing.has(id)||j.kind==='inventory'||j.accepted===true||j.approved===true)throw Error('仅当前运行且未批准的制作任务可准备路线');
   if(routeSealed(j.attemptDir))throw Error('本次尝试已预检或封存，不能再修改路线；失败后使用新尝试目录');
   const previous=assertProductionRoute(j),next=assertProductionRoute({...j,productionRoute});
   assertRouteEditable(j,next);
   for(const key of ['archive','word','inventory']){
    const a=previous.sourceReview[key],b=next.sourceReview[key];
    if(path.resolve(a.path)!==path.resolve(b.path)||a.sha256!==b.sha256)throw Error('不能更换本任务绑定的原包、Word或来源清单');
   }
   for(const source of j.sources)if(digest(source.path)!==source.sha256)throw Error('任务来源已变化，不能准备路线');
   const version=(j.routeHistory?.length||0)+1;
   const record={version,at:new Date(now()).toISOString(),attempt:j.attempt,previous:structuredClone(previous),productionRoute:structuredClone(next)};
   atomicJson(path.join(j.attemptDir,`route-${version}.json`),record);
   j.routeHistory=[...(j.routeHistory||[]),record];j.productionRoute=structuredClone(next);j.instructions=productionInstructions(next);
   j.sources=[...new Map([...j.sources,...routeSourceRefs(next)].map(s=>[path.resolve(s.path),s])).values()];
   j.heartbeatAt=now();event(j,'执行器已完成来源核对并准备路线；产物仍须独立质量核验');
   const {lease:privateLease,...task}=j;atomicJson(path.join(j.attemptDir,'task.json'),task);return structuredClone(task);
  },
  pause(id){const j=get(id);if(!['queued','running','interrupted'].includes(j.state))throw Error('当前任务不能暂停');j.pauseRequested=true;j.state=j.state==='queued'?'paused':'pausing';event(j,j.state==='pausing'?'请求安全暂停，等待 WorkBuddy 完成当前工具调用并保存进度':'已暂停，不会被领取');},
  acknowledgePause(id,lease){const j=claimed(id,lease);if(j.state!=='pausing')throw Error('未请求暂停');j.state='paused';delete j.lease;event(j,'WorkBuddy 已保存进度并暂停');},
  resume(id){const j=get(id);if(j.state!=='paused')throw Error('当前任务不处于暂停状态');j.state='queued';j.pauseRequested=false;event(j,'已继续：重新领取后复用上次候选和进度');},
  revisePlan(id,plan,confirmedStopped=false){const j=get(id);if(!['failed','needs_input','interrupted','paused'].includes(j.state)||j.state==='interrupted'&&!confirmedStopped)throw Error('执行中、未确认停止或已完成的任务不能改计划');const route=plan.productionRoute||j.productionRoute;assertProductionRoute({...j,productionRoute:route});j.productionRoute=structuredClone(route);j.instructions=productionInstructions(route);j.revisionNotes=plan.instructions;j.coordinatorDecision=structuredClone(plan.decision);event(j,'ChatGPT 已核对失败原因并更新执行说明');},
  retry(id,confirmedStopped){const j=get(id);if(!['failed','interrupted','needs_input'].includes(j.state))throw Error('当前任务不能重试');if(j.state==='interrupted'&&!confirmedStopped)throw Error('请先确认旧 WorkBuddy 任务已停止，避免重复执行');j.state='queued';j.pauseRequested=false;delete j.lease;event(j,'重试已排队，保留此前日志和候选');},
  fail(id,lease,message,needsInput=false){const j=claimed(id,lease);if(completing.has(id))throw Error('候选正在回传，不能同时修改状态');j.state=needsInput?'needs_input':'failed';if(automatic(j)&&!needsInput)j.retryLeaseHash=leaseHash(lease);delete j.lease;event(j,message);},
  submitCandidate(id,lease,result){
   const j=claimed(id,lease);if(completing.has(id))throw Error('本任务正在回传，请等待结果');
   if(automatic(j))return submitAutomatic(j,structuredClone(result),lease);
   const candidate=structuredClone(result);inspectCandidate(j,candidate);
   atomicJson(path.join(j.attemptDir,'candidate-submission.json'),candidate);j.candidateResult=candidate;j.state='review_pending';delete j.lease;
   event(j,'候选已提交，等待独立内部复核；未回传终审、未验收');
  },
  rejectCandidate(id,reason){
   const j=get(id);if(j.state!=='review_pending'||!j.candidateResult||completing.has(id))throw Error('当前候选不允许退回');
   if(typeof reason!=='string'||!reason.trim())throw Error('独立复核退回须填写原因');
   const review={decision:'rejected',reason,at:new Date(now()).toISOString(),attempt:j.attempt};
   atomicJson(path.join(j.attemptDir,'review-rejection.json'),review);
   j.reviewRejections=[...(j.reviewRejections||[]),review];j.state='needs_input';event(j,'独立复核退回：'+reason);
  },
  async reviewCandidate(id,result){
   const j=get(id);if(j.state!=='review_pending'||!j.candidateResult)throw Error('当前任务没有待内部复核候选');
   if(completing.has(id))throw Error('本任务正在复核，请等待结果');completing.add(id);
   try{
    const reviewed=structuredClone(result),submitted=j.candidateResult.outputs;
    if(!Array.isArray(reviewed.outputs)||reviewed.outputs.length!==submitted.length||reviewed.outputs.some(o=>!submitted.some(s=>s.number===o.number&&path.resolve(s.path)===path.resolve(j.attemptDir,o.path)&&s.sha256===o.sha256)))throw Error('复核结果必须绑定已提交候选，不能替换图件');
    inspectCandidate(j,reviewed);await publishReviewed(j,reviewed);
   }finally{completing.delete(id);}
  },
  async complete(id,lease,result){
   const j=claimed(id,lease);
   if(completing.has(id))throw Error('本任务正在回传，请等待结果');
   completing.add(id);
   try{
   for(const s of j.sources)if(digest(s.path)!==s.sha256)throw Error('源件已变更，不能回传');
   if(j.kind==='inventory'){
    if(!result.evidence?.trim()||!Array.isArray(result.articles))throw Error('缺少来源核对与分组清单');
    await publish(j,result);j.result=result;
    const blocked=result.articles.flatMap(p=>p.blocked?[`${p.articleId}：${p.problem}`]:(p.figures||[]).filter(f=>f.blocked).map(f=>`${p.articleId} 图${f.number}：${f.problem}`));
    j.state=blocked.length?'needs_input':'ready';delete j.lease;
    event(j,blocked.length?'已派发可处理图件；以下项目待补充，补齐后重试本次核对：\n'+blocked.join('\n'):'图源与图种清单已回传，按处理方式派单');return;
   }
   inspectCandidate(j,result);await publishReviewed(j,result);
   }finally{completing.delete(id);}
  },
  events(id){get(id);const file=path.join(root,id,'events.jsonl'),size=fs.statSync(file).size,fd=fs.openSync(file,'r'),bytes=Buffer.alloc(Math.min(size,256*1024));try{fs.readSync(fd,bytes,0,bytes.length,size-bytes.length);}finally{fs.closeSync(fd);}return bytes.toString('utf8').split('\n').filter(Boolean).slice(-150).flatMap(line=>{try{return [JSON.parse(line)];}catch{return [];}});}
 };
}
