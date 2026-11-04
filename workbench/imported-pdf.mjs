import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {digest} from './revision-worker.mjs';
import {assertProductionRoute,routeSourceRefs} from './production-route.mjs';
import {verifyProcessingEvidence} from './processing-evidence.mjs';

const qualityRoot=fileURLToPath(new URL('../portable-production/',import.meta.url));
const sameRef=(a,b)=>a&&b&&path.resolve(a.path)===path.resolve(b.path)&&a.sha256===b.sha256;
const requiredChecks=['dimensions','coverage','artifact_set','preview_hashes'];
const inside=(root,value)=>{let actual;try{actual=fs.realpathSync(value);}catch{return false;}const relative=path.relative(fs.realpathSync(root),actual);return relative!==''&&!relative.startsWith('..'+path.sep)&&relative!=='..'&&!path.isAbsolute(relative);};
function ref(value,root){
 if(!value||typeof value.path!=='string'||! /^[a-f0-9]{64}$/.test(value.sha256||'')||!inside(root,value.path)||digest(value.path)!==value.sha256)throw Error('PDF候选质量文件不在本次隔离尝试内或哈希不符');
 return value;
}

// The caller supplies a task-quality contract already prechecked in this attempt.
// This runs only mechanical postcheck; its result remains pending manual review.
export function verifyImportedPdfCandidate(task,input,{python}={}){
 const route=assertProductionRoute(task),attempt=fs.realpathSync(task.attemptDir);
 if(route.method!=='editable-pdf')throw Error('PDF候选导入仅支持可编辑PDF路线');
 const processing=verifyProcessingEvidence(task,(task.existingPdf?.outputs??[]).map(o=>({number:o.number,...o.staged})),input?.processingEvidence,{python});
 if(!python)throw Error('未配置独立质量核验Python');
 if(!input||!input.contract||!input.submission||!input.outputBindings)throw Error('缺少预检质量契约、提交文件或输出图号绑定');
 const contractRef=ref(input.contract,attempt),submissionRef=ref(input.submission,attempt);
 const contract=JSON.parse(fs.readFileSync(contractRef.path,'utf8'));
 if(contract.id!==task.id||!['diagram','circuit','source-preserving-chart'].includes(contract.route)||typeof contract.producer!=='string'||!contract.producer.trim())throw Error('PDF质量契约未绑定当前任务或路线');
 if(!Array.isArray(contract.mechanical)||requiredChecks.some(id=>!contract.mechanical.includes(id)))throw Error('PDF质量契约缺少尺寸、覆盖、产物集合或预览哈希检查');
 if(!Array.isArray(contract.manual_review)||!['source_content','visual','runtime_provenance','typography','grayscale_semantics'].every(id=>contract.manual_review.includes(id)))throw Error('既有PDF契约必须保留内容、视觉、来源、字体及灰度语义人工复核');
 if(!inside(attempt,contract.workspace)||!fs.statSync(contract.workspace).isDirectory())throw Error('PDF质量工作区须位于本次隔离尝试');
 if(!sameRef(contract.source,route.sourceReview.selected))throw Error('PDF质量契约主源件与已核对来源不一致');
 const routeRefs=[...new Map([...(task.outputRoutes||[]).flatMap(entry=>routeSourceRefs(entry.productionRoute)),...routeSourceRefs(route)].map(source=>[path.resolve(source.path),source])).values()];
 if(!Array.isArray(contract.source_inputs)||routeRefs.some(source=>!contract.source_inputs.some(input=>sameRef(source,input))))throw Error('PDF质量契约未覆盖原包、Word、来源清单及候选源件');
 if(!Array.isArray(contract.outputs)||contract.outputs.length!==task.outputNumbers.length||contract.outputs.some(output=>output.format!=='pdf'))throw Error('PDF质量契约输出集合或格式不符');
 const bindings=input.outputBindings;
 if(typeof bindings!=='object'||Array.isArray(bindings)||Object.keys(bindings).length!==contract.outputs.length)throw Error('PDF契约输出图号绑定不完整');
 const numbers=new Set(),ids=new Set();
 for(const output of contract.outputs){
  const number=bindings[output.id];
  if(typeof number!=='string'||!task.outputNumbers.includes(number)||numbers.has(number)||ids.has(output.id))throw Error('PDF质量契约输出与任务图号重复或不符');
  numbers.add(number);ids.add(output.id);
  const artifact=path.resolve(contract.workspace,output.path);
  const staged=task.existingPdf?.outputs?.find(item=>item.number===number)?.staged;
  const outputRoute=(task.outputRoutes||[]).find(entry=>entry.number===number)?.productionRoute??route;
  if(Math.abs(output.width_mm-outputRoute.requirements.widthMm)>0.000001||!inside(attempt,artifact)||!fs.existsSync(artifact)||path.extname(artifact).toLowerCase()!=='.pdf'||!staged||path.resolve(staged.path)!==artifact||digest(artifact)!==staged.sha256)throw Error('PDF产物必须精确绑定隔离复制的候选哈希及路线尺寸');
 }
 if(task.outputNumbers.some(number=>!numbers.has(number)))throw Error('PDF候选未覆盖完整任务图号集合');
 const contractPath=contractRef.path,submissionPath=submissionRef.path;
 let checked;
 try{
  checked=JSON.parse(execFileSync(python,['-m','task_quality','postcheck',contractPath,submissionPath],{cwd:qualityRoot,env:{...process.env,PYTHONPATH:qualityRoot,PYTHONUTF8:'1'},windowsHide:true,encoding:'utf8',timeout:120000,maxBuffer:1024*1024}));
 }catch(error){throw Error('PDF候选独立自动检查失败：'+String(error.stdout||error.message).slice(0,2000));}
 const receipt=checked.result;
 if(checked.ok!==true||checked.phase!=='postcheck'||receipt?.status!=='candidate'||receipt?.manual_status!=='pending')throw Error('PDF候选自动检查未返回待人工复核状态');
 if(requiredChecks.some(id=>receipt.coverage_pending?.includes(id)))throw Error('PDF候选机械覆盖仍有未解决检查');
 const outputs=contract.outputs.map(output=>{
  const number=bindings[output.id],artifact=path.resolve(contract.workspace,output.path),preview=path.join(contract.workspace,'.task-quality',output.id+'.preview.png');
  if(!fs.existsSync(preview))throw Error('PDF质量门未生成绑定预览');
  const width=output.width_mm,base=width<=80?80:160;
  return {number,path:artifact,sha256:digest(artifact),preview,previewSha256:digest(preview),columnLabel:(width<=80?'单栏约':'双栏约')+Math.round(width/base*10)*10+'%',fontLabel:''};
 });
 const result={evidence:'既有PDF已按本任务预检契约执行task_quality postcheck，机械检查完成，待独立人工复核。',outputs,
  quality:{processingEvidence:processing,importedPdf:{contract:contractRef,submission:submissionRef,outputBindings:bindings,result:receipt}}};
 return {result,qualityVerification:{kind:'automatic-candidate',status:'candidate',manualStatus:'pending',manualReviewPending:contract.manual_review,coveragePending:receipt.coverage_pending,measurements:receipt.measurements,previews:receipt.previews}};
}
