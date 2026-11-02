import {timingSafeEqual} from 'node:crypto';
import {digest} from './revision-worker.mjs';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
import {buildFigureTasks} from './workbuddy-plan.mjs';
export function createWorkBuddyHandler({root,origin,config,publish,restore}){
 const queue=createWorkBuddyQueue({root,publish(job,result){if(job.kind==='inventory'){const tasks=buildFigureTasks(config.catalog,result);for(const task of tasks)for(const source of task.sources)if(digest(source.path)!==source.sha256)throw Error('分组来源已变更，未派发制作');for(const task of tasks)queue.enqueue(task);}else return publish(job,result);}});
 for(const j of queue.list())if(j.state==='ready'&&j.result&&!['inventory','revision'].includes(j.kind))restore(j,j.result);
 const json=(res,status,value)=>res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(value));
 const authorized=req=>{const a=Buffer.from(req.headers.authorization||''),b=Buffer.from('Bearer '+config.workerToken);return a.length===b.length&&timingSafeEqual(a,b);};
 return {queue,handle(req,res,url){
  if(!url.pathname.startsWith('/workbuddy/'))return false;
  if(req.method==='GET'&&url.pathname==='/workbuddy/status'){json(res,200,{jobs:queue.list().map(({id,key,label,group,state,attempt,message,kind,updatedAt,executor})=>({id,key,label,group,state,attempt,message,kind,updatedAt,executor})),worker:queue.worker(),pilot:config.pilot?{key:config.pilot.key,label:config.pilot.label,group:config.pilot.group}:null,inventoryAvailable:!!config.inventory});return true;}
  if(req.method==='GET'&&url.pathname==='/workbuddy/events'){try{json(res,200,{events:queue.events(url.searchParams.get('id'))});}catch(e){json(res,404,{error:e.message});}return true;}
  const workerRoute=url.pathname==='/workbuddy/worker';
  if(req.method!=='POST'||(workerRoute?!authorized(req):req.headers.origin!==origin)){json(res,403,{error:'请求来源未授权'});return true;}
  let bytes=0,chunks=[];req.on('data',c=>{bytes+=c.length;if(bytes<1024*1024)chunks.push(c);});
  req.on('end',async()=>{try{
   if(bytes>=1024*1024)throw Error('请求过大');
   const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));let result={ok:true};
   if(workerRoute){
    const {action,id,lease}=body;
    if(action==='claim')result={job:queue.claim(body.session||'WorkBuddy')};
    else if(action==='heartbeat')result=queue.heartbeat(id,lease);
    else if(action==='progress')queue.progress(id,lease,body.message);
    else if(action==='paused')queue.acknowledgePause(id,lease);
    else if(action==='fail')queue.fail(id,lease,body.message,body.needsInput===true);
    else if(action==='complete')await queue.complete(id,lease,body.result);
    else throw Error('未知执行操作');
   }else if(url.pathname==='/workbuddy/start-pilot'){
    if(!config.pilot)throw Error('尚未配置已核对的试跑图件');result={job:queue.enqueue(config.pilot)};
   }else if(url.pathname==='/workbuddy/start-inventory'){
    if(!config.inventory||!queue.list().some(j=>j.key===config.pilot.key&&j.state==='ready'))throw Error('先完成单图试跑并回传，再进行本批图种分组');result={job:queue.enqueue(config.inventory)};
   }else if(url.pathname==='/workbuddy/control'){
    if(body.action==='retry'&&queue.list().some(j=>j.id===body.id&&j.kind==='revision'))throw Error('终审修订须先由 ChatGPT 排障并更新执行说明，不能直接重跑旧计划');
    if(body.action==='pause')queue.pause(body.id);else if(body.action==='resume')queue.resume(body.id);else if(body.action==='retry')queue.retry(body.id,body.confirmedStopped===true);else throw Error('未知控制操作');
   }else throw Error('未知入口');
   json(res,200,result);
  }catch(e){json(res,409,{error:e.message});}});return true;
 }};
}
