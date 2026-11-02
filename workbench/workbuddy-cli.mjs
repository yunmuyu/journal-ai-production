import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
const [configPath,action,...args]=process.argv.slice(2);
if(!configPath||!action)throw Error('Usage: node workbuddy-cli.mjs <worker-config.json> claim|heartbeat|progress|run|complete|fail|paused ...');
const config=JSON.parse(fs.readFileSync(configPath,'utf8').replace(/^\uFEFF/,''));
async function api(body){const response=await fetch(new URL('/workbuddy/worker',config.origin),{method:'POST',headers:{Authorization:'Bearer '+config.workerToken,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});const result=await response.json();if(!response.ok)throw Error(result.error||'工作台请求失败');return result;}
if(action==='claim'){
 const wait=Math.min(60,Math.max(0,Number(args[0]||0))),until=Date.now()+wait*1000;let job;
 do{({job}=await api({action:'claim',session:config.session||'WorkBuddy本地执行会话'}));if(job||Date.now()>=until)break;await new Promise(r=>setTimeout(r,2000));}while(true);
 if(job){const leaseFile=path.join(job.attemptDir,'lease.json');fs.writeFileSync(leaseFile,JSON.stringify({id:job.id,lease:job.lease}));delete job.lease;fs.writeFileSync(path.join(job.attemptDir,'task.json'),JSON.stringify(job,null,2));console.log(JSON.stringify({job,leaseFile},null,2));}else console.log(JSON.stringify({job:null,message:'暂无待执行任务，可再次领取'}));
}else{
 const [leaseFile,...rest]=args;if(!leaseFile)throw Error('缺少本任务 lease.json 路径');
 const lease=JSON.parse(fs.readFileSync(leaseFile,'utf8'));
 if(action==='run'){
  const [executable,...argv]=rest;if(!executable)throw Error('缺少工具命令');
  const state=await api({...lease,action:'heartbeat'});if(state.pauseRequested){await api({...lease,action:'paused'});console.log('已到安全停点，停止执行后续工具');process.exit(0);}
  await api({...lease,action:'progress',message:'执行工具：'+path.basename(executable)+' '+argv.join(' ').slice(0,4000)});
  let stopped=false;const timer=setInterval(()=>api({...lease,action:'heartbeat'}).catch(e=>{stopped=true;console.error(e.message);}),15000);timer.unref();
  const child=spawn(executable,argv,{cwd:path.dirname(leaseFile),windowsHide:true,stdio:['ignore','pipe','pipe']});let tail='';
  for(const stream of [child.stdout,child.stderr]){stream.setEncoding('utf8');stream.on('data',s=>{process.stdout.write(s);tail=(tail+s).slice(-12000);});}
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',resolve);}).finally(()=>clearInterval(timer));
  if(!stopped)await api({...lease,action:'progress',message:`工具结束（${code}）：\n${tail.replace(/\bsk-[\w-]{12,}/g,'[已隐藏]')}`});
  process.exitCode=code||0;
 }else{
  const body={...lease,action};if(action==='progress'||action==='fail')body.message=rest.join(' ');if(action==='complete')body.result=JSON.parse(fs.readFileSync(rest[0],'utf8'));console.log(JSON.stringify(await api(body)));
 }
}
