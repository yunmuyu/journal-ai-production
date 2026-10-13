import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
const marker='jfw-current-delivery-v1';
const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const safe=value=>String(value).replace(/[<>:"|?*]/g,'_').split('/').join('_').split(String.fromCharCode(92)).join('_').replace(/[. ]+$/,'').replace(/^$/,'unnamed');
function approved(f){return f.userAcceptance?.accepted===true||(f.userAcceptance?.accepted!==false&&/最终验收通过|终检通过/.test(f.status||''));}
function inside(root,relative){const resolved=path.resolve(root,relative);if(!resolved.startsWith(path.resolve(root)+path.sep))throw Error('Delivery path escapes managed root');return resolved;}
function inventoryPlan({records,inventory,resolve=p=>p}){
 const items=[],issues=[],excluded=[];const articles=new Map(inventory.articles.map(a=>[a.id,a])),figures=new Map(inventory.figures.map(f=>[f.id,f]));
 for(const [id,f]of Object.entries(records.figures||{})){
  const state=approved(f)?'approved':/内部复核通过|待终检/.test(f.status||'')?'review':null;if(!state)continue;
  const mainId=id.replace(/[.][0-9]+$/,'');if(!figures.has(id)&&mainId!==id&&figures.has(mainId)&&records.figures[mainId]){excluded.push({id,reason:'legacy-child-shadow',authority:mainId});continue;}const figure=figures.get(id),article=articles.get(figure?.articleId);if(!article){issues.push({id,error:'Missing authoritative author identity'});continue;}
  const parts=f.subfigures?.length?f.subfigures:[f],planned=[],numbers=new Set();
  try{for(const c of parts){const number=String(c.number||figure.number),source=resolve(c.output);if(!/^(?:4-1|\d+(?:\.\d+)?)$/.test(number)||numbers.has(number))throw Error('Invalid or duplicate output number');numbers.add(number);
   if(!source||!fs.existsSync(source)||!fs.statSync(source).isFile())throw Error('Current output missing: '+number);
   if(!/^[a-f0-9]{64}$/.test(c.outputHash||'')||hash(source)!==c.outputHash)throw Error('Current output hash missing/mismatching: '+number);
   const extension=path.extname(source).toLowerCase();if(!['.pdf','.jpg','.jpeg','.png','.tif','.tiff'].includes(extension))throw Error('Unsupported layout file');
   const relative=path.join(state==='approved'?'排版定稿':'待终检',safe(article.author)+'_'+safe(article.id),safe(article.author)+'-图'+number+extension);
   planned.push({id,articleId:article.id,author:article.author,number,state,source,sha256:c.outputHash,relative,acceptanceAt:f.userAcceptance?.at||null});
  }items.push(...planned);}catch(error){issues.push({id,error:error.message});}
 }
 items.sort((a,b)=>(a.articleId+' '+a.number).localeCompare(b.articleId+' '+b.number,'zh',{numeric:true}));const destinations=new Set();for(const item of items){const key=item.relative.toLowerCase();if(destinations.has(key))throw Error('Duplicate delivery identity');destinations.add(key);}return {items,issues,excluded};
}
export function syncCurrentDelivery(options,{copy=fs.copyFileSync}={}){
 const root=path.resolve(options.root),current=inside(root,'当前'),manifest=path.join(current,'manifest.json');fs.mkdirSync(root,{recursive:true});
 const lock=inside(root,'.publication.lock'),fd=fs.openSync(lock,'wx');let stage,archive,promoted=false;
 try{
  let prior;if(fs.existsSync(current)){if(!fs.existsSync(manifest))throw Error('Refusing unmanaged current directory');prior=JSON.parse(fs.readFileSync(manifest));if(prior.schema!==marker)throw Error('Refusing unmanaged current directory');for(const item of prior.items){const target=inside(current,item.relative);if(!fs.existsSync(target)||hash(target)!==item.sha256)throw Error('Managed copy changed; preserve manual edits and reconcile: '+target);}}
  const plan=inventoryPlan(options),signature=createHash('sha256').update(JSON.stringify(plan)).digest('hex');
  if(prior?.signature===signature)return {...prior,changed:false,items:prior.items.map(x=>({...x,target:inside(current,x.relative)}))};
  stage=inside(root,'.stage-'+randomUUID());fs.mkdirSync(stage);for(const item of plan.items){const target=inside(stage,item.relative);fs.mkdirSync(path.dirname(target),{recursive:true});copy(item.source,target);if(hash(target)!==item.sha256||hash(item.source)!==item.sha256)throw Error('Source changed during publication');}
  const result={schema:marker,createdAt:new Date().toISOString(),signature,...plan};fs.writeFileSync(path.join(stage,'manifest.json'),JSON.stringify(result,null,2));fs.writeFileSync(path.join(stage,'使用说明.txt'),'排版只从“排版定稿”取单图文件。待终检不可付印。每张图由正式台账ID、验收与SHA-256决定，不按文件修改日期选择。历史修订在上一级“历史归档”，不作为排版入口。');
  if(options.isCurrent&&!options.isCurrent())throw Error('Authority changed while preparing delivery; retry');
  if(prior){archive=inside(root,path.join('历史归档',new Date().toISOString().replace(/[:.]/g,'-')+'-'+randomUUID()));fs.mkdirSync(path.dirname(archive),{recursive:true});fs.renameSync(current,archive);}
  try{fs.renameSync(stage,current);promoted=true;}catch(error){if(archive)fs.renameSync(archive,current);throw error;}
  return {...result,changed:true,archive,items:result.items.map(x=>({...x,target:inside(current,x.relative)}))};
 }finally{if(stage&&!promoted&&fs.existsSync(stage))fs.rmSync(stage,{recursive:true,force:true});fs.closeSync(fd);fs.unlinkSync(lock);}
}
