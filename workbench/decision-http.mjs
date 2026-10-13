import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createDecisionStore} from './decision-store.mjs';
import {resolveLocal} from './paths.mjs';
import {candidateDeliveryPreview} from './candidate-preview.mjs';
export function createDecisionHandler({recordRoot,origin}) {
 const pilotPath=path.join(recordRoot,'decision-pilot.json');
 const store=createDecisionStore({recordsPath:path.join(recordRoot,'production-results.json'),pilotPath});
 const files=new Map();
 function publicData(){
  if(!fs.existsSync(pilotPath))return {schemaVersion:1,figures:[],cases:[],assets:{}};
  const data=store.read();files.clear();
  const classificationPath=path.join(recordRoot,'figure-classification.json');
  const classification=fs.existsSync(classificationPath)?JSON.parse(fs.readFileSync(classificationPath,'utf8')):{cards:[]};
  const classifications=new Map(classification.cards.map(card=>[card.id,card]));
  const digestCache=new Map(),digest=file=>{if(!digestCache.has(file))digestCache.set(file,createHash('sha256').update(fs.readFileSync(file)).digest('hex'));return digestCache.get(file);};
  const assets={};
  for(const [id,asset] of Object.entries(data.assets||{})) {
   if(!asset.path||!fs.existsSync(resolveLocal(asset.path)))continue;
   const file=path.resolve(resolveLocal(asset.path)),token=createHash('sha256').update(file).digest('hex').slice(0,24);
   files.set(token,file);assets[id]={token,name:path.basename(file),label:asset.label||path.basename(file)};
  }
  for(const figure of data.figures){for(const a of figure.decision?.sourceReview?.attachments||[]){if(!fs.existsSync(resolveLocal(a.path)))continue;const file=path.resolve(resolveLocal(a.path)),token=createHash('sha256').update(file).digest('hex').slice(0,24);files.set(token,file);a.token=token;}}
  const figures=data.figures.map(figure=>{
   const {retrievalQuery,similarCaseIds,sourceFiles,proposalHistory,...publicFigure}=figure;
   const {caseRetrieval,...proposal}=figure.aiProposal;
   const copy=structuredClone({...publicFigure,aiProposal:proposal});
   const card=classifications.get(figure.id);copy.basicClassification={value:card?.type??figure.aiProposal.fields?.contentTypes?.value??'待判断',confirmed:card?.review==='分类已确认',review:card?.review||'待复核'};
   const candidate=candidateDeliveryPreview(copy,(id,region)=>{
    const source=resolveLocal(region.source),file=resolveLocal(region.path);
    if(!fs.existsSync(source)||!fs.existsSync(file)||digest(source)!==region.sourceHash)return null;
    if(region.previewHash&&createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==region.previewHash)return null;
    const token=createHash('sha256').update(path.resolve(file)).digest('hex').slice(0,24);files.set(token,path.resolve(file));assets[id]={token,name:path.basename(file),label:'候选原像素范围，未制作'};return id;
   });
   if(candidate)copy.candidateDeliveryPreview=candidate;
   delete copy.retrievalQuery;delete copy.similarCaseIds;delete copy.sourceFiles;delete copy.aiProposal.caseRetrieval;return copy;
  });
  return {schemaVersion:data.schemaVersion,figures,assets};
 }
 function json(res,status,data){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(data));}
 function handle(req,res,url){
  if(!url.pathname.startsWith('/decisions'))return false;
  if(url.pathname==='/decisions'&&req.method==='GET'){try{json(res,200,publicData());}catch(error){json(res,500,{error:error.message});}return true;}
  const id=url.pathname.slice('/decisions/'.length);
  if(!url.pathname.startsWith('/decisions/')||req.method!=='POST'){json(res,405,{error:'不支持的请求'});return true;}
  if(req.headers.origin!==origin){json(res,403,{error:'只允许工作台内保存'});return true;}
  if(!(req.headers['content-type']||'').startsWith('application/json')){json(res,415,{error:'需要JSON方案'});return true;}
  const chunks=[];let size=0;
  req.on('data',part=>{size+=part.length;if(size<=40*1024*1024)chunks.push(part);});
  req.on('end',()=>{try{
   if(size>40*1024*1024)throw Object.assign(Error('方案内容过长'),{status:413});
   let input;try{input=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw Object.assign(Error('方案格式错误'),{status:400});}
   const decision=store.save(id,input);json(res,200,{ok:true,decision});
  }catch(error){json(res,error.status||500,{error:error.message,fields:error.fields,issues:error.issues});}});
  return true;
 }
 publicData();
 return {handle,files};
}
