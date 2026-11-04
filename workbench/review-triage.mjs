import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID,timingSafeEqual} from 'node:crypto';
import {atomicJson} from './revision-jobs.mjs';
import {digest} from './revision-worker.mjs';
import {verifyFeedbackCandidate,verifyFeedbackPdfCandidate,feedbackHash,attachmentHashes} from './feedback-candidate-audit.mjs';
import {assertProductionRoute,productionInstructions,routeSourceRefs} from './production-route.mjs';
import {commonRevisionTools} from './common-revision.mjs';

// A saved review is first a coordinator decision, never an implicit AI launch.
export function createReviewTriage({root,origin,token,queue,rows,articles,refresh,activate,legacyJobs=()=>[],candidateManifest,candidateManifestsByFigureId={},qualityPython,getAcceptance=()=>null}){
 fs.mkdirSync(root,{recursive:true});const file=path.join(root,'reviews.json');
 const records=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):[];
 const save=()=>atomicJson(file,records);
 const manifestForFigure=id=>{
  const configured=Object.hasOwn(candidateManifestsByFigureId,id)?candidateManifestsByFigureId[id]:candidateManifest;
  return configured?path.resolve(configured):null;
 };
 const figure=id=>{refresh();const f=rows.find(f=>f.id===id);if(!f)throw Error('图件不存在');return f;};
 const view=r=>{const job=r.jobId&&queue.list().find(j=>j.id===r.jobId),failed=job&&['failed','needs_input'].includes(job.state);return {...r,state:failed?(r.state==='waiting_tools'?'waiting_tools':'needs_triage'):job?.state||r.state,message:failed?(r.state==='waiting_tools'?r.message:'执行问题已交 ChatGPT 排障：'+job.message):job?.message||r.message,executor:job&&!failed?'WorkBuddy':'ChatGPT'};};
 function assertAvailable(id,excludeJobId){
  if(legacyJobs().some(j=>j.figureId===id&&['queued','running','interrupted'].includes(j.state)))throw Error('旧执行器任务尚未收敛，不能重复派单');
  if(queue.list().some(j=>j.id!==excludeJobId&&(j.figureId===id||j.articleId+'-F'+j.figureNumber===id)&&['queued','running','pausing','paused','interrupted','review_pending'].includes(j.state)))throw Error('此图已有执行任务，等待安全结束后处理');
 }
 function submit(id,version,reason){
  const f=figure(id);if(f.reviewVersion!==version)throw Error('图稿或批注已变化，请刷新');
  if(f.status==='终检通过')throw Error('此版本已通过；请先新增终审意见，不能重跑已解决的旧批注');
  const feedback=f.feedback??null,revision=feedback?.revision??null;
  const old=records.findLast(r=>r.figureId===id&&r.feedbackRevision===revision&&r.version===version);if(old)return view(old);
  assertAvailable(id);if(!f.outputs.length)throw Error('此图尚无可修订成稿');
  const word=articles.find(a=>a.id===f.articleId)?.word;
  const baseOutputs=f.outputs.map(o=>({number:o.number,path:o.file.path,sha256:digest(o.file.path)}));
  const articleWord=word?.path?{path:word.path,sha256:digest(word.path)}:null;
  const sourceReview=f.productionRoute?.sourceReview;
  const routedSources=sourceReview?[sourceReview.selected,...(sourceReview.additionalSelected||[]),...(sourceReview.candidates||[])].filter(source=>source?.path&&source?.sha256):[];
  const sources=[...baseOutputs.map(({path,sha256})=>({path,sha256})),...(articleWord?[articleWord]:[]),...routedSources];
  const configuredManifest=manifestForFigure(id);
  const candidateManifestPath=configuredManifest&&fs.existsSync(configuredManifest)?configuredManifest:null;
  const candidateManifestSha256=candidateManifestPath?digest(candidateManifestPath):null;
  const r={id:randomUUID(),figureId:id,articleId:f.articleId,author:f.author,number:f.number,feedbackRevision:revision,version,feedback:structuredClone(feedback),feedbackHash:feedbackHash(feedback),feedbackAttachmentHashes:feedback?attachmentHashes(feedback):[],correctionReason:typeof reason==='string'?reason.trim():'',baseOutputs,articleWord,sources,candidateManifestPath,candidateManifestSha256,outputNumbers:f.outputs.map(o=>o.number),state:'needs_triage',executor:'ChatGPT',message:feedback?'终审意见已交给 ChatGPT 分流，尚未启动制作':'制作侧更正已登记，尚未启动制作',createdAt:new Date().toISOString()};
  records.push(r);save();return view(r);
 }
 function resolve(id,decision){
  const r=records.find(r=>r.id===id);if(!r)throw Error('终审事项不存在');
  const prior=r.jobId&&queue.list().find(j=>j.id===r.jobId);if(prior&&!['failed','needs_input','interrupted'].includes(prior.state))return view(r);
  if(prior?.state==='interrupted'&&decision.confirmedStopped!==true)throw Error('必须先核实旧 WorkBuddy 任务已停止；原会话仍可续接');
  const f=figure(r.figureId);if(f.reviewVersion!==r.version||(f.feedback?.revision??null)!==r.feedbackRevision||feedbackHash(f.feedback??null)!==r.feedbackHash||!baseOutputsMatch(r,f))throw Error('图稿或批注已经更新，请重新核对');
  if(!['ordinary','tool_fix','mixed'].includes(decision.kind)||!decision.instructions?.trim())throw Error('缺少明确的分流及执行说明');
  r.decision=structuredClone(decision);
  if(decision.kind!=='ordinary'&&(!decision.toolResolved||!decision.toolCommit?.match(/^[a-f0-9]{7,40}$/)||!decision.tests?.trim())){r.state='waiting_tools';r.message='ChatGPT 处理中：公共工具修复完成并验证后，才交给 WorkBuddy 重跑';save();return view(r);}
  assertAvailable(r.figureId,prior?.id);
  const previousRoute=assertProductionRoute({productionRoute:f.productionRoute,outputNumbers:r.outputNumbers});
  const route=decision.productionRoute===undefined?previousRoute:assertProductionRoute({productionRoute:decision.productionRoute,outputNumbers:r.outputNumbers});
  for(const key of ['archive','word','inventory']){
   const before=previousRoute.sourceReview[key],after=route.sourceReview[key];
   if(fs.realpathSync(before.path)!==fs.realpathSync(after.path)||before.sha256!==after.sha256)throw Error('修订路线不能更换原包、Word或来源清单的来源身份');
  }
  if(r.articleWord&&(fs.realpathSync(route.sourceReview.word.path)!==fs.realpathSync(r.articleWord.path)||route.sourceReview.word.sha256!==r.articleWord.sha256))throw Error('修订路线与提交时Word来源身份不同');
  const instructions=productionInstructions(route);
  if(prior){queue.revisePlan(prior.id,{productionRoute:route,instructions:decision.instructions+'\n按task.feedback逐项修订，使用公共工具，回传待终审。',decision},decision.confirmedStopped===true);queue.retry(prior.id,decision.confirmedStopped===true);r.state='queued';save();return view(r);}
  const job=queue.enqueue({key:`revision:${r.figureId}:${r.feedbackRevision}:${r.version}`,kind:'revision',priority:0,label:`${r.author} 图${r.number} · 终审修订`,group:'终审修订 / 已由 ChatGPT 分流',figureId:r.figureId,articleId:r.articleId,figureNumber:r.number,feedbackRevision:r.feedbackRevision,baseVersion:r.version,baseOutputs:r.baseOutputs,outputNumbers:r.outputNumbers,productionRoute:route,sources:[...r.sources,...routeSourceRefs(route)],feedback:r.feedback,coordinatorDecision:r.decision,instructions});
  r.jobId=job.id;r.state='queued';r.message='已交 WorkBuddy，等待领取';save();return view(r);
 }
 function publish(job,result){
  const f=figure(job.figureId);if(f.reviewVersion!==job.baseVersion||(f.feedback?.revision??null)!==job.feedbackRevision)throw Error('批注或图稿已更新；旧意见产物不能覆盖当前版本');
  if(!Array.isArray(job.baseOutputs)||job.baseOutputs.length!==f.outputs.length||job.baseOutputs.some(base=>{const current=f.outputs.find(o=>o.number===base.number);return !current||path.resolve(current.file.path)!==path.resolve(base.path)||digest(current.file.path)!==base.sha256;}))throw Error('原工作台输出或哈希已变化；候选未覆盖现有版本');
  activate({at:new Date().toISOString(),jobId:job.id,figureId:job.figureId,pendingKey:job.figureId,feedbackRevision:job.feedbackRevision,qualityVerification:job.qualityVerification||null,result});refresh();
 }
 function candidateVersion(outputs,feedbackRevision){
  const current=outputs.map(output=>[output.number,output.path,fs.existsSync(output.path)?digest(output.path):null]);
  return createHash('sha256').update(JSON.stringify([current,feedbackRevision||0])).digest('hex');
 }
 function outputsMatch(outputs,current){
  return Array.isArray(outputs)&&outputs.length===current.length&&outputs.every(output=>{const item=current.find(candidate=>candidate.number===output.number);return item&&path.resolve(item.file.path)===path.resolve(output.path)&&digest(item.file.path)===output.sha256;});
 }
 function baseOutputsMatch(r,f){
  return Array.isArray(r.baseOutputs)&&r.baseOutputs.length===f.outputs.length&&r.baseOutputs.every(base=>{const current=f.outputs.find(output=>output.number===base.number);return current&&path.resolve(current.file.path)===path.resolve(base.path)&&digest(current.file.path)===base.sha256;});
 }
 function alreadyActivated(r,f){
  return outputsMatch(r.result?.outputs,f.outputs)&&f.reviewVersion===candidateVersion(r.result.outputs,r.feedbackRevision);
 }
 function prepareCandidate(id,input){
  const r=records.find(r=>r.id===id);if(!r)throw Error('终审事项不存在');
  return common.prepare(r,input);
 }
 function importCandidate(id,input){
  const r=records.find(r=>r.id===id);if(!r)throw Error('终审事项不存在');
  if(r.commonCandidate||input)return common.publish(r,input);
  if(!qualityPython)throw Error('未配置直接候选检查清单及验证Python');
  const f=figure(r.figureId);
  if((f.feedback?.revision??null)!==r.feedbackRevision||feedbackHash(f.feedback??null)!==r.feedbackHash)throw Error('用户反馈revision或图稿版本已变化');
  const hasPersistedCandidate=['publishing','ready'].includes(r.state)&&Boolean(r.result?.outputs?.length);
  if(!hasPersistedCandidate&&f.reviewVersion!==r.version)throw Error('用户反馈revision或图稿版本已变化');
  const wasActivated=alreadyActivated(r,f);
  if(wasActivated&&(!r.result||!r.baseOutputs))throw Error('已激活候选缺少可恢复历史');
  const acceptance=getAcceptance(r.figureId),acceptedCandidate=acceptance?.accepted===true&&acceptance.version===candidateVersion(r.result?.outputs||[],r.feedbackRevision);
  if(f.status==='终检通过'&&(!wasActivated||!acceptedCandidate))throw Error('验收记录未精确绑定此候选版本，不能恢复或替换');
  if(!wasActivated&&(f.reviewVersion!==r.version||!baseOutputsMatch(r,f)))throw Error('原输出或图稿版本已变化，拒绝恢复候选');
  if(acceptance?.accepted===true&&wasActivated&&!acceptedCandidate)throw Error('已验收版本与当前候选版本不一致');
  assertAvailable(r.figureId);
  const manifestPath=r.candidateManifestPath||(r.candidateManifest?path.resolve(r.candidateManifest):manifestForFigure(r.figureId));
  if(!manifestPath||manifestForFigure(r.figureId)!==manifestPath)throw Error('终审记录绑定的候选清单不在此图件服务端allowlist内');
  const candidateRoot=path.dirname(manifestPath),manifestSha256=digest(manifestPath),audit=JSON.parse(fs.readFileSync(manifestPath,'utf8'));
  const boundAtSubmission=r.candidateManifestPath===manifestPath&&r.candidateManifestSha256===manifestSha256;
  const verifiedLegacyRaster=r.qualityVerification?.kind==='feedback-raster-replay'&&r.candidateManifest===manifestPath&&r.qualityVerification.manifestSha256===manifestSha256;
  if(!boundAtSubmission&&!verifiedLegacyRaster)throw Error('候选检查清单在终审提交后已变化或未绑定');
  const item=audit.items?.find(row=>String(row.figure)===String(r.number));if(!item)throw Error('候选清单中没有匹配图号');
  if(!hasPersistedCandidate)throw Error('新修订须使用共用prepare-candidate入口及加工证据，旧专用清单仅用于恢复历史候选');
  if(['publishing','ready'].includes(r.state)&&r.result){
   if(JSON.stringify(r.baseOutputs)!==JSON.stringify(r.importBaseOutputs)||!Array.isArray(r.result.outputs))throw Error('已持久化的候选基线与原输出不一致');
   if(r.candidateManifest!==manifestPath)throw Error('恢复候选的清单路径与已记录版本不一致');
  }
  const dir=path.join(root,r.id,'direct-candidate');
  const checkedFigure=wasActivated?{...f,reviewVersion:r.version,outputs:r.baseOutputs.map(o=>({number:o.number,file:{path:o.path}}))}:f;
  const currentArticle=articles.find(article=>article.id===r.articleId);
  const verify=item.kind==='vector-pdf'?verifyFeedbackPdfCandidate:verifyFeedbackCandidate;
  const {check,outputs}=verify({figure:checkedFigure,record:r,item,manifestPath,candidateRoot,attemptDir:dir,python:qualityPython,articleWord:currentArticle?.word});
  if(wasActivated){
   const persisted=path.join(dir,'published.json');
   if(!fs.existsSync(persisted)||JSON.stringify(JSON.parse(fs.readFileSync(persisted,'utf8')).qualityVerification)!==JSON.stringify(r.qualityVerification))throw Error('已激活候选的持久化检查回执缺失或不同');
   if(r.state==='publishing'){r.state='ready';r.message='自动检查通过，候选已恢复到工作台待用户终审';save();}
   return view(r);
  }
  refresh();const current=rows.find(row=>row.id===r.figureId);
  if(!current||current.reviewVersion!==r.version||(current.feedback?.revision??null)!==r.feedbackRevision||feedbackHash(current.feedback??null)!==r.feedbackHash||JSON.stringify(current.outputs.map(o=>({number:o.number,path:o.file.path,sha256:digest(o.file.path)})))!==JSON.stringify(r.baseOutputs))throw Error('自动检查期间工作台原输出或用户反馈已变化');
  const isVectorPdf=item.kind==='vector-pdf';
  const result=isVectorPdf?{summary:'矢量标题PDF候选已完成图源、Word、反馈、字体、灰度及标题外像素自动检查，待用户终审。',evidence:'PDF标题为可提取的嵌入SimSun Type0文字；正文灰度图与当前输出逐像素一致；300 dpi页面渲染标题区域之外无像素变化。人工终审仍待用户完成。',outputs:outputs.map(output=>({...output,columnLabel:'双栏约110%',fontLabel:'SimSun嵌入'}))}:{summary:'灰度裁剪候选已完成源图、处理规则与输出自动重放检查，待用户终审。',evidence:'已从冻结源图重放裁剪边界、左上区域灰字清理及灰度转换；PNG逐像素匹配，JPG与PNG差异在阈值内。裁剪意图语义待用户终审。',outputs:outputs.map(output=>({...output,columnLabel:'栏宽待核对',fontLabel:''}))};
  const record={at:new Date().toISOString(),jobId:r.id,figureId:r.figureId,feedbackRevision:r.feedbackRevision,feedbackHash:r.feedbackHash,feedbackAttachmentHashes:r.feedbackAttachmentHashes,baseOutputs:r.baseOutputs,qualityVerification:check,result};
  r.state='publishing';r.executor='工作台自动候选检查';r.candidateManifest=manifestPath;r.importBaseOutputs=structuredClone(r.baseOutputs);r.qualityVerification=check;r.result=result;r.message='自动检查通过，候选正在登记回工作台';r.publishedAt=record.at;save();
  atomicJson(path.join(dir,'published.json'),record);
  activate({at:record.at,jobId:r.id,figureId:r.figureId,pendingKey:r.figureId,feedbackRevision:r.feedbackRevision,qualityVerification:check,result});refresh();
  r.state='ready';r.message='自动检查通过，候选已回工作台待用户终审';save();
  return view(r);
 }
 function restorePublished(r){
  const f=figure(r.figureId);
  if(f.outputs.length)return importCandidate(r.id);
  const receipt=JSON.parse(fs.readFileSync(path.join(root,r.id,'direct-candidate','published.json'),'utf8'));
  for(const key of ['figureId','feedbackRevision','feedbackHash','baseOutputs','qualityVerification','result']){
   if(JSON.stringify(receipt[key])!==JSON.stringify(r[key]))throw Error('持久化发布回执与修订记录不一致：'+key);
  }
  if(receipt.jobId!==r.id||JSON.stringify(r.baseOutputs)!==JSON.stringify(r.importBaseOutputs))throw Error('发布身份或修订基线不一致');
  if((f.feedback?.revision??null)!==r.feedbackRevision||feedbackHash(f.feedback??null)!==r.feedbackHash)throw Error('发布后的用户反馈已变化');
  const acceptance=getAcceptance(r.figureId);
  if(acceptance?.accepted===true&&acceptance.version!==candidateVersion(r.result.outputs,r.feedbackRevision))throw Error('验收版本与发布候选不一致');
  assertAvailable(r.figureId);
  const manifestPath=r.candidateManifestPath||(r.candidateManifest?path.resolve(r.candidateManifest):manifestForFigure(r.figureId));
  if(!manifestPath||manifestForFigure(r.figureId)!==manifestPath||digest(manifestPath)!==r.qualityVerification.manifestSha256)throw Error('发布后的候选清单已变化');
  const item=JSON.parse(fs.readFileSync(manifestPath,'utf8')).items?.find(item=>String(item.figure)===String(r.number));
  const baselineJobs=queue.list().filter(j=>j.state==='ready'&&j.articleId===r.articleId&&String(j.figureNumber)===String(r.number)&&j.result?.outputs?.length===r.baseOutputs.length&&r.baseOutputs.every(b=>j.result.outputs.some(o=>o.number===b.number&&o.path===b.path&&o.sha256===b.sha256)));
  const productionRoute=f.productionRoute||(baselineJobs.length===1?baselineJobs[0].productionRoute:null);
  const checkedFigure={...f,productionRoute,reviewVersion:r.version,outputs:r.baseOutputs.map(o=>({number:o.number,file:{path:o.path}}))};
  const verify=item.kind==='vector-pdf'?verifyFeedbackPdfCandidate:verifyFeedbackCandidate;
  const {check}=verify({figure:checkedFigure,record:r,item,manifestPath,candidateRoot:path.dirname(manifestPath),attemptDir:path.dirname(r.result.outputs[0].path),python:qualityPython,articleWord:articles.find(a=>a.id===r.articleId)?.word});
  if(JSON.stringify(check)!==JSON.stringify(r.qualityVerification))throw Error('发布候选重放与原检查回执不一致');
  activate({...receipt,pendingKey:r.figureId});f.productionRoute=productionRoute;refresh();
  r.state='ready';delete r.restoreError;save();
 }
 const common=commonRevisionTools({root,figure,articles,assertAvailable,baseOutputsMatch,alreadyActivated,candidateVersion,getAcceptance,activate,refresh,save,view,qualityPython});
 for(const r of records.filter(r=>r.commonCandidate&&r.result&&['publishing','ready'].includes(r.state))){
  try{common.restore(r);}catch(error){r.restoreError=error.message;save();}
 }
 // Recover the latest published revision even when its superseded baseline cannot
 // be activated under the current acceptance version. Never downgrade the journal.
 for(const r of records.filter(r=>r.result&&['feedback-raster-replay','feedback-vector-pdf'].includes(r.qualityVerification?.kind)&&(['publishing','ready'].includes(r.state)||(r.state==='needs_triage'&&r.message?.startsWith('候选恢复被阻止：'))))){
  try{restorePublished(r);}catch(error){r.restoreError=error.message;save();}
 }
 for(const j of queue.list().filter(j=>j.kind==='revision'&&j.state==='ready'&&j.result).sort((a,b)=>a.updatedAt.localeCompare(b.updatedAt)))activate({jobId:j.id,figureId:j.figureId,pendingKey:j.figureId,feedbackRevision:j.feedbackRevision,result:j.result,qualityVerification:j.qualityVerification||null});
 const json=(res,status,value)=>res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(value));
 return {submit,resolve,publish,prepareCandidate,importCandidate,list:()=>records.map(view),decorate(){for(const f of rows){const r=records.findLast(r=>r.figureId===f.id);if(r)f.revisionJob=r.feedbackRevision===(f.feedback?.revision??null)?view(r):null;f.revisionRoute='coordinator';}},handle(req,res,url){
  const resolution=url.pathname==='/review-triage/resolve',directImport=url.pathname==='/review-triage/import-candidate',preparation=url.pathname==='/review-triage/prepare-candidate';if(!resolution&&!directImport&&!preparation&&!url.pathname.startsWith('/revision-jobs'))return false;
  if(req.method==='GET'&&!resolution){json(res,200,{jobs:records.map(view),legacy:legacyJobs()});return true;}
  const a=Buffer.from(req.headers.authorization||''),b=Buffer.from('Bearer '+token);
  if(req.method!=='POST'||(resolution||directImport||preparation?!(a.length===b.length&&timingSafeEqual(a,b)):req.headers.origin!==origin)){json(res,403,{error:'请求来源未授权'});return true;}
  let size=0,chunks=[];req.on('data',c=>{size+=c.length;if(size<1024*1024)chunks.push(c);});req.on('end',()=>{try{
   if(size>=1024*1024)throw Error('请求过大');const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  const job=resolution?resolve(body.id,body.decision):preparation?prepareCandidate(body.id,body):directImport?importCandidate(body.id,body.candidate):submit(decodeURIComponent(url.pathname.slice('/revision-jobs/'.length)),body.version,body.reason);
   json(res,202,{job});
  }catch(e){json(res,409,{error:e.message});}});return true;
 }};
}
