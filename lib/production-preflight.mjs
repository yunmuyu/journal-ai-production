import {readFileSync,existsSync} from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

const CONTINUE='可继续',CHANGED='源已变需确认',REPAIR='必须修单图';
const hash=file=>createHash('sha256').update(readFileSync(file)).digest('hex');
const json=file=>JSON.parse(readFileSync(file,'utf8').replace(/^\uFEFF/,''));
export function loadProductionContext(root='F:/2026年10月/_作图工作台'){
 return {registry:json(path.join(root,'production-results.json')),templates:json(path.join(root,'author-templates.json'))};
}
function finish(stage,issues,observations){
 const status=issues.some(i=>i.status===CHANGED)?CHANGED:issues.length?REPAIR:CONTINUE;
 return {stage,status,issues,observations,finalPdfReviewRequired:true};
}
function verifyFile(file,expected,status,kind,id,issues){
 if(!file||!existsSync(file)){issues.push({status,kind,id,path:file,reason:'文件缺失'});return;}
 if(!expected){issues.push({status,kind,id,path:file,reason:'缺少已登记hash，不能视为已验证'});return;}
 const actual=hash(file);
 if(actual!==expected)issues.push({status,kind,id,path:file,expected,actual,reason:'文件已变，当前证据不适用于它'});
}
function checkFormal(articleIds,context,issues){
 const {registry,templates}=context;
 for(const articleId of articleIds){
  const article=registry.articles?.[articleId],entry=templates[articleId];
  const ai=article?.ai||entry?.path,aiHash=article?.aiHash||entry?.sha256;
  if(ai)verifyFile(ai,aiHash,CHANGED,'current-author-ai',articleId,issues);
  for(const [figureId,record] of Object.entries(registry.figures||{})){
   if(!figureId.startsWith(articleId+'-F'))continue;
   const exports=record.subfigures?.length?record.subfigures:[record];
   for(const output of exports)if(output.output)verifyFile(output.output,output.outputHash,CHANGED,'current-formal-output',figureId,issues);
  }
 }
}
function readRecord(file,id,issues){
 try{return json(file);}catch(error){issues.push({status:REPAIR,kind:'render-record',id,path:file,reason:String(error.message)});return null;}
}
function sizes(record){return [...new Set((record.adobe?.snapshot?.texts||record.report?.snapshot?.texts||[]).map(t=>t.size).filter(Number.isFinite))];}
export function preflightRender(inputs,context,{priorRows=[]}={}){
 const issues=[],observations=[];
 checkFormal([...new Set(inputs.map(i=>i.articleId))],context,issues);
 for(const input of inputs){
  const id=input.figureId||input.articleId+'-F'+String(input.number).split('.')[0];
  verifyFile(input.source,input.sourceHash,CHANGED,'source',id,issues);
  const previous=priorRows.find(r=>r.articleId===input.articleId&&String(r.number)===String(input.number)&&(r.sourceHash===input.sourceHash||r.result?.outputHash===input.sourceHash||r.result?.aiHash===input.sourceHash));
  const reuse=input.preflight?.reuseRecord||previous?.record;
  if(!reuse)continue;
  const record=readRecord(reuse,id,issues);if(!record)continue;
  const actual=sizes(record);observations.push({id,kind:'available-render-font',sizesPt:actual,record:reuse});
  const minimum=actual.length?Math.min(...actual):null;
  if(minimum!==null&&input.plan.fontSize<minimum&&!input.preflight?.fontSizeChangeReason?.trim())issues.push({status:REPAIR,kind:'reuse-font',id,actualSizesPt:actual,requestedPt:input.plan.fontSize,reason:'复用字号低于已有实际字号；先确认排版/容量依据，不能猜成更小字号'});
 }
 return finish('before-render',issues,observations);
}
export function preflightAggregate(config,context){
 const issues=[],observations=[];
 checkFormal([config.articleId],context,issues);
 for(const figure of config.figures){
  const id=figure.figureId||config.articleId+'-F'+String(figure.number).split('.')[0];
  const record=readRecord(figure.record,id,issues);if(!record)continue;
  let plan;
  const planFile=path.join(path.dirname(figure.record),'plan.json');
  if(existsSync(planFile)){try{plan=json(planFile);}catch(error){issues.push({status:REPAIR,kind:'plan',id,reason:String(error.message)});}}
  const source=figure.source||record.source;
  if(source)verifyFile(source,figure.sourceHash||record.sourceHash||plan?.sourceHash,CHANGED,'source',id,issues);
  else issues.push({status:REPAIR,kind:'source',id,reason:'没有可核对的源文件'});
  verifyFile(record.output,record.outputHash,REPAIR,'candidate-output',id,issues);
  verifyFile(record.ai,record.aiHash,REPAIR,'candidate-ai',id,issues);
  const mechanical=record.adobe?.mechanicalIssues||record.report?.mechanicalIssues||[];
  if(record.ok===false||mechanical.length||record.adobe?.diagramAudit?.ok===false)issues.push({status:REPAIR,kind:'mechanical',id,details:mechanical,reason:'单图有未解决问题，禁止进入汇总'});
  if(!(record.audit||record.pdfAudit)?.ok)issues.push({status:REPAIR,kind:'actual-pdf-audit',id,reason:'单图缺少通过的实际PDF审计'});
  const actual=sizes(record);observations.push({id,number:figure.number,kind:'candidate-font',sizesPt:actual});
  if(plan?.fontSize&&actual.some(size=>Math.abs(size-plan.fontSize)>.01))issues.push({status:REPAIR,kind:'font-size',id,actualSizesPt:actual,plannedPt:plan.fontSize,reason:'实际snapshot字号与当前渲染计划不一致'});
 }
 return finish('before-aggregate',issues,observations);
}
export function requirePreflight(report){
 if(report.status!==CONTINUE){console.error(JSON.stringify(report));throw Error('批前检查：'+report.status);}
 return report;
}
