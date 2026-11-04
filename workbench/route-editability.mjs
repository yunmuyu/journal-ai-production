export function assertRouteEditableState(job,figure,articles){
 if(!figure){
  if((!job.kind||job.kind==='production')&&articles.some(article=>article.id===job.articleId))return;
  throw Error('图件不存在或已批准，不能修改制作路线');
 }
 if(figure.status==='终检通过')throw Error('图件不存在或已批准，不能修改制作路线');
 if(job.kind==='revision'||figure.feedback?.text?.trim()||figure.feedback?.annotations?.length)throw Error('存在终审修订约束，请保留已分流路线，报告具体冲突');
}
