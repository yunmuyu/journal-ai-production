import fs from 'node:fs';
import path from 'node:path';
import {randomUUID,timingSafeEqual} from 'node:crypto';
import {atomicJson} from './revision-jobs.mjs';
import {digest} from './revision-worker.mjs';

// A saved review is first a coordinator decision, never an implicit AI launch.
export function createReviewTriage({root,origin,token,queue,rows,articles,refresh,activate,legacyJobs=()=>[]}){
 fs.mkdirSync(root,{recursive:true});const file=path.join(root,'reviews.json');
 const records=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):[];
 const save=()=>atomicJson(file,records);
 const figure=id=>{refresh();const f=rows.find(f=>f.id===id);if(!f)throw Error('图件不存在');return f;};
 const view=r=>{const job=r.jobId&&queue.list().find(j=>j.id===r.jobId),failed=job&&['failed','needs_input'].includes(job.state);return {...r,state:failed?(r.state==='waiting_tools'?'waiting_tools':'needs_triage'):job?.state||r.state,message:failed?(r.state==='waiting_tools'?r.message:'执行问题已交 ChatGPT 排障：'+job.message):job?.message||r.message,executor:job&&!failed?'WorkBuddy':'ChatGPT'};};
 function assertAvailable(id,excludeJobId){
  if(legacyJobs().some(j=>j.figureId===id&&['queued','running','interrupted'].includes(j.state)))throw Error('旧执行器任务尚未收敛，不能重复派单');
  if(queue.list().some(j=>j.id!==excludeJobId&&(j.figureId===id||j.articleId+'-F'+j.figureNumber===id)&&['queued','running','pausing','paused','interrupted'].includes(j.state)))throw Error('此图已有执行任务，等待安全结束后处理');
 }
 function submit(id,version){
  const f=figure(id);if(f.reviewVersion!==version)throw Error('图稿或批注已变化，请刷新');
  if(f.status==='终检通过')throw Error('此版本已通过；请先新增终审意见，不能重跑已解决的旧批注');
  const feedback=f.feedback;if(!feedback||!(feedback.text?.trim()||feedback.attachments?.length||feedback.points?.length))throw Error('请先保存终审意见');
  const old=records.findLast(r=>r.figureId===id&&r.feedbackRevision===feedback.revision&&r.version===version);if(old)return view(old);
  assertAvailable(id);if(!f.outputs.length)throw Error('此图尚无可修订成稿');
  const word=articles.find(a=>a.id===f.articleId)?.word;
  const r={id:randomUUID(),figureId:id,articleId:f.articleId,author:f.author,number:f.number,feedbackRevision:feedback.revision,version,feedback:structuredClone(feedback),sources:[...f.outputs.map(o=>({path:o.file.path,sha256:digest(o.file.path)})),...(word?[{path:word.path,sha256:digest(word.path)}]:[])],outputNumbers:f.outputs.map(o=>o.number),state:'needs_triage',executor:'ChatGPT',message:'终审意见已交给 ChatGPT 分流，尚未启动制作',createdAt:new Date().toISOString()};
  records.push(r);save();return view(r);
 }
 function resolve(id,decision){
  const r=records.find(r=>r.id===id);if(!r)throw Error('终审事项不存在');
  const prior=r.jobId&&queue.list().find(j=>j.id===r.jobId);if(prior&&!['failed','needs_input','interrupted'].includes(prior.state))return view(r);
  if(prior?.state==='interrupted'&&decision.confirmedStopped!==true)throw Error('必须先核实旧 WorkBuddy 任务已停止；原会话仍可续接');
  const f=figure(r.figureId);if(f.reviewVersion!==r.version||f.feedback?.revision!==r.feedbackRevision)throw Error('图稿或批注已经更新，请重新核对');
  if(!['ordinary','tool_fix','mixed'].includes(decision.kind)||!decision.instructions?.trim())throw Error('缺少明确的分流及执行说明');
  r.decision=structuredClone(decision);
  if(decision.kind!=='ordinary'&&(!decision.toolResolved||!decision.toolCommit?.match(/^[a-f0-9]{7,40}$/)||!decision.tests?.trim())){r.state='waiting_tools';r.message='ChatGPT 处理中：公共工具修复完成并验证后，才交给 WorkBuddy 重跑';save();return view(r);}
  assertAvailable(r.figureId,prior?.id);
  if(prior){queue.revisePlan(prior.id,{instructions:decision.instructions+'\n按task.feedback逐项修订，使用公共工具，回传待终审。',decision},decision.confirmedStopped===true);queue.retry(prior.id,decision.confirmedStopped===true);r.state='queued';save();return view(r);}
  const job=queue.enqueue({key:`revision:${r.figureId}:${r.feedbackRevision}:${r.version}`,kind:'revision',priority:0,label:`${r.author} 图${r.number} · 终审修订`,group:'终审修订 / 已由 ChatGPT 分流',figureId:r.figureId,articleId:r.articleId,figureNumber:r.number,feedbackRevision:r.feedbackRevision,baseVersion:r.version,outputNumbers:r.outputNumbers,sources:r.sources,feedback:r.feedback,coordinatorDecision:r.decision,instructions:decision.instructions+'\n本次反馈：'+r.feedback.text+'\n必须逐项核对位置批注及截图（见task.feedback），保留源件。使用当前公共工具，不编写替代引擎。结果回传原图件，不能自动验收。'});
  r.jobId=job.id;r.state='queued';r.message='已交 WorkBuddy，等待领取';save();return view(r);
 }
 function publish(job,result){
  const f=figure(job.figureId);if(f.reviewVersion!==job.baseVersion||f.feedback?.revision!==job.feedbackRevision)throw Error('批注或图稿已更新；旧意见产物不能覆盖当前版本');
  activate({at:new Date().toISOString(),jobId:job.id,figureId:job.figureId,pendingKey:job.figureId,feedbackRevision:job.feedbackRevision,result});refresh();
 }
 // Legacy candidates are restored before this adapter; newer WorkBuddy revisions win.
 for(const j of queue.list().filter(j=>j.kind==='revision'&&j.state==='ready'&&j.result).sort((a,b)=>a.updatedAt.localeCompare(b.updatedAt)))activate({jobId:j.id,figureId:j.figureId,pendingKey:j.figureId,feedbackRevision:j.feedbackRevision,result:j.result});
 const json=(res,status,value)=>res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(value));
 return {submit,resolve,publish,list:()=>records.map(view),decorate(){for(const f of rows){const r=records.findLast(r=>r.figureId===f.id);if(r)f.revisionJob=r.feedbackRevision===f.feedback?.revision?view(r):null;f.revisionRoute='coordinator';}},handle(req,res,url){
  const resolution=url.pathname==='/review-triage/resolve';if(!resolution&&!url.pathname.startsWith('/revision-jobs'))return false;
  if(req.method==='GET'&&!resolution){json(res,200,{jobs:records.map(view),legacy:legacyJobs()});return true;}
  const a=Buffer.from(req.headers.authorization||''),b=Buffer.from('Bearer '+token);
  if(req.method!=='POST'||(resolution?!(a.length===b.length&&timingSafeEqual(a,b)):req.headers.origin!==origin)){json(res,403,{error:'请求来源未授权'});return true;}
  let size=0,chunks=[];req.on('data',c=>{size+=c.length;if(size<1024*1024)chunks.push(c);});req.on('end',()=>{try{
   if(size>=1024*1024)throw Error('请求过大');const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
   const job=resolution?resolve(body.id,body.decision):submit(decodeURIComponent(url.pathname.slice('/revision-jobs/'.length)),body.version);
   json(res,202,{job});
  }catch(e){json(res,409,{error:e.message});}});return true;
 }};
}
