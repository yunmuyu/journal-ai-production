// One mechanical run; never claims a task, submits it, or approves a visual review.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {performance} from 'node:perf_hooks';
import {prepareProductionWorkspace} from './production-workspace.mjs';
import {snapshotEvidence,writeSealedJson,sealEvidence,verifyEvidenceSeal,appendSelfCheck,checkEvidence} from './evidence-seal.mjs';

const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const ref=p=>({path:path.resolve(p),sha256:createHash('sha256').update(fs.readFileSync(p)).digest('hex')});
const save=(p,data)=>{fs.writeFileSync(p,JSON.stringify(data,null,2)+'\n',{encoding:'utf8',flag:'wx'});return ref(p);};
const tools=fileURLToPath(new URL('../portable-production/',import.meta.url));
const mechanicalCode=`import json,sys
from pathlib import Path
from task_quality.models import Contract
from task_quality.checks import measure,check_artifact_set
c=Contract.parse(json.load(open(sys.argv[1],encoding='utf-8')))
check_artifact_set(c)
print(json.dumps([{'id':o.id,'measurement':measure(o,c.workspace/o.path)} for o in c.outputs]))`;

export function runRasterJob(taskPath,planPath,evidencePath){
 const task=read(taskPath),attempt=fs.realpathSync(task.attemptDir);
 if(fs.realpathSync(path.dirname(taskPath))!==attempt)throw Error('task.json必须来自领取后的attempt根目录');
 const runDir=path.join(attempt,'raster-job');
 if(fs.existsSync(runDir)){
  const seal=verifyEvidenceSeal(runDir),request=read(path.join(runDir,'request.json'));
  for(const [key,p] of Object.entries({task:taskPath,plan:planPath,evidence:evidencePath})){
   if(path.resolve(p)!==request[key].path)throw Error('运行输入路径变化，需要新attempt');
   checkEvidence(request[key]);
  }
  return {...read(path.join(runDir,'run.json')),seal,reused:true};
 }
 // Never mutate an incomplete previous run; retries need a new attempt.
 fs.mkdirSync(runDir);
 const timings=[];let activeStage='prepare';
 function stage(name,fn){
  activeStage=name;const started=performance.now();
  try{const value=fn();timings.push({stage:name,elapsed_ms:performance.now()-started,status:'ok'});return value;}
  catch(error){timings.push({stage:name,elapsed_ms:performance.now()-started,status:'failed'});throw error;}
 }
 try{
  writeSealedJson(path.join(runDir,'request.json'),{task:ref(taskPath),plan:ref(planPath),evidence:ref(evidencePath)});
  const snapshots=path.join(runDir,'snapshots');fs.mkdirSync(snapshots);
  const evidence=read(evidencePath),originalEvidence=snapshotEvidence(snapshots,'executor-evidence.original.json',evidencePath);
  const frozenTask=snapshotEvidence(snapshots,'task.json',taskPath),frozenPlan=snapshotEvidence(snapshots,'raster-plan.json',planPath);
  if(evidence.history?.evidence)evidence.history.evidence=snapshotEvidence(snapshots,'history.json',evidence.history.evidence);
  if(evidence.frozen_manifest)evidence.frozen_manifest=snapshotEvidence(snapshots,'frozen.json',evidence.frozen_manifest);
  const prepared=stage('prepare',()=>prepareProductionWorkspace(frozenTask.path,frozenPlan.path,evidence));
  if(prepared.status!=='prepared')throw Error('缺少执行者证据: '+prepared.missing.join(', '));
  const contract=prepared.contract;
  contract.runtime.code.push(ref(fileURLToPath(import.meta.url)));
  contract.source_inputs.push(originalEvidence);
  const contractRef=writeSealedJson(path.join(runDir,'quality-contract.json'),contract);
  const env={...process.env,PYTHONPATH:tools,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
  function python(name,args){return stage(name,()=>{
   let stdout;
   try{stdout=execFileSync(contract.runtime.python.path,['-X','utf8',...args],{env,encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer:4*1024*1024});}
   catch(error){save(path.join(runDir,name+'.error.json'),{stdout:String(error.stdout||''),stderr:String(error.stderr||''),message:error.message});throw error;}
   const value=JSON.parse(stdout);save(path.join(runDir,name+'.json'),value);
   if(value.ok===false)throw Error(name+' failed: '+JSON.stringify(value.error));
   return value;
  });}
  python('precheck',['-m','task_quality','precheck',contractRef.path]);
  const rendered=python('render',['-m','raster','render',frozenPlan.path]);
  // raster CLI wraps the report in {ok,result}; never infer success from exit status alone.
  const report=rendered.result??rendered;
  python('mechanical',['-c',mechanicalCode,contractRef.path]);
  const output=contract.outputs[0],jpg=ref(path.join(contract.workspace,output.path));
  const preview=ref(report.preview.path);
  if(jpg.sha256!==report.output.sha256||preview.sha256!==report.preview.sha256)throw Error('产物/预览哈希与公共raster报告不符');
  const mechanical=ref(path.join(runDir,'mechanical.json'));
  const audit=save(path.join(contract.workspace,'raster-job-audit.json'),{
   coverage:contract.mechanical.map(id=>({id,status:'checked',evidence:[mechanical,jpg,preview]})),
   source_geometry:{status:'pending',evidence:[contract.source,prepared.plan],observation:'按执行者计划加工；内容保留与灰度语义尚待实际看图及独立审阅。'},
   label_path_binding:{status:'not-applicable',evidence:[prepared.plan],observation:'位图保留路线没有可编辑标签及矢量连线归属；图片内容仍待复核。'},
   scene:null,output_bindings:{[output.id]:jpg.sha256}});
  const submission=save(path.join(runDir,'submission.json'),{artifacts:[jpg],audit});
  const checked=python('postcheck',['-m','task_quality','postcheck',contractRef.path,submission.path]);
  if(checked.result?.manual_status!=='pending')throw Error('postcheck未返回预期的待人工复核状态');
  const column=Math.round(output.width_mm/80*10)*10;
  const result=save(path.join(runDir,'result.json'),{
   summary:'灰度 JPG 候选已生成，待看图及独立复核。',
   evidence:'公共工具机械检查完成；来源内容、可辨性及灰度语义尚未进行视觉通过判定。',
   outputs:[{number:task.outputNumbers[0],path:jpg.path,sha256:jpg.sha256,preview:preview.path,
    columnLabel:output.width_mm<=80?'单栏约'+column+'%':'双栏约'+Math.round(output.width_mm/160*10)*10+'%',fontLabel:''}],
   quality:{contract:contractRef,rasterPlan:prepared.plan}});
  const value={status:'awaiting_visual_review',result,submission,contract:contractRef,timings,
   next:'执行者看图后用self-check写独立笔记与派生result，再提交；禁止修改audit/history。'};
  save(path.join(runDir,'run.json'),value);
  const external=read(path.join(contract.workspace,'.task-quality','envelope.json')).inputs;
  const seal=sealEvidence(attempt,runDir,contract.workspace,external);
  return {...value,seal};
 }catch(error){save(path.join(runDir,'failure.json'),{status:'failed',stage:activeStage,error:error.message,timings});throw error;}
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  const args=process.argv.slice(2);if(args.length!==3)throw Error('Usage: node raster-job.mjs task.json raster-plan.json existing-evidence.json OR self-check task.json observations.json');
  const value=args[0]==='self-check'?appendSelfCheck(read(args[1]).attemptDir,read(args[2])):runRasterJob(...args);
  console.log(JSON.stringify(value,null,2));
 }catch(error){console.error(error.message);process.exitCode=1;}
}
