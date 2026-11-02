import {catalogFor,belongsToBatch} from './batch-scope.mjs';
import {timingSafeEqual} from 'node:crypto';
import {digest} from './revision-worker.mjs';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
import {buildFigureTasks} from './workbuddy-plan.mjs';
import {summarizeProduction} from './workbuddy-summary.mjs';
export function createWorkBuddyHandler({root,origin,config,publish,restore,verifyQuality,verifyAutomatic,figures=()=>null,assertRouteEditable,assertRoutineEligible}){
 const queue=createWorkBuddyQueue({root,qualityPython:config.qualityPython,verifyQuality,verifyAutomatic,assertRouteEditable,routineTrial:config.routineTrial,assertRoutineEligible,automaticRasterBatches:config.automaticRasterBatches,publish(job,result){if(job.kind==='inventory'){const tasks=buildFigureTasks(catalogFor(config,job.batchHash),result);for(const task of tasks)for(const source of task.sources)if(digest(source.path)!==source.sha256)throw Error('分组来源已变更，未派发制作');for(const task of tasks)queue.enqueue(task);}else return publish(job,result);}});
 for(const j of queue.list().filter(j=>j.state==='ready'&&j.result&&!['inventory','revision'].includes(j.kind)).sort((a,b)=>(a.updatedAt||a.createdAt).localeCompare(b.updatedAt||b.createdAt)||a.id.localeCompare(b.id)))restore(j,j.result);
 const json=(res,status,value)=>res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(value));
 const authorized=(req,token)=>{if(typeof token!=='string'||!token.trim())return false;const a=Buffer.from(req.headers.authorization||''),b=Buffer.from('Bearer '+token);return a.length===b.length&&timingSafeEqual(a,b);};
 return {queue,handle(req,res,url){
  if(!url.pathname.startsWith('/workbuddy/'))return false;
  if(req.method==='GET'&&url.pathname==='/workbuddy/status'){const jobs=queue.list();json(res,200,{summary:summarizeProduction(jobs,figures()),jobs:jobs.map(({id,key,label,group,state,attempt,message,kind,createdAt,updatedAt,executor,articleId,figureId,figureNumber})=>({id,key,label,group,state,attempt,message,kind,createdAt,updatedAt,executor,articleId,figureId,figureNumber})),worker:queue.worker(),pilot:config.pilot?{key:config.pilot.key,label:config.pilot.label,group:config.pilot.group}:null,inventoryAvailable:!!config.inventory});return true;}
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
    if(action==='claim'){
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
    if(body.action==='retry'&&queue.list().some(j=>j.id===body.id&&j.kind==='revision'))throw Error('终审修订须先由 ChatGPT 排障并更新执行说明，不能直接重跑旧计划');
    if(body.action==='pause')queue.pause(body.id);else if(body.action==='resume')queue.resume(body.id);else if(body.action==='retry')queue.retry(body.id,body.confirmedStopped===true);else throw Error('未知控制操作');
   }else throw Error('未知入口');
   json(res,200,result);
  }catch(e){json(res,409,{error:e.message});}});return true;
 }};
}
