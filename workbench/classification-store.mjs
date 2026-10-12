import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export const classificationTypes=['流程/算法图','系统/模块框图','网络/拓扑图','电路/接线图','统计图表','曲线/波形/频谱','界面/代码截图','实物/设备照片','地图/空间图','结构/原理示意','表格','混合多子图','待辨认'];
export const classificationRoutes=['保留原图换字','重排框图候选','仅做图像排版','待确认'];
export const classificationReviews=['待复核','用户已调整','分类已确认','有疑问'];
const fail=(message,status=400)=>Object.assign(new Error(message),{status});
export function createClassificationStore(file){
 function read(){
  const data=JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
  if(!Number.isSafeInteger(data.revision)||data.revision<0||!Array.isArray(data.cards)||new Set(data.cards.map(c=>c.id)).size!==data.cards.length)throw fail('分类文件身份或版本无效',503);
  return data;
 }
 function save(input){
  if(!input||Object.keys(input).some(k=>!['revision','changes'].includes(k))||!Number.isSafeInteger(input.revision)||!Array.isArray(input.changes)||!input.changes.length)throw fail('无效分类保存请求');
  const data=read();
  if(input.changes.length>data.cards.length)throw fail('变更数超过当前图件数');
  if(input.revision!==data.revision)throw Object.assign(fail('分类已被其他窗口修改，请重新读取',409),{revision:data.revision});
  const byId=new Map(data.cards.map(c=>[c.id,c])),seen=new Set(),changes=[],updatedAt=new Date().toISOString();
  for(const change of input.changes){
   if(!change||typeof change!=='object'||Array.isArray(change)||typeof change.id!=='string'||!byId.has(change.id)||seen.has(change.id))throw fail('未知或重复图件ID');
   seen.add(change.id);
   const keys=Object.keys(change).filter(k=>k!=='id');
   if(!keys.length||keys.some(k=>!['type','route','note','review'].includes(k)))throw fail('只能保存类型、处理路线、备注和复核');
   for(const key of keys){
    if(typeof change[key]!=='string'||change[key].length>(key==='type'?64:4000))throw fail('分类字段必须是限长文本');
    if(key==='type'&&!classificationTypes.includes(change[key]))throw fail('未知分类类型');
    if(key==='route'&&!classificationRoutes.includes(change[key]))throw fail('未知处理路线');
    if(key==='review'&&!classificationReviews.includes(change[key]))throw fail('未知复核状态');
    if(byId.get(change.id)[key]!==change[key])changes.push({id:change.id,field:key,previous:byId.get(change.id)[key]??null,next:change[key]});
    byId.get(change.id)[key]=change[key];
   }
   byId.get(change.id).updatedAt=updatedAt;
  }
  data.revision++;data.updatedAt=updatedAt;
  data.history=[...(data.history||[]),{revision:data.revision,updatedAt,changes}];
  const temp=file+'.'+randomUUID()+'.tmp';
  try{fs.writeFileSync(temp,JSON.stringify(data,null,2)+'\n',{encoding:'utf8',flag:'wx'});fs.renameSync(temp,file);}finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}
  return data;
 }
 return {read,save};
}

export function createClassificationHandler({store,origin,assetsDirectory}){
 const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.svg':'image/svg+xml','.webp':'image/webp','.gif':'image/gif'};
 function json(res,status,data){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(data));}
 return function handle(req,res,url){
  if(url.pathname!=='/classification'&&!url.pathname.startsWith('/classification/'))return false;
  if(url.pathname==='/classification/data'){
   if(req.method==='GET'){try{json(res,200,store.read());}catch(e){json(res,e.status||500,{ok:false,error:e.message});}return true;}
   if(req.method!=='POST'){json(res,405,{ok:false,error:'Method not allowed'});return true;}
   if(req.headers.origin!==origin){json(res,403,{ok:false,error:'只允许同源保存'});return true;}
   if((req.headers['content-type']||'').split(';')[0].trim()!=='application/json'){json(res,415,{ok:false,error:'需要application/json'});return true;}
   const chunks=[];let length=0,large=false;
   req.on('data',chunk=>{length+=chunk.length;if(length>2*1024*1024){large=true;chunks.length=0;}else if(!large)chunks.push(chunk);});
   req.on('end',()=>{try{if(large)throw fail('分类保存体积超过2MiB',413);let input;try{input=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw fail('无效JSON');}json(res,200,{ok:true,...store.save(input)});}catch(e){json(res,e.status||500,{ok:false,error:e.message,...(e.revision===undefined?{}:{revision:e.revision})});}});
   return true;
  }
  if(req.method!=='GET'){res.writeHead(405).end();return true;}
  let file;
  const staticName={'/classification':'classification.html','/classification/':'classification.html','/classification/classification.js':'classification.js','/classification/classification.css':'classification.css'}[url.pathname];
  if(staticName)file=path.join(assetsDirectory,staticName);
  else if(url.pathname.startsWith('/classification/images/')){
   let name;try{name=decodeURIComponent(url.pathname.slice('/classification/images/'.length));}catch{res.writeHead(400).end();return true;}
   if(!/^[a-zA-Z0-9_.-]+$/.test(name)||name==='.'||name==='..'||!mime[path.extname(name).toLowerCase()]||!['.png','.jpg','.jpeg','.svg','.webp','.gif'].includes(path.extname(name).toLowerCase())){res.writeHead(404).end();return true;}
   const root=path.join(assetsDirectory,'classification-assets','images');file=path.join(root,name);
   if(fs.existsSync(file)){const relative=path.relative(fs.realpathSync(root),fs.realpathSync(file));if(relative.startsWith('..')||path.isAbsolute(relative)){res.writeHead(403).end();return true;}}
  }
  if(!file||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end();return true;}
  res.setHeader('Content-Type',mime[path.extname(file).toLowerCase()]);fs.createReadStream(file).pipe(res);return true;
 };
}
