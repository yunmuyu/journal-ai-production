import fs from 'node:fs';
import path from 'node:path';
import {atomicJson} from './revision-jobs.mjs';
import {digest,checkedArtifact} from './revision-worker.mjs';
import {assertProductionRoute,assertOutputRoutes,routeSourceRefs,verifyAutomaticRevisionCandidate} from './production-route.mjs';
import {processingRequirement} from './processing-evidence.mjs';
import {verifyImportedPdfCandidate} from './imported-pdf.mjs';
import {feedbackHash} from './feedback-candidate-audit.mjs';

const ref=p=>({path:p,sha256:digest(p)});
const sameRef=(a,b)=>a&&b&&fs.realpathSync(a.path)===fs.realpathSync(b.path)&&a.sha256===b.sha256;
const checkRef=value=>{if(!value?.path||digest(value.path)!==value.sha256)throw Error('修订冻结证据或来源已变化');};

// Called only by the existing authenticated coordinator endpoint and single writer.
export function commonRevisionTools({root,figure,articles,assertAvailable,baseOutputsMatch,alreadyActivated,candidateVersion,getAcceptance,activate,refresh,save,view,qualityPython}){
 function current(r,{restorePublished=false}={}){
  const f=figure(r.figureId);
  if((f.feedback?.revision??null)!==r.feedbackRevision||feedbackHash(f.feedback??null)!==r.feedbackHash){
   // New point feedback on a sealed, already published candidate does not erase
   // that candidate on restart. It does not authorize making a new revision.
   const points=f.feedback?.points,outputs=r.result?.outputs;
   const laterText=restorePublished&&(f.feedback?.revision??0)>(r.feedbackRevision??0)&&(!points||points.length===0);
   const bound=laterText||(restorePublished&&Array.isArray(points)&&points.length>0&&Array.isArray(outputs)&&points.every(p=>outputs.some(o=>o.number===p.output&&o.sha256===p.sha256)));
   if(!bound)throw Error('批注已变化，请重新提交修订');
  }
  if(r.articleWord){const word=articles.find(a=>a.id===r.articleId)?.word;if(!word||!sameRef(ref(word.path),r.articleWord))throw Error('提交时Word来源身份已变化');}
  assertAvailable(r.figureId);return f;
 }
 function prepare(r,input){
  const f=current(r);
  if(f.status==='终检通过'||r.result||f.reviewVersion!==r.version||!baseOutputsMatch(r,f))throw Error('图稿或批注已变化，不能改写已回传或已验收修订');
  const route=assertProductionRoute({productionRoute:input.productionRoute,outputNumbers:r.outputNumbers});
  const previous=assertProductionRoute({productionRoute:f.productionRoute,outputNumbers:r.outputNumbers});
  for(const key of ['archive','word','inventory'])if(!sameRef(previous.sourceReview[key],route.sourceReview[key]))throw Error('修订路线不能更换原包、Word或来源清单的来源身份');
  if(r.articleWord&&!sameRef(route.sourceReview.word,r.articleWord))throw Error('修订Word来源身份不匹配');
  const routes=assertOutputRoutes({outputNumbers:r.outputNumbers,figureNumber:r.number,productionRoute:route},input.outputRoutes);
  routes.forEach(entry=>processingRequirement(entry.productionRoute));
  if(r.commonCandidate&&!input.newAttempt){
   checkRef(r.commonCandidate.task);const task=JSON.parse(fs.readFileSync(r.commonCandidate.task.path,'utf8'));
   if(JSON.stringify(task.outputRoutes)!==JSON.stringify(routes))throw Error('加工路线已变化，须明确建立新尝试');
   return view(r);
  }
  const attempt=(r.commonCandidate?.attempt??0)+1,attemptDir=path.join(root,r.id,'common-candidate',String(attempt));
  fs.mkdirSync(attemptDir,{recursive:true});
  const task={id:r.id+'-'+attempt,kind:'revision',figureId:r.figureId,articleId:r.articleId,author:r.author,figureNumber:r.number,attempt,attemptDir,
   baseVersion:r.version,baseOutputs:r.baseOutputs,feedback:r.feedback,feedbackRevision:r.feedbackRevision,feedbackHash:r.feedbackHash,
   outputNumbers:r.outputNumbers,productionRoute:route,outputRoutes:routes,sources:[...new Map(routes.flatMap(entry=>routeSourceRefs(entry.productionRoute)).map(source=>[fs.realpathSync(source.path),source])).values()]};
  const taskPath=path.join(attemptDir,'task.json');fs.writeFileSync(taskPath,JSON.stringify(task,null,2),{flag:'wx'});
  r.commonCandidate={attempt,task:ref(taskPath)};r.state='candidate_prepared';r.executor='Codex';r.message='共用修订尝试已冻结，等待公共工具候选；未启动执行器';save();return view(r);
 }
 function taskFor(r){
  checkRef(r.commonCandidate.task);const task=JSON.parse(fs.readFileSync(r.commonCandidate.task.path,'utf8'));
  if(task.id!==r.id+'-'+r.commonCandidate.attempt||task.figureId!==r.figureId||task.feedbackHash!==r.feedbackHash||task.baseVersion!==r.version)throw Error('修订尝试身份不匹配');
  task.sources.forEach(checkRef);return task;
 }
 function restore(r){
  const f=current(r,{restorePublished:true}),task=taskFor(r),dir=task.attemptDir;
  const receipt=JSON.parse(fs.readFileSync(path.join(dir,'published.json'),'utf8'));
  for(const key of ['figureId','feedbackRevision','feedbackHash','baseOutputs','qualityVerification','result'])if(JSON.stringify(receipt[key])!==JSON.stringify(r[key]))throw Error('共用修订发布回执不一致：'+key);
  if(receipt.jobId!==r.id||!sameRef(receipt.task,r.commonCandidate.task))throw Error('发布任务身份不匹配');
  receipt.sealedEvidence.forEach(checkRef);
  r.result.outputs.forEach(o=>{checkedArtifact(dir,o.path,/\.(pdf|jpg|jpeg)$/i);checkRef(o);checkRef({path:o.preview,sha256:o.previewSha256});});
  const activated=alreadyActivated(r,f),acceptance=getAcceptance(r.figureId);
  if(f.status==='终检通过'&&(!activated||acceptance?.version!==candidateVersion(r.result.outputs,r.feedbackRevision)))throw Error('已验收版本不匹配，不覆盖');
  if(!f.outputs.length&&acceptance?.accepted===true&&acceptance.version!==candidateVersion(r.result.outputs,r.feedbackRevision))throw Error('验收版本不匹配，不能恢复');
  const laterFeedback=(f.feedback?.revision??0)>(r.feedbackRevision??0);
  const samePublished=f.outputs.length===r.result.outputs.length&&r.result.outputs.every(o=>f.outputs.some(current=>current.number===o.number&&sameRef(ref(current.file.path),o)));
  if(f.outputs.length&&!activated&&!(laterFeedback&&samePublished)&&((f.reviewVersion!==r.version&&!laterFeedback)||!baseOutputsMatch(r,f)))throw Error('当前图稿已变化，不能恢复旧修订');
  if(!activated){activate({...receipt,pendingKey:r.figureId});f.productionRoute=task.productionRoute;refresh();}
  r.state='ready';r.message='共用修订候选已回工作台待用户终审';delete r.restoreError;save();return view(r);
 }
 function publish(r,input){
  if(!r.commonCandidate)throw Error('请先准备共用修订尝试');
  if(r.result&&['publishing','ready'].includes(r.state)){
   if(input&&input.attempt!==r.commonCandidate.attempt)throw Error('修订尝试已失效');
   return restore(r);
  }
  const f=current(r);
  if(f.status==='终检通过'||f.reviewVersion!==r.version||!baseOutputsMatch(r,f))throw Error('图稿或批注已变化，不能回传旧修订');
  if(!input||input.attempt!==r.commonCandidate?.attempt)throw Error('修订尝试已失效');
  const task=taskFor(r),raster=task.productionRoute.method==='raster-preserve',outputs=raster?input.result?.outputs:input.outputs;
  if(!Array.isArray(outputs)||outputs.length!==task.outputNumbers.length||new Set(outputs.map(o=>o.number)).size!==outputs.length||outputs.some(o=>!task.outputNumbers.includes(o.number)))throw Error('修订输出图号不完整或重复');
  for(const output of outputs){checkedArtifact(task.attemptDir,output.path,raster?/\.jpe?g$/i:/\.pdf$/i);checkRef(output);if(r.baseOutputs.some(old=>old.number===output.number&&old.sha256===output.sha256))throw Error('候选与旧图相同，不能当作已加工修订');}
  const staged={...task,existingPdf:{outputs:outputs.map(o=>({number:o.number,staged:{path:o.path,sha256:o.sha256}}))}};
  const checked=raster?{qualityVerification:verifyAutomaticRevisionCandidate(task,input.result,{python:qualityPython}),result:structuredClone(input.result)}:verifyImportedPdfCandidate(staged,input,{python:qualityPython});
  const after=current(r);if(after.reviewVersion!==r.version||!baseOutputsMatch(r,after))throw Error('检查期间图稿或批注变化');
  const result={...checked.result,summary:typeof input.summary==='string'&&input.summary.trim()?input.summary:'公共工具修订候选已通过必要自动检查，待用户终审。'};
  const qualityVerification={...checked.qualityVerification,manualStatus:checked.qualityVerification.manualStatus??checked.qualityVerification.manual_status,kind:'common-revision-candidate'};
  const sealedEvidence=raster?[r.commonCandidate.task,...(input.result.quality.outputChecks??[]).flatMap(e=>[e.task,e.result]),...[input.result.quality.contract,input.result.quality.rasterPlan,input.result.selfCheck].filter(Boolean)]:[r.commonCandidate.task,input.contract,input.submission,...input.processingEvidence.flatMap(e=>[e.report,e.spec])];
  sealedEvidence.forEach(checkRef);
  const record={at:new Date().toISOString(),jobId:r.id,figureId:r.figureId,feedbackRevision:r.feedbackRevision,feedbackHash:r.feedbackHash,baseOutputs:r.baseOutputs,task:r.commonCandidate.task,productionRoute:task.productionRoute,qualityVerification,result,sealedEvidence};
  atomicJson(path.join(task.attemptDir,'published.json'),record);
  r.state='publishing';r.qualityVerification=qualityVerification;r.result=result;r.message='自动检查通过，正在登记共用修订候选';save();
  activate({...record,pendingKey:r.figureId});f.productionRoute=task.productionRoute;refresh();
  r.state='ready';r.message='共用修订候选已回工作台待用户终审';save();return view(r);
 }
 return {prepare,publish,restore};
}
