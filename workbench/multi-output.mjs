import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const digest=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sameRef=(a,b)=>a&&b&&path.resolve(a.path)===path.resolve(b.path)&&a.sha256===b.sha256;

export function assertCompleteOutputSet(task,outputRoutes=task.outputRoutes,{python}={}){
 const evidenceRef=task.outputSetEvidence;
 if(!evidenceRef||typeof evidenceRef.path!=='string'||!/^[a-f0-9]{64}$/.test(evidenceRef.sha256||''))throw Error('缺少Word绑定的完整输出集合证据');
 if(digest(evidenceRef.path)!==evidenceRef.sha256)throw Error('完整输出集合证据哈希变化');
 const evidence=JSON.parse(fs.readFileSync(evidenceRef.path,'utf8'));
 const published=evidence.publishNumbers;
 const evidenceOutputs=published===undefined?evidence.outputs:evidence.outputs?.filter(item=>published.includes(item.number));
 if(published!==undefined&&(!Array.isArray(published)||JSON.stringify(published)!==JSON.stringify(task.outputNumbers)||new Set(published).size!==published.length||!evidenceOutputs||evidenceOutputs.length!==published.length))throw Error('分次回传范围必须精确绑定本次输出及完整Word集合');
 const routes=outputRoutes,base=task.productionRoute.sourceReview;
 if(!Array.isArray(routes)||routes.length!==task.outputNumbers.length)throw Error('逐输出制作路线必须覆盖完整导出集合');
 const shared=[base.archive,base.word,base.inventory];
 for(let index=0;index<routes.length;index++){
  const entry=routes[index],number=task.outputNumbers[index];
  const sourceReview=entry?.productionRoute?.sourceReview;
  if(entry?.number!==number||!sourceReview||!sameRef(shared[0],sourceReview.archive)||!sameRef(shared[1],sourceReview.word)||!sameRef(shared[2],sourceReview.inventory))throw Error('逐输出路线顺序或文章来源身份不匹配');
 }
 if(evidence.version!==1||evidence.articleId!==task.articleId||evidence.figureNumber!==task.figureNumber||
   !sameRef(evidence.word,base.word)||!Array.isArray(evidenceOutputs)||evidenceOutputs.length!==task.outputNumbers.length)throw Error('完整输出集合证据与文章、图号或当前Word不符');
 for(let index=0;index<task.outputNumbers.length;index++){
  const item=evidenceOutputs[index],route=routes[index].productionRoute;
  if(item?.number!==task.outputNumbers[index]||typeof item.basis!=='string'||!item.basis.trim())throw Error('Word图件、完整输出集合与逐输出源件映射不完整');
  if(['word-inline-columns','word-labelled-segments'].includes(evidence.grouping)){
   const members=item.members,selected=[route.sourceReview.selected,...(route.sourceReview.additionalSelected??[])];
   if(!Array.isArray(members)||members.length<(evidence.grouping==='word-labelled-segments'?1:2)||members.length!==selected.length||members.some((part,i)=>typeof part.wordMedia!=='string'||!part.wordMedia||!/^[a-f0-9]{64}$/.test(part.wordMediaSha256||'')||!sameRef(part.source,selected[i])||(part.originPdf&&!route.sourceReview.candidates.some(c=>c.decision==='not-applicable'&&sameRef(c,part.originPdf)))))throw Error('多媒体子图来源集合或顺序不完整');
  }else if(typeof item.wordMedia!=='string'||!item.wordMedia||!/^[a-f0-9]{64}$/.test(item.wordMediaSha256||'')||!sameRef(item.source,route.sourceReview.selected))throw Error('Word图件、完整输出集合与逐输出源件映射不完整');
 }
 if(typeof python!=='string'||!python.trim())throw Error('多输出安全入口必须配置可信Python以独立核对当前Word媒体及题注');
 try{
  execFileSync(python,[fileURLToPath(new URL('./verify-word-output-set.py',import.meta.url)),base.word.path,evidenceRef.path],
   {windowsHide:true,encoding:'utf8',timeout:120000,maxBuffer:1024*1024,env:{...process.env,PYTHONUTF8:'1'}});
 }catch(error){throw Error('当前Word题注/媒体集合无法独立核实：'+String(error.stderr||error.stdout||error.message).slice(0,1200));}
 return {ref:{path:path.resolve(evidenceRef.path),sha256:evidenceRef.sha256},evidence};
}
