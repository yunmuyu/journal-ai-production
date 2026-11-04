import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const samePath=(a,b)=>typeof a==='string'&&typeof b==='string'&&path.resolve(a)===path.resolve(b);
const columnLabel=value=>typeof value==='string'&&value?value.replace(/((?:单|双)栏约)(\d+(?:\.\d+)?)%/g,(_all,prefix,percent)=>prefix+Math.round(Number(percent)/10)*10+'%'):'栏宽待核对';
function verify(ref){
 if(!ref?.path||! /^[a-f0-9]{64}$/.test(ref.sha256||'')||hash(ref.path)!==ref.sha256)throw Error('归并来源或预览哈希不符');
}

// Import existing candidates, never reviews/approval. All checks precede model writes.
export function activateRelatedCandidates({articles,rows,metadata,link,feedbackRecords,acceptanceRecords},manifest,{receipt}={}){
 if(!feedbackRecords||!acceptanceRecords)throw Error('归并须提供当前批注和验收记录，不能跳过冲突检查');
 if(manifest?.version!==1||!Array.isArray(manifest.articles))throw Error('归并清单格式无效');
 // Caller persists this receipt in its private state, never accepts one from a worker.
 // This binds recovery to the exact import, not a signature or grant of approval.
 const expectedReceipt={version:1,manifestSha256:createHash('sha256').update(JSON.stringify(manifest)).digest('hex'),articles:manifest.articles.map(a=>({targetArticleId:a.targetArticleId,oldArticleId:a.oldArticleId,wordSha256:a.word?.sha256,figures:(a.figures||[]).map(f=>({oldFigureId:f.oldFigureId,targetFigureId:f.targetFigureId}))}))};
 if(receipt!==undefined&&JSON.stringify(receipt)!==JSON.stringify(expectedReceipt))throw Error('归并恢复回执与清单或稿件身份不符');
 const restoring=receipt!==undefined;
 const pending=[],skipped=[],ids=new Set(),outputPaths=new Set();
 for(const source of manifest.articles){
  const article=articles.find(a=>a.id===source.targetArticleId);
  const expected='PKG-'+createHash('sha256').update(source.archiveSha256+'\0'+source.member).digest('hex').slice(0,20);
  if(!article||article.id!==expected||ids.has(article.id)||article.archiveHash!==source.archiveSha256||!samePath(article.word?.path,source.word?.path))throw Error('归并稿件身份不匹配');
  ids.add(article.id);verify(source.word);
  if(article.relatedImport){
   if(article.relatedImport.oldArticleId!==source.oldArticleId||article.relatedImport.wordSha256!==source.word.sha256)throw Error('归并历史身份冲突');
   skipped.push(article.id);continue; // Existing later revisions/feedback remain authoritative.
  }
  if(article.figures.length||rows.some(f=>f.articleId===article.id))throw Error('归并目标已有图件，须人工核对版本冲突');
  if(!Array.isArray(source.figures)||!source.figures.length)throw Error('归并图件清单为空');
  const figureIds=new Set();
  for(const f of source.figures){
   if(f.targetFigureId!==article.id+'-F'+f.mainNumber||figureIds.has(f.targetFigureId))throw Error('归并图号重复或身份不匹配');
   figureIds.add(f.targetFigureId);
   if((!restoring&&(feedbackRecords[f.targetFigureId]||acceptanceRecords[f.targetFigureId]))||f.currentFeedback||f.currentAcceptance)throw Error('归并目标已有批注或验收，禁止覆盖');
   if(f.legacyFeedback||f.legacyAcceptance)throw Error('旧批注或验收须先映射保全，禁止静默丢弃');
   if(!Array.isArray(f.outputs)||!f.outputs.length)throw Error('归并输出为空');
   const numbers=new Set();
   for(const o of f.outputs){
    verify(o.output);verify(o.preview);
    if(!/\.(pdf|jpe?g)$/i.test(o.output.path)||!o.proposedOutputNumber||numbers.has(o.proposedOutputNumber)||outputPaths.has(path.resolve(o.output.path)))throw Error('归并输出格式或编号重复');
    numbers.add(o.proposedOutputNumber);outputPaths.add(path.resolve(o.output.path));
    if(metadata[o.output.path]&&metadata[o.output.path].sha256!==o.output.sha256)throw Error('归并元数据已有不同版本');
   }
  }
  pending.push({article,source});
 }
 for(const {article,source} of pending){
  const figures=source.figures.map(f=>{
   const outputs=f.outputs.map(o=>{
    metadata[o.output.path]={sha256:o.output.sha256,previewPath:o.preview.path,format:path.extname(o.output.path).slice(1).toUpperCase(),columnLabel:columnLabel(o.existingMetadata?.columnLabel),fontLabel:''};
    return {number:o.proposedOutputNumber,file:link(pathToFileURL(o.output.path))};
   });
   const aliases=f.outputs.filter(o=>o.legacyOutputNumber&&o.legacyOutputNumber!==o.proposedOutputNumber).map(o=>({text:`旧输出图${o.legacyOutputNumber}对应Word图${f.mainNumber}（当前输出图${o.proposedOutputNumber}），原文件名保留。`}));
   return {id:f.targetFigureId,articleId:article.id,author:article.author,editor:article.editor,number:f.mainNumber,type:'历史成稿复用候选',status:'待终检',outputs,notices:[{text:'既有成稿已归入当前工作台，待终审。历史检查说明不代表当前质量结论。'},...aliases],feedback:feedbackRecords[f.targetFigureId]||null,reason:'',batchCandidate:true,
    relatedProvenance:{url:manifest.legacy,oldArticleId:source.oldArticleId,oldFigureId:f.oldFigureId,oldReviewVersion:f.legacyReviewVersion,legacyFeedback:null,legacyAcceptance:null,historicalNotice:f.historicalNotice,revokedSmallFontFailure:!!f.revokedSmallFontFailure,outputs:f.outputs.map(o=>({number:o.legacyOutputNumber,currentNumber:o.proposedOutputNumber,output:o.output,preview:o.preview}))}};
  });
  article.figures.push(...figures);rows.push(...figures);article.state='待核验';
  article.relatedImport={oldArticleId:source.oldArticleId,wordSha256:source.word.sha256,url:manifest.legacy};
  article.notices=[{text:'既有图件已归入本工作台，未自动验收；旧稿和历史记录保留。'}];delete article.externalReviewUrl;
 }
 return {imported:restoring?[]:pending.map(p=>p.article.id),restored:restoring?pending.map(p=>p.article.id):[],skipped,receipt:expectedReceipt,figures:pending.reduce((n,p)=>n+p.source.figures.length,0),outputs:pending.reduce((n,p)=>n+p.source.figures.reduce((m,f)=>m+f.outputs.length,0),0)};
}
