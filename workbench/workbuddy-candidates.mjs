import path from 'node:path';
import {pathToFileURL} from 'node:url';
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
