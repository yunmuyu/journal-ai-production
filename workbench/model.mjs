import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {groupArticles} from './articles.mjs';
import {buildWorkspace,authorState,figureType} from './workspace.mjs';
import {recordRoot,resolveLocal,readLocalJson} from './paths.mjs';
export const root=recordRoot;
const productionRoot=path.resolve('work/october-production');
const read=readLocalJson;
const hashCache=new Map();
const cachedHash=p=>{const stat=fs.statSync(p),key=stat.mtimeMs+':'+stat.size;const cached=hashCache.get(p);if(cached?.key===key)return cached.hash;const hash=createHash('sha256').update(fs.readFileSync(p)).digest('hex');hashCache.set(p,{key,hash});return hash;};
const exists=p=>typeof p==='string'&&fs.existsSync(p);
export function classify(text){
 if(/已暂停|生产暂停/.test(text))return '生产中';
 if(/暂缓|待确认|不支持/.test(text))return '暂缓';
 if(/待修订/.test(text))return '待修订';
 if(/异常|失败|已修改待复核/.test(text))return '异常';
 if(/最终验收通过|用户.*通过|终检通过/.test(text))return '终检通过';
 if(/复核通过|待终检/.test(text))return '待终检';
 if(/生产中|制作中|rendering|running/.test(text))return '生产中';
 return '待制作';
}
export function loadModel(){
 const inventory=read(root+'/inventory.json'),production=read(root+'/production-results.json'),templates=read(root+'/author-templates.json');
 const deferred=new Map(),inProgress=new Set(),extraSources=new Map();
 for(const dir of fs.readdirSync(productionRoot,{withFileTypes:true}).filter(x=>x.isDirectory())){
  const base=path.join(productionRoot,dir.name);
  if(exists(base+'/deferred.json'))for(const f of read(base+'/deferred.json'))deferred.set(f.articleId+'-F'+f.number,f);
  for(const file of ['image-results.json','plan-results.json'])if(exists(base+'/'+file))for(const f of read(base+'/'+file)){
   if(f.result?.ok&&exists(f.result.output)){const id=f.articleId+'-F'+String(f.number).split('.')[0];inProgress.add(id);if(f.source)extraSources.set(id,f.source);}
  }
  if(exists(base+'/queue.json'))for(const f of read(base+'/queue.json')){if(['rendering','running'].includes(f.status))inProgress.add(f.articleId+'-F'+String(f.number).split('.')[0]);if(f.source)extraSources.set(f.articleId+'-F'+String(f.number).split('.')[0],f.source);}
 }
 const preflight=new Map();
 for(const name of ['hardware','vision','applications']){
  const file=path.resolve('work/parallel-research-20261009/worktrees/'+name+'/experiments/preflight.json');
  if(exists(file)){const checked=read(file);for(const f of checked.figures||checked.figureSources||[])preflight.set(f.author+'-F'+f.number,f);}
 }
 const figures=new Map(inventory.figures.map(f=>[f.id,f]));
 for(const [id,f]of deferred)if(!figures.has(id))figures.set(id,{id,articleId:f.articleId,number:f.number,caption:'批次补登记图号'});
 const files=new Map();
 function link(p){const local=p&&resolveLocal(p);if(!exists(local))return null;const resolved=path.resolve(local);const token=createHash('sha256').update(resolved).digest('hex').slice(0,24);files.set(token,resolved);return {token,name:path.basename(resolved),path:resolved};}
 const rows=[];
 for(const f of figures.values()){
  const a=inventory.articles.find(a=>a.id===f.articleId);if(!a)continue;
  const stored=production.figures[f.id];
  const p=stored&&Object.keys(stored).some(key=>key!=='productionDecision')?stored:undefined,defer=deferred.get(f.id);
  const child=p?.subfigures?.length?p.subfigures:[p].filter(Boolean);
  const outputs=child.map(c=>({number:c.number||path.basename(c.output||'').match(/图(\d+(?:\.\d+)*)/)?.[1]||f.number,file:link(c.output)}));
  const ai=link(production.articles[f.articleId]?.ai)||link(p?.ai)||link(templates[f.articleId]?.path);
  const folder=link(ai?path.dirname(ai.path):path.dirname(a.localWord));
  const outputDir=outputs.find(c=>c.file)?.file.path;
  const summary=link(production.articles[f.articleId]?.summary)||(outputDir?link(path.join(path.dirname(outputDir),a.author+'-核对汇总.pdf')):null);
  let status=classify(p?.status||'');
  let reason=defer?.reason||'';
  if(/已暂停|生产暂停/.test(p?.status||'')&&!reason)reason='生产已暂停，尚未完成审核收尾';
  if(!p&&defer)status='暂缓';
  if(!p&&inProgress.has(f.id))status='生产中';
  if(p&&outputs.some(c=>!c.file)){status='异常';reason='交付记录中的文件缺失';}
  if(p)for(const c of child){const local=c.output&&resolveLocal(c.output);if(c.outputHash&&exists(local)&&cachedHash(local)!==c.outputHash){status='异常';reason='成品已发生变化，需要重新核对';}}
  const source=link(p?.sourceAi)||link(p?.source)||link(extraSources.get(f.id));
  const word=link(a.localWord);
  const modified=outputs.filter(c=>c.file).map(c=>fs.statSync(c.file.path).mtimeMs);
  const updated=p?.reviewedAt||p?.userAcceptance?.at|| (modified.length?new Date(Math.max(...modified)).toISOString():inventory.scannedAt);
  const feedback=p?.userFeedback?{...p.userFeedback,attachments:(p.userFeedback.attachments||[]).map(a=>({...a,file:link(a.path)}))}:null;
  rows.push({type:figureType(f,p,preflight.get(a.author+'-F'+f.number)),feedback,id:f.id,articleId:f.articleId,editor:a.editor,author:a.author,number:f.number,caption:f.caption,status,reason,updated,source,word,outputs,ai,folder,summary,review:p?.review||'',sourceLabel:source?'已记录图源':'原稿Word（附件尚未配对）'});
 }
 rows.sort((a,b)=>(a.status==='待终检'?0:1)-(b.status==='待终检'?0:1)||a.editor.localeCompare(b.editor,'zh')||a.author.localeCompare(b.author,'zh')||a.number.localeCompare(b.number,undefined,{numeric:true}));
 const articles=groupArticles(rows,inventory.articles).map(a=>({...a,notices:production.articles[a.id]?.notices||[],state:authorState(a.figures)}));
 return {data:{updatedAt:new Date().toISOString(),productionControl:production.productionControl||null,rows,articles,workspace:buildWorkspace(rows,production,link,inventory)},files};
}

