import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export function atomicJson(file,value){fs.writeFileSync(file+'.tmp',JSON.stringify(value,null,2));fs.renameSync(file+'.tmp',file);}
const alive=pid=>{try{process.kill(pid,0);return true;}catch{return false;}};
export function createRevisionJobs({root,run,publish}){
 fs.mkdirSync(root,{recursive:true});
 const jobs=fs.readdirSync(root).filter(n=>/^[\da-f-]{36}$/.test(n)).map(n=>JSON.parse(fs.readFileSync(path.join(root,n,'job.json'),'utf8'))).sort((a,b)=>a.createdAt.localeCompare(b.createdAt));
 const save=job=>{job.updatedAt=new Date().toISOString();atomicJson(path.join(root,job.id,'job.json'),job);};
 for(const job of jobs)if(job.state==='running'){job.state='interrupted';job.message='服务中断；候选未发布，请检查后重新提交';save(job);}
 let busy=null;
 return {
  list:()=>jobs.map(({input,...job})=>structuredClone(job)),
  submit(input,retry=false){
   if(jobs.some(j=>j.childPid&&alive(j.childPid)&&j.state==='interrupted'))throw Error('上次执行进程仍在退出，不能重复开工');
   const same=jobs.findLast(j=>j.figureId===input.figureId&&j.version===input.version);
   if(same&&['queued','running','ready'].includes(same.state))return structuredClone(same);
   if(jobs.some(j=>j.figureId===input.figureId&&['queued','running'].includes(j.state)))throw Error('此图已有任务，请等本次结束后提交新批注');
   if(same&&!retry)throw Error('上次任务未完成，请点击重新提交');
   const job={id:randomUUID(),figureId:input.figureId,version:input.version,state:'queued',message:'等待执行',createdAt:new Date().toISOString(),input:structuredClone(input)};
   fs.mkdirSync(path.join(root,job.id));atomicJson(path.join(root,job.id,'input.json'),input);jobs.push(job);save(job);return structuredClone(job);
  },
  async drain(){
   if(busy)return busy;
   if(jobs.some(j=>j.state==='interrupted'&&j.childPid&&alive(j.childPid)))return;
   busy=(async()=>{
    for(const job of jobs.filter(j=>j.state==='queued')){
     job.state='running';job.message='AI 正在读取原图与批注';save(job);
     try{
      const result=await run(path.join(root,job.id),job.input,(message,childPid)=>{job.message=message;if(childPid)job.childPid=childPid;save(job);});
      delete job.childPid;
      if(result.status==='needs_input'){job.state='needs_input';job.message=result.summary;}
      else if(result.status==='completed'){
       job.message='正在核验候选并回传';save(job);
       await publish(job,result,path.join(root,job.id));job.state='ready';job.message=result.summary;
      }else throw Error('AI 返回的任务状态不合法');
     }catch(error){delete job.childPid;job.state='failed';job.message=error.message;}
     save(job);
    }
   })();
   try{await busy;}finally{busy=null;}
  }
 };
}
