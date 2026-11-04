// Common adapter for already-rendered public-tool PDFs. No publication or acceptance.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {assertOutputRoutes,routeSourceRefs} from './production-route.mjs';
import {verifyImportedPdfCandidate} from './imported-pdf.mjs';
import {digest,checkedArtifact} from './revision-worker.mjs';

const repo=fileURLToPath(new URL('../',import.meta.url)),tools=path.join(repo,'portable-production');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const ref=p=>({path:fs.realpathSync(p),sha256:digest(p)});
function checked(value){const actual=ref(value.path);if(actual.sha256!==value.sha256)throw Error('PDF候选输入或证据哈希变化');return actual;}
export function preparePdfCandidate(taskPath,inputPath,contextPath){
 const task=read(taskPath),attempt=fs.realpathSync(task.attemptDir);checkedArtifact(attempt,taskPath,/\.json$/i);
 const routes=assertOutputRoutes(task),input=read(inputPath),context=read(contextPath);
 const python=checked(context.runtime.python).path,dir=path.join(attempt,'pdf-candidate'),request=[taskPath,inputPath,contextPath].map(ref);
 if(fs.existsSync(dir)){
  if(JSON.stringify(read(path.join(dir,'request.json')))!==JSON.stringify(request))throw Error('PDF候选准备输入变化，须新尝试');
  const candidate=read(path.join(dir,'candidate.json'));
  verifyImportedPdfCandidate(task.existingPdf?task:{...task,existingPdf:{outputs:candidate.outputs.map(o=>({number:o.number,staged:{path:o.path,sha256:o.sha256}}))}},candidate,{python});
  return {candidate:ref(path.join(dir,'candidate.json')),reused:true};
 }
 if(routes.some(r=>r.productionRoute.method!=='editable-pdf')||!Array.isArray(input.outputs)||input.outputs.length!==task.outputNumbers.length||!Array.isArray(input.processingEvidence)||input.processingEvidence.length!==task.outputNumbers.length)throw Error('PDF候选须逐输出提供公共工具报告及制作说明');
 for(const entry of routes){
  const proof=input.processingEvidence.find(e=>e.number===entry.number);
  if(!proof)throw Error('缺少图号加工报告：'+entry.number);
  const report=read(checked(proof.report).path),actual=report.pdf_audit?.width_mm,expected=entry.productionRoute.requirements.widthMm;
  if(!Number.isFinite(actual)||Math.abs(actual-expected)>0.01)throw Error(`图${entry.number}路线宽度${expected}mm与加工报告实际宽度${actual}mm不符；按最终输出核对路线后再封装`);
 }
 const imported=task.existingPdf?.outputs;
 if(imported){
  if(imported.length!==task.outputNumbers.length)throw Error('服务端PDF隔离输出集合不完整');
  for(const number of task.outputNumbers){
   const staged=imported.find(o=>o.number===number)?.staged,output=input.outputs.find(o=>o.number===number);
   if(!staged||!output||checked(staged).sha256!==checked(output).sha256)throw Error('输入PDF与服务端隔离候选哈希不同');
   checkedArtifact(attempt,staged.path,/\.pdf$/i);
  }
  if(new Set(imported.map(o=>path.dirname(fs.realpathSync(o.staged.path)))).size!==1)throw Error('服务端PDF须位于同一隔离目录');
 }
 fs.mkdirSync(dir);const workspace=imported?path.dirname(fs.realpathSync(imported[0].staged.path)):path.join(dir,'artifacts');if(!imported)fs.mkdirSync(workspace);
 const write=(name,data)=>{const p=path.join(dir,name);fs.writeFileSync(p,JSON.stringify(data,null,2),{flag:'wx'});return ref(p);};
 const copy=(value,name)=>{const source=checked(value),target=path.join(dir,name);fs.copyFileSync(source.path,target,fs.constants.COPYFILE_EXCL);if(digest(target)!==source.sha256)throw Error('复制候选时输入变化');return ref(target);};
 write('request.json',request);
 const outputs=[],processingEvidence=[],contracts=[],outputBindings={};
 for(const [index,number] of task.outputNumbers.entries()){
  const output=input.outputs.find(o=>o.number===number),proof=input.processingEvidence.find(e=>e.number===number),route=routes[index].productionRoute;
  if(!output||!proof||!context.delivery_targets?.[number])throw Error('图号、加工证据或交付身份缺失');
  const staged=imported?checked(imported.find(o=>o.number===number).staged):copy(output,'artifacts/figure-'+number+'.pdf'),report=copy(proof.report,'report-'+number+'.json'),spec=copy(proof.spec,'spec-'+number+'.json');
  outputs.push({number,...staged});processingEvidence.push({number,report,spec,sourceRoot:proof.sourceRoot??path.dirname(proof.spec.path)});
  const id='fig'+number.replace(/[.-]/g,'_');outputBindings[id]=number;
  contracts.push({id,path:path.basename(staged.path),delivery_target:context.delivery_targets[number],format:'pdf',width_mm:route.requirements.widthMm,pixels:[],dpi:300,stroke_pt:null});
 }
 const contract={id:task.id,producer:context.producer,route:context.qualityRoute,source:task.productionRoute.sourceReview.selected,
  source_inputs:[...new Map([...routes.flatMap(r=>routeSourceRefs(r.productionRoute)),...request].map(r=>[fs.realpathSync(r.path),r])).values()],
  workspace,author_roots:context.author_roots,history:context.history,frozen_manifest:context.frozen_manifest,
  runtime:{python:ref(python),code_root:repo,code:[ref(fileURLToPath(import.meta.url)),ref(path.join(tools,'direct-pdf','journal_pdf','render.py'))],font_profile:checked(context.runtime.font_profile)},
  outputs:contracts,mechanical:['dimensions','coverage','artifact_set','preview_hashes'],
  manual_review:['source_content','visual','runtime_provenance','typography','grayscale_semantics',...(['diagram','circuit'].includes(context.qualityRoute)?['topology','label_ownership']:[])],
  allowed_changes:context.allowed_changes,immutable_content:context.immutable_content,failure_policy:context.failure_policy};
 const contractRef=write('contract.json',contract);
 execFileSync(python,['-m','task_quality','precheck',contractRef.path],{cwd:tools,env:{...process.env,PYTHONPATH:tools,PYTHONUTF8:'1'},encoding:'utf8',windowsHide:true,timeout:120000});
 const reports=processingEvidence.map(e=>e.report);
 const audit=write(path.relative(dir,path.join(workspace,'audit.json')),{output_bindings:Object.fromEntries(contracts.map((c,i)=>[c.id,outputs[i].sha256])),coverage:contract.mechanical.map(id=>({id,status:'checked',evidence:reports})),
  source_geometry:{status:'pending',evidence:reports,observation:'公共工具报告保留实际图形检查；来源与语义仍由用户终审。'},
  label_path_binding:{status:'pending',evidence:reports,observation:'标签与连接含义等待用户终审，不自动验收。'},scene:null});
 const submission=write('submission.json',{artifacts:outputs.map(({number,...r})=>r),audit});
 const candidate={attempt:task.attempt,outputs,processingEvidence,contract:contractRef,submission,outputBindings,summary:input.summary};
 verifyImportedPdfCandidate(task.existingPdf?task:{...task,existingPdf:{outputs:outputs.map(o=>({number:o.number,staged:{path:o.path,sha256:o.sha256}}))}},candidate,{python});
 return {candidate:write('candidate.json',candidate),reused:false};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const args=process.argv.slice(2);if(args.length!==3)throw Error('Usage: node pdf-candidate.mjs task.json rendered-input.json existing-evidence.json');console.log(JSON.stringify(preparePdfCandidate(...args)));}
 catch(error){console.error(error.message);if(error.stdout)console.error(String(error.stdout));if(error.stderr)console.error(String(error.stderr));process.exitCode=1;}
}
