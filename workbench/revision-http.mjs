import {dispatchInstructions} from './production-dispatch.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {createRevisionJobs,atomicJson} from './revision-jobs.mjs';
import {createCodexWorker,digest,validateResult} from './revision-worker.mjs';
import {assertProductionRoute,routeSourceRefs} from './production-route.mjs';

// Adapter owns candidate activation; worker only writes its isolated directory.
export function createRevisionHandler({root,config,origin,rows,articles,refresh,activate,run=createCodexWorker(config),enabled=true}){
 fs.mkdirSync(root,{recursive:true});
 const lock=path.join(root,'service.lock');
 if(fs.existsSync(lock)){
  const owner=Number(fs.readFileSync(lock,'utf8'));let live=false;
  try{process.kill(owner,0);live=true;}catch{}
  if(live)throw Error('此修订队列已有工作台服务在运行');
  fs.unlinkSync(lock);
 }
 fs.writeFileSync(lock,String(process.pid),{flag:'wx'});
 const restore=fs.readdirSync(root).filter(n=>/^[\da-f-]{36}$/.test(n)).map(n=>path.join(root,n,'published.json')).filter(p=>fs.existsSync(p)).map(p=>({jobId:path.basename(path.dirname(p)),...JSON.parse(fs.readFileSync(p,'utf8'))})).sort((a,b)=>a.at.localeCompare(b.at));
 for(const record of restore){
  const dir=path.join(root,record.jobId);
  validateResult(dir,JSON.parse(fs.readFileSync(path.join(dir,'input.json'),'utf8')),record.result,{legacy:true});record.qualityStatus=record.result.quality?'recorded':'legacy-unverified';activate(record);
  const file=path.join(dir,'job.json'),job=JSON.parse(fs.readFileSync(file,'utf8'));
  if(job.state!=='ready'){job.state='ready';job.message=record.result.summary;delete job.childPid;atomicJson(file,job);}
 }
 const queue=createRevisionJobs({root,run,publish(job,result,dir){
  refresh();const figure=rows.find(f=>f.id===job.figureId);
  if(!figure||figure.reviewVersion!==job.version)throw Error('图稿或批注在执行期间变化；候选保留，请核对后重新提交');
  if(job.input.word&&digest(job.input.word.path)!==job.input.word.sha256)throw Error('原 Word 已变化，候选暂不回传');
  validateResult(dir,{...job.input,taskId:job.id},result,{qualityPython:config.qualityPython});
  const record={at:new Date().toISOString(),jobId:job.id,figureId:job.figureId,feedbackRevision:job.input.feedback.revision,result};
  atomicJson(path.join(dir,'published.json'),record);activate(record);refresh();
 }});
 let timer=enabled?setInterval(()=>queue.drain().catch(error=>console.error('Revision queue:',error.message)),1000):null;timer?.unref();
 const json=(res,status,body)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(body));};
 return {
  queue,
  decorate(){const jobs=queue.list();for(const figure of rows)figure.revisionJob=jobs.findLast(j=>j.figureId===figure.id)||null;},
  close(){clearInterval(timer);if(fs.existsSync(lock)&&fs.readFileSync(lock,'utf8')===String(process.pid))fs.unlinkSync(lock);},
  handle(req,res,url){
   if(!url.pathname.startsWith('/revision-jobs'))return false;
   if(req.method==='GET'&&url.pathname==='/revision-jobs'){json(res,200,{jobs:queue.list()});return true;}
   if(!enabled){json(res,409,{error:'旧 Codex 制作入口已停用；请提交终审意见，由 ChatGPT 分流给 WorkBuddy'});return true;}
   if(req.method!=='POST'||req.headers.origin!==origin){json(res,403,{error:'只允许在工作台内提交'});return true;}
   if(!url.pathname.startsWith('/revision-jobs/')||!req.headers['content-type']?.startsWith('application/json')){json(res,400,{error:'提交格式不正确'});return true;}
   let size=0;const chunks=[];req.on('data',part=>{size+=part.length;if(size<=4096)chunks.push(part);});
   req.on('end',()=>{try{
    if(size>4096)throw Error('请求过大');
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));refresh();
    const figure=rows.find(f=>f.id===decodeURIComponent(url.pathname.slice('/revision-jobs/'.length)));
    if(!figure||figure.reviewVersion!==body.version)throw Error('图稿或批注已变化，请刷新后提交');
    if(figure.status==='终检通过')throw Error('此版本已通过，请先新增或修改批注，不能把已解决的旧批注再次当作任务');
    const feedback=figure.feedback;
    if(!feedback||!(feedback.text?.trim()||feedback.attachments?.length||feedback.points?.length))throw Error('请先填写并保存本次修改意见');
    const word=articles.find(a=>a.id===figure.articleId)?.word;
    const input={figureId:figure.id,author:figure.author,number:figure.number,version:figure.reviewVersion,feedback,productionRoute:figure.productionRoute,
     word:word?{path:word.path,sha256:digest(word.path)}:null,
     outputs:figure.outputs.map(o=>({number:o.number,path:o.file.path,sha256:digest(o.file.path)}))};
    input.instructions=dispatchInstructions({...input,outputNumbers:input.outputs.map(o=>o.number)});
    input.sources=routeSourceRefs(input.productionRoute);
    const job=queue.submit(input,body.retry===true);json(res,202,{job:{id:job.id,state:job.state}});
   }catch(error){json(res,409,{error:error.message});}});
   return true;
  }
 };
}
