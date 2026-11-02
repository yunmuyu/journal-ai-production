import {assertProductionRoute,productionInstructions,routeSourceRefs} from './production-route.mjs';
export function buildFigureTasks(catalog,plan){
 if(!Array.isArray(plan.articles)||plan.articles.length!==catalog.articles.length)throw Error('分组清单必须覆盖本批每篇文章；缺项须明确标注');
 const seen=new Set(),tasks=[];
 for(const paper of plan.articles){
  const source=catalog.articles.find(a=>a.id===paper.articleId);if(!source||seen.has(paper.articleId))throw Error('文章身份不一致或重复');seen.add(paper.articleId);
  if(!paper.evidence?.trim()||!Array.isArray(paper.figures))throw Error('缺少本篇图号核对证据');
  if(paper.blocked){if(!paper.problem?.trim()||paper.figures.length)throw Error('无法核对的文章须明确问题且不得猜测图号');continue;}
  if(!paper.figures.length&&!paper.noFiguresConfirmed)throw Error('空图号清单须明确确认无图或说明阻塞');
  const numbers=new Set(),outputs=new Set();
  for(const figure of paper.figures){
   if(!/^\d+(?:[.-]\d+)*$/.test(figure.number)||numbers.has(figure.number))throw Error('主图号重复或非法');numbers.add(figure.number);
   if(!figure.evidence?.trim())throw Error('缺少图源和图种判断依据');
   if(figure.blocked){if(!figure.problem?.trim())throw Error('待补充图件必须明确问题');continue;}
   if(!catalog.groups.includes(figure.group)||!Array.isArray(figure.outputNumbers)||!figure.outputNumbers.length||new Set(figure.outputNumbers).size!==figure.outputNumbers.length||figure.outputNumbers.some(n=>!/^\d+(?:[.-]\d+)*$/.test(n)))throw Error('图种、加工方式或导出编号未明确');
   for(const number of figure.outputNumbers){if(outputs.has(number)||!(number===figure.number||number.startsWith(figure.number+'.')||number.startsWith(figure.number+'-')))throw Error('输出编号重复或不属于本图');outputs.add(number);}
   const key=catalog.batchHash+':'+source.id+':'+figure.number;
   if(catalog.completedKeys.includes(key))continue;
   const task={key,label:`${source.author} 图${figure.number}`,group:figure.group,articleId:source.id,figureNumber:figure.number,mainNumbers:paper.figures.map(f=>f.number),outputNumbers:figure.outputNumbers,productionRoute:figure.productionRoute,legacyProductionInstructions:catalog.productionInstructions};
   const route=assertProductionRoute(task);
   if(route.sourceReview.archive.sha256!==catalog.archive.sha256||route.sourceReview.word.sha256!==source.word.sha256)throw Error('路线原包或Word与批次不一致');
   task.sources=[...new Map([source.word,catalog.archive,...routeSourceRefs(route)].map(s=>[s.path,s])).values()];
   delete task.legacyProductionInstructions;
   task.instructions=productionInstructions(route);
   task.sourceEvidence=figure.evidence;task.articleEvidence=paper.evidence;
   tasks.push(task);
  }
 }
 return tasks;
}
