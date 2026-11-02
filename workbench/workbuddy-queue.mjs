import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {atomicJson} from './revision-jobs.mjs';
import {digest,checkedArtifact} from './revision-worker.mjs';
export function createWorkBuddyQueue({root,publish,now=()=>Date.now()}){
 fs.mkdirSync(root,{recursive:true});
 const jobs=fs.readdirSync(root).filter(n=>/^[a-f0-9-]{36}$/.test(n)).map(id=>JSON.parse(fs.readFileSync(path.join(root,id,'job.json'),'utf8')));
 let worker=null;
 const completing=new Set();
 const save=j=>{j.updatedAt=new Date(now()).toISOString();atomicJson(path.join(root,j.id,'job.json'),j);};
 const event=(j,message)=>{fs.appendFileSync(path.join(root,j.id,'events.jsonl'),JSON.stringify({at:new Date(now()).toISOString(),message:String(message).slice(0,16000)})+'\n');j.message=String(message).slice(0,250);save(j);};
 const get=id=>{const j=jobs.find(j=>j.id===id);if(!j)throw Error('任务不存在');return j;};
 const claimed=(id,lease)=>{const j=get(id);if(!['running','pausing','interrupted'].includes(j.state)||!lease||j.lease!==lease)throw Error('任务租约已失效，不能回传');if(j.state==='interrupted'){j.state=j.pauseRequested?'pausing':'running';event(j,'原 WorkBuddy 会话重新连接，继续同一尝试');}return j;};
 function expire(){for(const j of jobs)if(['running','pausing'].includes(j.state)&&now()-j.heartbeatAt>120000){j.state='interrupted';event(j,'超过2分钟没有进度心跳，执行状态待核实；原会话可续接，不自动重做');}}
 for(const j of jobs)if(['running','pausing'].includes(j.state)){j.state='interrupted';event(j,'工作台重启，等待原 WorkBuddy 会话续接；未启动重复制作');}
 return {
  list(){expire();return jobs.map(({lease,...j})=>structuredClone(j));},
  worker:()=>worker&&{...worker,online:now()-worker.seenAt<120000},
  enqueue(input){
   const old=jobs.findLast(j=>j.key===input.key);if(old)return {...old,lease:undefined};
   for(const s of input.sources)if(digest(s.path)!==s.sha256)throw Error('任务源件已变化，需要重新核对');
   const j={id:randomUUID(),...structuredClone(input),executor:'WorkBuddy',state:'queued',attempt:0,createdAt:new Date(now()).toISOString()};
   fs.mkdirSync(path.join(root,j.id));jobs.push(j);event(j,'工作台已派单，等待 WorkBuddy 领取');return {...j};
  },
  claim(session){
   expire();worker={session:String(session).slice(0,100),seenAt:now()};
   if(jobs.some(j=>['running','pausing','interrupted'].includes(j.state)&&j.lease))return null;
   // Group by verified kind/method; article is an identity, never a scheduling bucket.
   const j=jobs.filter(j=>j.state==='queued').sort((a,b)=>a.group.localeCompare(b.group)||a.createdAt.localeCompare(b.createdAt))[0];if(!j)return null;
   for(const s of j.sources)if(digest(s.path)!==s.sha256){j.state='failed';event(j,'源件哈希变化，领取已阻止');return null;}
   j.attempt++;j.state='running';j.session=session;j.lease=randomUUID();j.heartbeatAt=now();j.attemptDir=path.join(root,j.id,String(j.attempt));fs.mkdirSync(j.attemptDir,{recursive:true});event(j,'WorkBuddy 已领取：'+j.group);return structuredClone(j);
  },
  heartbeat(id,lease){const j=claimed(id,lease);j.heartbeatAt=now();worker={session:j.session,seenAt:now()};save(j);return {pauseRequested:j.state==='pausing'};},
  progress(id,lease,message){const j=claimed(id,lease);j.heartbeatAt=now();event(j,message);},
  pause(id){const j=get(id);if(!['queued','running','interrupted'].includes(j.state))throw Error('当前任务不能暂停');j.pauseRequested=true;j.state=j.state==='queued'?'paused':'pausing';event(j,j.state==='pausing'?'请求安全暂停，等待 WorkBuddy 完成当前工具调用并保存进度':'已暂停，不会被领取');},
  acknowledgePause(id,lease){const j=claimed(id,lease);if(j.state!=='pausing')throw Error('未请求暂停');j.state='paused';delete j.lease;event(j,'WorkBuddy 已保存进度并暂停');},
  resume(id){const j=get(id);if(j.state!=='paused')throw Error('当前任务不处于暂停状态');j.state='queued';j.pauseRequested=false;event(j,'已继续：重新领取后复用上次候选和进度');},
  retry(id,confirmedStopped){const j=get(id);if(!['failed','interrupted','needs_input'].includes(j.state))throw Error('当前任务不能重试');if(j.state==='interrupted'&&!confirmedStopped)throw Error('请先确认旧 WorkBuddy 任务已停止，避免重复执行');j.state='queued';j.pauseRequested=false;delete j.lease;event(j,'重试已排队，保留此前日志和候选');},
  fail(id,lease,message,needsInput=false){const j=claimed(id,lease);j.state=needsInput?'needs_input':'failed';delete j.lease;event(j,message);},
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
   if(!result.evidence?.trim()||!Array.isArray(result.outputs)||!result.outputs.length)throw Error('缺少产物或原图/最终PDF核对证据');
   const seen=new Set();
   for(const o of result.outputs){
    if(!/^\d+(?:[.-]\d+)*$/.test(o.number)||seen.has(o.number)||!j.outputNumbers.includes(o.number))throw Error('输出图号与已核对任务不符');seen.add(o.number);
    o.path=checkedArtifact(j.attemptDir,o.path,/^\.(pdf|jpg|jpeg)$/i);o.preview=checkedArtifact(j.attemptDir,o.preview,/^\.png$/i);
    if(digest(o.path)!==o.sha256)throw Error('产物哈希不一致');
    const bytes=fs.readFileSync(o.path),png=fs.readFileSync(o.preview);
    if(path.extname(o.path).toLowerCase()==='.pdf'?!bytes.subarray(0,5).equals(Buffer.from('%PDF-')):bytes[0]!==255||bytes[1]!==216)throw Error('产物格式无效');
    if(!png.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))throw Error('预览格式无效');
    o.previewSha256=digest(o.preview);
   }
   if(j.outputNumbers.some(n=>!seen.has(n)))throw Error('本任务导出项未齐备');
   atomicJson(path.join(j.attemptDir,'result.json'),result);
   await publish(j,result);j.result=result;j.state='ready';delete j.lease;event(j,'成图已回传，等待终审；未自动验收');
   }finally{completing.delete(id);}
  },
  events(id){get(id);const file=path.join(root,id,'events.jsonl'),size=fs.statSync(file).size,fd=fs.openSync(file,'r'),bytes=Buffer.alloc(Math.min(size,256*1024));try{fs.readSync(fd,bytes,0,bytes.length,size-bytes.length);}finally{fs.closeSync(fd);}return bytes.toString('utf8').split('\n').filter(Boolean).slice(-150).flatMap(line=>{try{return [JSON.parse(line)];}catch{return [];}});}
 };
}
