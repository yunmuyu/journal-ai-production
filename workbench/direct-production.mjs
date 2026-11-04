import fs from 'node:fs';
import path from 'node:path';
import {belongsToBatch} from './batch-scope.mjs';
import {digest} from './revision-worker.mjs';
import {assertOutputRoutes,assertProductionRoute,productionInstructions,routeSourceRefs} from './production-route.mjs';

const sameRef=(a,b)=>a&&b&&fs.realpathSync(a.path)===fs.realpathSync(b.path)&&a.sha256===b.sha256;
const hasEntries=value=>Array.isArray(value)?value.length>0:value&&typeof value==='object'?Object.keys(value).length>0:Boolean(value);
const hasFeedback=value=>Boolean(value&&(value.text?.trim()||hasEntries(value.annotations)||hasEntries(value.points)||hasEntries(value.attachments)||value.revision>0));

export function prepareDirectProduction(job,route,{root,jobs,config,assertCurrent,outputRoutes}){
 if(!config?.enabled||!config.batchHashes?.some(hash=>belongsToBatch(job,hash))||!config.groups?.includes(job.group))throw Error('图件不在直接制作范围');
 if(job.state==='ready'&&job.result)return {alreadyReturned:true,job:structuredClone(job)};
 if(job.executionMode==='direct'&&job.state==='running'){
  if(JSON.stringify(job.productionRoute)!==JSON.stringify(route))throw Error('直接制作已开始，不能更换路线');
  return {resumed:true,job:structuredClone(job)};
 }
 const retry=job.executionMode==='direct'&&job.state==='failed'&&Number.isSafeInteger(job.attempt)&&job.attempt>0&&JSON.stringify(job.productionRoute)===JSON.stringify(route);
 if(retry&&(!job.attemptDir||fs.existsSync(path.join(job.attemptDir,'.direct-run.lock'))||fs.existsSync(path.join(job.attemptDir,'.direct-run.lock.recovery.lock'))))throw Error('旧直接执行尚未安全结束，不能重试');
 const routes=outputRoutes??job.outputRoutes;
 const rebind=job.state==='review_pending'&&job.attempt===1&&JSON.stringify(job.productionRoute)===JSON.stringify(route)&&job.candidateResult?.outputs?.length===job.outputNumbers.length;
 if((!retry&&!rebind&&(!['paused','queued'].includes(job.state)||job.attempt!==0))||job.kind&&job.kind!=='production'||job.result||(!rebind&&job.candidateResult)||job.approved||job.accepted||hasFeedback(job.feedback)||job.feedbackRevision||job.revisionHistory?.length)throw Error('直接入口仅处理尚未生产且无反馈的原任务');
 if(rebind&&digest(job.candidateResult.outputs[0].path)!==job.candidateResult.outputs[0].sha256)throw Error('原候选文件已变化');
 if(jobs.some(other=>other.id!==job.id&&other.articleId===job.articleId&&other.figureNumber===job.figureNumber&&(other.attempt>0||other.state!=='paused'||other.result||other.candidateResult)))throw Error('同图已有其他任务或成稿');
 assertProductionRoute({...job,legacyProductionInstructions:undefined,productionRoute:route});
 if(route.method!=='raster-preserve')throw Error('直接入口仅处理JPG候选');
 const checkedRoutes=assertOutputRoutes({...job,productionRoute:route},routes);
 const anchors=assertCurrent(structuredClone(job),structuredClone(route));
 if(!anchors||anchors.then||!['archive','word'].every(key=>sameRef(anchors[key],route.sourceReview[key])&&job.sources.some(source=>sameRef(source,anchors[key]))))throw Error('直接制作须绑定原任务原包及Word');
 for(const source of job.sources)if(digest(source.path)!==source.sha256)throw Error('原任务来源已变化');
 if(rebind){job.priorCandidateResult=structuredClone(job.candidateResult);delete job.candidateResult;}
 if(!retry&&!job.directPrevious)job.directPrevious={instructions:job.instructions,productionRoute:job.productionRoute||null,
  outputNumbers:job.outputNumbers||[],outputRoutes:job.outputRoutes||null,outputSetEvidence:job.outputSetEvidence||null};
 job.productionRoute=structuredClone(route);job.outputRoutes=structuredClone(checkedRoutes);job.instructions=productionInstructions(route);job.executor='Codex';delete job.legacyProductionInstructions;
 job.sources=[...new Map([...job.sources,...checkedRoutes.flatMap(entry=>routeSourceRefs(entry.productionRoute))].map(source=>[fs.realpathSync(source.path),source])).values()];
 job.attempt++;job.attemptDir=path.join(root,job.id,String(job.attempt));fs.mkdirSync(job.attemptDir,{recursive:true});
 job.executionMode='direct';job.returnMode='automatic-candidate';job.state='running';job.pauseRequested=false;
 delete job.lease;
 return {job:structuredClone(job)};
}
