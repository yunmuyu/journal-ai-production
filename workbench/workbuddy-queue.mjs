import {dispatchInstructions} from './production-dispatch.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {atomicJson} from './revision-jobs.mjs';
import {digest,checkedArtifact} from './revision-worker.mjs';
import {assertProductionRoute,productionInstructions,verifyProductionResult,routeSourceRefs} from './production-route.mjs';
export function createWorkBuddyQueue({root,publish,now=()=>Date.now(),qualityPython,verifyQuality=verifyProductionResult,assertRouteEditable=()=>{},routineTrial,assertRoutineEligible}){
 fs.mkdirSync(root,{recursive:true});
 const jobs=fs.readdirSync(root).filter(n=>/^[a-f0-9-]{36}$/.test(n)).map(id=>JSON.parse(fs.readFileSync(path.join(root,id,'job.json'),'utf8')));
 let worker=null;
 const completing=new Set();
 const save=j=>{j.updatedAt=new Date(now()).toISOString();atomicJson(path.join(root,j.id,'job.json'),j);};
 const event=(j,message)=>{fs.appendFileSync(path.join(root,j.id,'events.jsonl'),JSON.stringify({at:new Date(now()).toISOString(),message:String(message).slice(0,16000)})+'\n');j.message=String(message).slice(0,250);save(j);};
 const get=id=>{const j=jobs.find(j=>j.id===id);if(!j)throw Error('任务不存在');return j;};
 const trialFile=path.join(root,'routine-trials.json');
 const trials=fs.existsSync(trialFile)?JSON.parse(fs.readFileSync(trialFile,'utf8')):{};
 const trialEnabled=()=>routineTrial&&typeof routineTrial.id==='string'&&/^[a-zA-Z0-9_-]{1,80}$/.test(routineTrial.id)&&Number.isInteger(routineTrial.maxTasks)&&routineTrial.maxTasks>0&&routineTrial.maxTasks<=3&&Array.isArray(routineTrial.groups)&&routineTrial.groups.length>0&&typeof assertRoutineEligible==='function';
 const trialUsed=()=>new Set([...(trials[routineTrial?.id]||[]).map(r=>r.id),...jobs.filter(j=>j.routineTrialId===routineTrial?.id&&j.routineTrialId).map(j=>j.id)]).size;
 const sameRef=(a,b)=>a&&b&&path.resolve(a.path)===path.resolve(b.path)&&a.sha256===b.sha256;
 function routineEligibility(j,route=null){
  if(!trialEnabled())throw Error('未启用常规图试运行授权及权威状态检查');
  if(j.state!=='paused'||j.attempt!==0||j.kind&&j.kind!=='production'||j.result||j.candidateResult||j.accepted||j.approved||j.feedback?.text?.trim()||j.feedback?.points?.length||j.feedback?.attachments?.length||j.feedbackRevision||j.revisionHistory?.length)throw Error('仅未生产、无反馈且未批准的暂停常规图可自主恢复');
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
 function expire(){for(const j of jobs)if(['running','pausing'].includes(j.state)&&now()-j.heartbeatAt>120000){j.state='interrupted';event(j,'超过2分钟没有进度心跳，执行状态待核实；原会话可续接，不自动重做');}}
 function inspectCandidate(j,result){
  if(j.kind==='inventory')throw Error('来源清单不使用成图候选入口');
  const route=assertProductionRoute(j),raster=route.method==='raster-preserve';
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
 for(const j of jobs)if(['running','pausing'].includes(j.state)){j.state='interrupted';event(j,'工作台重启，等待原 WorkBuddy 会话续接；未启动重复制作');}
 return {
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
  enqueue(input){
   if(input.kind!=='inventory')input={...input,instructions:dispatchInstructions(input),executionProtocol:'instructions 是由 productionRoute 生成的唯一格式、字号范围与尺寸要求。必须逐项读取 feedback（含位置批注及截图）、coordinatorDecision 和 revisionNotes 的真实修订要求，读取 sourceEvidence/articleEvidence 的来源事实。既有明确用户约束不可覆盖；常规来源核对后可通过当前租约 prepare-route 更新制作路线（不更换文章来源身份），以返回的 task.json 冻结质量证据。未知含义或工具缺陷回报，不丢弃原始批注。使用公共工具，候选送独立复核后待用户终审，不自动验收。'};
   const old=jobs.findLast(j=>j.key===input.key);if(old)return {...old,lease:undefined};
   for(const s of input.sources)if(digest(s.path)!==s.sha256)throw Error('任务源件已变化，需要重新核对');
   const j={id:randomUUID(),...structuredClone(input),executor:typeof input.executor==='string'&&input.executor.trim()?input.executor.trim().slice(0,100):'WorkBuddy',state:'queued',attempt:0,createdAt:new Date(now()).toISOString()};
   fs.mkdirSync(path.join(root,j.id));jobs.push(j);event(j,'工作台已派单，等待执行器领取');return {...j};
  },
  claim(session){
   expire();worker={session:String(session).slice(0,100),seenAt:now()};
   if(jobs.some(j=>['running','pausing','interrupted'].includes(j.state)&&j.lease))return null;
   // Group by verified kind/method; article is an identity, never a scheduling bucket.
   let j;
   for(const candidate of jobs.filter(j=>j.state==='queued').sort((a,b)=>(a.priority??10)-(b.priority??10)||a.group.localeCompare(b.group)||a.createdAt.localeCompare(b.createdAt))){
    try{if(candidate.kind!=='inventory')dispatchInstructions(candidate);j=candidate;break;}
    catch(error){candidate.state='needs_input';event(candidate,'派单前路线检查阻断：'+error.message);}
   }
   if(!j)return null;
   for(const s of j.sources)if(digest(s.path)!==s.sha256){j.state='failed';event(j,'源件哈希变化，领取已阻止');return null;}
   j.attempt++;j.state='running';j.session=session;j.lease=randomUUID();j.heartbeatAt=now();j.attemptDir=path.join(root,j.id,String(j.attempt));fs.mkdirSync(j.attemptDir,{recursive:true});event(j,'执行器已领取（'+j.executor+'）：'+j.group);return structuredClone(j);
  },
  heartbeat(id,lease){const j=claimed(id,lease);j.heartbeatAt=now();worker={session:j.session,seenAt:now()};save(j);return {pauseRequested:j.state==='pausing'};},
  progress(id,lease,message){const j=claimed(id,lease);j.heartbeatAt=now();event(j,message);},
  prepareRoute(id,lease,productionRoute){
   const j=get(id);
   if(j.state!=='running'||!lease||lease!==j.lease||j.pauseRequested||completing.has(id)||j.kind==='inventory'||j.accepted===true||j.approved===true)throw Error('仅当前运行且未批准的制作任务可准备路线');
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
  fail(id,lease,message,needsInput=false){const j=claimed(id,lease);j.state=needsInput?'needs_input':'failed';delete j.lease;event(j,message);},
  submitCandidate(id,lease,result){
   const j=claimed(id,lease);if(completing.has(id))throw Error('本任务正在回传，请等待结果');
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
