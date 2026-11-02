import path from 'node:path';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
export function registerArchiveArticles({articles,link,wordTokens},batch){
 const counts=new Map();for(const m of batch.manuscripts)counts.set(m.author,(counts.get(m.author)||0)+1);
 for(const m of batch.manuscripts){
  const id='PKG-'+createHash('sha256').update(batch.archiveSha256+'\0'+m.member).digest('hex').slice(0,20);
  if(articles.some(a=>a.id===id))continue;
  const word=link(pathToFileURL(m.wordPath));if(word)wordTokens.add(word.token);
  articles.push({id,word,author:m.author,title:m.title,label:counts.get(m.author)>1?`${m.author} · ${m.title}`:m.author,editor:batch.editor,state:'未完成',figures:[],archiveHash:batch.archiveSha256,notices:[{text:'原包已登记，图号和图源待核对。尚未开始制作。'}]});
 }
}
// Existing workbenches remain authoritative. Match exact Word paths, never author alone.
export async function syncRelatedReviews(articles,urls,cachePath){
 const cache=cachePath&&fs.existsSync(cachePath)?JSON.parse(fs.readFileSync(cachePath,'utf8')):{};
 for(const url of urls||[]){
  let remote=cache[url],online=false;
  try{const response=await fetch(new URL('/data',url),{signal:AbortSignal.timeout(1500)});if(response.ok){const data=await response.json();remote={articles:(data.articles||[]).map(a=>({word:a.word,state:a.state,figureCount:a.figures.length}))};cache[url]=remote;online=true;}}catch{}
  if(!remote)continue;
  for(const article of articles.filter(a=>a.archiveHash)){
   const match=remote.articles?.find(a=>a.word?.path&&article.word?.path&&path.resolve(a.word.path).toLowerCase()===path.resolve(article.word.path).toLowerCase());
   if(!match)continue;
   article.externalReviewUrl=url;article.state=match.state;article.notices=[{text:`已有 ${match.figureCount} 张图件的制作记录。原工作台保留图稿、批注和验收，请打开已有图件继续查看。${online?'':'原工作台暂未连接，此处保留上次同步状态。'}`}];
  }
 }
 if(cachePath){const value=JSON.stringify(cache);if(!fs.existsSync(cachePath)||fs.readFileSync(cachePath,'utf8')!==value){fs.writeFileSync(cachePath+'.tmp',value);fs.renameSync(cachePath+'.tmp',cachePath);}}
}
