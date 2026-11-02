import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {pipeline} from 'node:stream/promises';
import {Transform} from 'node:stream';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const run=promisify(execFile);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
function safe(value){return typeof value==='string'&&value.length>0&&value.length<160&&!/[<>:"/\\|?*\x00-\x1f]|[. ]$/.test(value)&&! /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(value);}
export function intakeFields(url){
 const filename=url.searchParams.get('filename'),editor=url.searchParams.get('editor'),month=Number(url.searchParams.get('month')),count=Number(url.searchParams.get('count'));
 if(!safe(filename)||!safe(editor)||! /\.(zip|rar)$/i.test(filename)||!Number.isInteger(month)||month<1||month>12||!Number.isInteger(count)||count<1||count>999)throw Error('请填写月份、编辑、篇数，并选择 ZIP 或 RAR 文件');
 return {filename,editor,month,count};
}
export function createArchiveIntake({config,root,origin,register,execute=run}){
 fs.mkdirSync(root,{recursive:true});
 const registryPath=path.join(root,'batches.json');
 let batches=fs.existsSync(registryPath)?read(registryPath):[],busy=false;
 for(const batch of batches)register(batch);
 async function receive(req,fields){
  const dir=path.join(root,'incoming',randomUUID());fs.mkdirSync(dir,{recursive:true});
  const archive=path.join(dir,fields.filename),hasher=createHash('sha256');let size=0;
  try{
   await pipeline(req,new Transform({transform(chunk,encoding,done){size+=chunk.length;if(size>(config.maxBytes||512*1024*1024))return done(Error('压缩包超过大小限制'));hasher.update(chunk);done(null,chunk);}}),fs.createWriteStream(archive,{flags:'wx'}));
   if(!size)throw Error('压缩包为空');
   const hash=hasher.digest('hex'),old=batches.find(b=>b.archiveSha256===hash);
   if(old){if(old.month!==fields.month||old.editor!==fields.editor||old.articles!==fields.count)throw Error('这个包已登记，填写的信息与原登记不一致');return {...old,duplicate:true};}
   const batchName=`${fields.month}月-${fields.editor}-${fields.count}篇`,batchRoot=path.join(config.deliveryRoot,batchName);
   if(batches.some(b=>b.batch===batchRoot))throw Error('该批次已有不同原包，请先核对版本，不能覆盖');
   if(fs.existsSync(batchRoot))for(const name of fs.readdirSync(batchRoot).filter(n=>/\.(zip|rar)$/i.test(n))){
    const current=createHash('sha256').update(fs.readFileSync(path.join(batchRoot,name))).digest('hex');
    if(current!==hash)throw Error('现有交付批次已有不同原包，不能覆盖或混入');
   }
   const manifest=path.join(dir,'manifest.json'),sourceRoot=path.join(config.internalRoot,`${fields.editor}-${fields.count}篇`,'原稿');
   try{await execute(config.powershell,['-NoProfile','-NonInteractive','-File',config.folderScript,'-Archive',archive,'-Destination',config.deliveryRoot,'-Month',String(fields.month),'-Editor',fields.editor,'-Count',String(fields.count),'-SourceRoot',sourceRoot,'-ManifestPath',manifest,...(config.unrar?['-Unrar',config.unrar]:[])],{windowsHide:true,timeout:180000,maxBuffer:1024*1024});}
   catch(error){
    const detail=String(error.stderr||error.message).replace(/\x1b\[[0-9;]*m/g,'');
    fs.writeFileSync(path.join(root,'last-error.json'),JSON.stringify({time:new Date().toISOString(),filename:fields.filename,detail},null,2));
    const count=detail.match(/Expected (\d+) articles, found (\d+)/);
    throw Error(count?`填写了 ${count[1]} 篇，包内识别到 ${count[2]} 篇，请核对篇数。`:'原包核对未通过，未登记工作台。请核对 Word 命名、压缩包完整性和现有原稿；详细原因已保存在内部日志。');
   }
   const receipt=read(manifest);
   if(receipt.archiveSha256!==hash||receipt.articles!==fields.count)throw Error('收包回执不一致，未登记工作台');
   const batch={...receipt,month:fields.month,editor:fields.editor,filename:fields.filename,registeredAt:new Date().toISOString()};
   const next=[...batches,batch],temp=registryPath+'.tmp';fs.writeFileSync(temp,JSON.stringify(next,null,2));fs.renameSync(temp,registryPath);batches=next;
   register(batch);return batch;
  }finally{
   // Only this request's generated staging directory is removed; original archives remain.
   fs.rmSync(dir,{recursive:true,force:true});
  }
 }
 return {handle(req,res,url){
  if(url.pathname!=='/archive-intake')return false;
  const json=(status,value)=>{if(!res.destroyed)res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(value));};
  if(req.method!=='POST'||req.headers.origin!==origin){json(403,{error:'请从工作台上传'});return true;}
  if(busy){req.resume();json(409,{error:'正在登记另一个包，请稍后重试'});return true;}
  let fields;try{fields=intakeFields(url);}catch(error){req.resume();json(400,{error:error.message});return true;}
  busy=true;
  receive(req,fields).then(batch=>json(200,{batch})).catch(error=>json(400,{error:error.message})).finally(()=>{busy=false;});return true;
 }};
}
