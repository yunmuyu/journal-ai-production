import path from 'node:path';
import {pathToFileURL} from 'node:url';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
export function registerInventoryFigures({articles,rows},jobs){
 for(const inventory of jobs.filter(job=>job.kind==='inventory'&&Array.isArray(job.result?.articles))){
  for(const paper of inventory.result.articles){
   const article=articles.find(a=>a.id===paper.articleId);if(!article)continue;
   for(const item of paper.figures||[]){
    if(!/^\d+(?:[.-]\d+)*$/.test(item.number))continue;
    const blocked=item.blocked&&!jobs.some(job=>job.kind!=='inventory'&&job.articleId===paper.articleId&&job.figureNumber===item.number);
    const existing=article.figures.find(figure=>figure.number===item.number);
    if(existing){if(!existing.outputs.length&&blocked&&item.problem){existing.reason=item.problem;existing.notices=[{text:item.problem}];}continue;}
    const reason=blocked?item.problem||'来源核对受阻':item.evidence||'';
    const figure={id:article.id+'-F'+item.number,articleId:article.id,author:article.author,editor:article.editor,number:item.number,type:item.group||'待核对',status:'待制作',outputs:[],notices:reason?[{text:reason}]:[],feedback:null,reason,batchCandidate:true};
    article.figures.push(figure);rows.push(figure);
   }
  }
 }
}
export function activateWorkBuddy({articles,rows,metadata,link},job,result){
 const article=articles.find(a=>a.id===job.articleId);if(!article)throw Error('任务文章不存在');
 for(const number of job.mainNumbers){
  if(article.figures.some(f=>f.number===number))continue;
  const figure={id:article.id+'-F'+number,articleId:article.id,author:article.author,editor:article.editor,number,type:'待核对',status:'待制作',outputs:[],notices:[],feedback:null,reason:'',batchCandidate:true};article.figures.push(figure);rows.push(figure);
 }
 const figure=article.figures.find(f=>f.number===job.figureNumber);if(!figure)throw Error('主图号未登记');
 if(figure.outputs.length){figure.previousOutputs=figure.outputs;figure.revisionHistory=[...(figure.revisionHistory||[]),...figure.outputs];}
 for(const o of result.outputs)metadata[o.path]={sha256:o.sha256,previewPath:o.preview,format:path.extname(o.path).slice(1).toUpperCase(),columnLabel:o.columnLabel||'栏宽待核对',fontLabel:/\.pdf$/i.test(o.path)?o.fontLabel||'':''};
 const notice=job.kind!=='revision'&&job.productionRoute?.method==='raster-preserve'?'JPG 候选已回传，待终审。':result.summary||'WorkBuddy 制作回传，待终审';
 figure.outputs=result.outputs.map(o=>({number:o.number,file:link(pathToFileURL(o.path))}));figure.status='待终检';figure.type=job.group;figure.notices=[{text:notice}];figure.batchCandidate=true;
 if(job.productionRoute)figure.productionRoute=job.productionRoute;
 article.state=article.figures.some(f=>!f.outputs.length)?'制作中':'待核验';article.notices=[{text:'按图种分组制作中；本篇仍有待核对图件时，不代表整篇完成。'}];
}

// Host adapter for safe direct-candidate recovery. It reads authoritative stores,
// never caller-supplied output paths or hashes.
export function directPublicationState({articles,metadata,feedbackStore,reviewStore,pending},job){
 const article=articles.find(value=>value.id===job.articleId);
 const figure=article?.figures.find(value=>String(value.number)===String(job.figureNumber));
 if(!figure)return null;
 const feedback=feedbackStore?.get(figure.id)??figure.feedback??null;
 const acceptance=reviewStore?.get(figure.id)??null;
 const revision=pending?.[figure.id]??pending?.[figure.author+'-'+figure.number]??null;
 return {
  status:figure.status,
  outputs:(figure.outputs||[]).map(output=>{
   const file=output.file,path=file?.path;
   return {number:output.number,path,sha256:path?(metadata?.[path]?.sha256??file?.meta?.sha256):undefined};
  }),
  feedback,
  feedbackRevision:feedback?.revision??0,
  accepted:acceptance?.accepted===true,
  approved:figure.status==='终检通过',
  userAcceptance:acceptance,
  revisionHistory:revision
 };
}

export function acceptedDirectVersionMatches(snapshot,result){
 return snapshot?.accepted===true&&snapshot?.userAcceptance?.accepted===true&&recordedDirectVersionMatches(snapshot,result);
}

export function recordedDirectVersionMatches(snapshot,result){
 const acceptance=snapshot?.userAcceptance,revision=snapshot?.feedbackRevision??0;
 if(!acceptance?.version||!Number.isSafeInteger(revision)||revision<0||!Array.isArray(result?.outputs)||!result.outputs.length)return false;
 const outputs=[];
 for(const output of result.outputs){
  if(typeof output.number!=='string'||typeof output.path!=='string'||!/^[a-f0-9]{64}$/.test(output.sha256||''))return false;
  try{const sha256=createHash('sha256').update(fs.readFileSync(output.path)).digest('hex');if(sha256!==output.sha256)return false;outputs.push([output.number,output.path,sha256]);}catch{return false;}
 }
 const version=createHash('sha256').update(JSON.stringify([outputs,revision])).digest('hex');
 return acceptance.version===version;
}

export function restoreAcceptedDirectWorkBuddy(context,job,result){
 const snapshot=directPublicationState(context,job);
 if(!acceptedDirectVersionMatches(snapshot,result))throw Error('用户验收版本与持久化候选文件或反馈版本不一致，拒绝恢复');
 const article=context.articles.find(value=>value.id===job.articleId),figure=article?.figures.find(value=>String(value.number)===String(job.figureNumber));
 if(!figure)throw Error('验收图件尚未由来源清单登记');
 if(figure.outputs?.length){
  const exact=figure.outputs.length===result.outputs.length&&result.outputs.every((expected,index)=>{
   const current=figure.outputs[index],file=current?.file,path=file?.path;
   return current?.number===expected.number&&path===expected.path&&context.metadata?.[path]?.sha256===expected.sha256;
  });
  if(!exact)throw Error('当前图件已有其他输出，拒绝覆盖用户验收版本');
  figure.status='终检通过';return figure;
 }
 for(const output of result.outputs)context.metadata[output.path]={sha256:output.sha256,previewPath:output.preview,format:path.extname(output.path).slice(1).toUpperCase(),columnLabel:output.columnLabel||'栏宽待核对',fontLabel:/\.pdf$/i.test(output.path)?output.fontLabel||'':''};
 figure.outputs=result.outputs.map(output=>({number:output.number,file:context.link(pathToFileURL(output.path))}));
 figure.status='终检通过';figure.type=job.group;figure.batchCandidate=true;
 if(job.productionRoute)figure.productionRoute=job.productionRoute;
 return figure;
}
