// Existing Office conversion as source preparation, never figure delivery.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {acquireDirectRunLock} from './raster-batch.mjs';
import {buildPptxPlan,validatePptxPlan} from '../lib/pptx-plan.mjs';
const exec=promisify(execFile),entry=fileURLToPath(import.meta.url);
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
export const isOfficeSource=file=>/\.(docx?|emf|wmf|ppt[xm]?|vsd[xm]?|xls[xmb]?)$/i.test(file);
let pending=Promise.resolve();

export function prepareOfficeSource(request){
 const deadline=Date.now()+Math.min(request.timeoutMs??180000,180000);
 const task=pending.then(()=>{
  const timeoutMs=deadline-Date.now();if(timeoutMs<=0)throw Error('office_source_deadline: resource_wait');
  return convertPreparedOfficeSource({...request,timeoutMs});
 });
 pending=task.then(()=>undefined,()=>undefined);return task;
}

async function convertPreparedOfficeSource({source,workbenchRoot,timeoutMs,python,pptxPlan,pptxDecision,grayscale=false}){
 const deadline=Date.now()+timeoutMs;
 if(!isOfficeSource(source.path))throw Error('office_source_format');
 if(hash(source.path)!==source.sha256)throw Error('office_source_changed');
 if(pptxPlan&&pptxDecision)throw Error('pptx_plan_conflict');
 let proposal;
 if(pptxDecision){
  if(!python||pptxDecision.sourceSha256!==source.sha256)throw Error('pptx_plan_source');
  const inspector=fileURLToPath(new URL('../scripts/pptx-chart-candidates.py',import.meta.url));
  const inspected=await exec(python,[inspector,source.path,String(pptxDecision.slide),JSON.stringify(pptxDecision.plotRectPt),JSON.stringify(pptxDecision.legendRectPt)],
   {windowsHide:true,timeout:Math.min(timeoutMs,30000),maxBuffer:4*1024*1024,env:{...process.env,PYTHONUTF8:'1'}});
  proposal=JSON.parse(inspected.stdout);pptxPlan=buildPptxPlan(proposal,pptxDecision,source);
 }
 if(pptxPlan)validatePptxPlan(pptxPlan,source,python);
 if(grayscale&&!pptxPlan)throw Error('pptx_gray_plan_required');
 const root=path.join(workbenchRoot,'source-preparation','office');fs.mkdirSync(root,{recursive:true});
 const uncertain=path.join(root,'.uncertain');if(fs.existsSync(uncertain))throw Error('office_source_uncertain_requires_inspection');
 const lock=path.join(root,'.conversion.lock'),owner=acquireDirectRunLock(lock);
 try{
  const remaining=deadline-Date.now();if(remaining<=0)throw Error('office_source_deadline: preparation');
  const {stdout}=await exec(process.execPath,[entry,'--worker',path.join(root,source.sha256),path.resolve(source.path),JSON.stringify({python,pptxPlan,grayscale})],
   {windowsHide:true,timeout:Math.min(remaining,180000),maxBuffer:4*1024*1024});
  const result=JSON.parse(stdout);
  if(hash(source.path)!==source.sha256||!result.ok)throw Error('office_source_conversion_failed');
  const outputs=result.outputs.filter(o=>o.kind==='pdf').map(o=>{
   if(hash(o.path)!==o.sha256)throw Error('office_prepared_output_changed');return {path:o.path,sha256:o.sha256};
  });
  if(!outputs.length)throw Error('office_prepared_pdf_missing');
  return {status:'prepared-intermediate',entry:'lib/convert.mjs::convertOffice',source,outputs,cached:!!result.cached,geometry:result.geometry??null,
   ...(proposal?{objectCandidates:proposal,appliedPlan:pptxPlan}:{}),
   warning:'转换件仅证明图源可读取；须绑定实际图号、页、裁区及加工要求，不能当成已交付成图'};
 }catch(error){
  if(error.killed||error.code==='ETIMEDOUT')fs.writeFileSync(uncertain,JSON.stringify({at:new Date().toISOString(),source,reason:'Office child execution timed out; inspect cscript/Office before reuse'}),{flag:'wx'});
  throw error;
 }finally{if(fs.existsSync(lock)&&JSON.parse(fs.readFileSync(lock,'utf8')).token===owner.token)fs.unlinkSync(lock);}
}

if(process.argv[1]&&path.resolve(process.argv[1])===entry&&process.argv[2]==='--worker'){
 const {convertOffice}=await import('../lib/convert.mjs');
 console.log(JSON.stringify(convertOffice(process.argv[3],process.argv[4],JSON.parse(process.argv[5]??'{}'))));
}
