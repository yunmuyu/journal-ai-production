import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const qualityRoot=fileURLToPath(new URL('../portable-production/',import.meta.url));
const digest=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const nonempty=v=>typeof v==='string'&&v.trim().length>0;
const samePath=(a,b)=>path.resolve(a)===path.resolve(b);
const sameRef=(a,b)=>a&&b&&samePath(a.path,b.path)&&a.sha256===b.sha256;
function ref(value,checkFiles){
 if(!value||!nonempty(value.path)||! /^[a-f0-9]{64}$/.test(value.sha256||''))throw Error('来源核对缺少文件路径或SHA256');
 if(checkFiles&&(!fs.statSync(value.path).isFile()||digest(value.path)!==value.sha256))throw Error('来源文件哈希已变化');
 return value;
}
function child(root,p){
 const actual=fs.realpathSync(p),relative=path.relative(fs.realpathSync(root),actual);
 if(relative.startsWith('..')||path.isAbsolute(relative))throw Error('独立质量文件必须位于本次隔离目录');
 return actual;
}
export function routeSourceRefs(route){
 const s=route.sourceReview;return [s.archive,s.word,s.inventory,...s.candidates.map(({path,sha256})=>({path,sha256}))];
}

// No provider names or group-label heuristics: only an explicit, source-bound decision.
export function assertProductionRoute(task,{checkFiles=true}={}){
 const r=task.productionRoute;
 if(!r||r.version!==1||!['raster-preserve','editable-pdf'].includes(r.method))throw Error('缺少有效的结构化制作路线合同；旧任务须重新核对');
 if(nonempty(task.legacyProductionInstructions))throw Error('旧通用派单模板不能混入路线任务；须迁移为按路线生成');
 const s=r.sourceReview,q=r.requirements;
 if(!s||!nonempty(s.basis)||!Array.isArray(s.candidates)||!s.candidates.length)throw Error('候选源件及原包/Word核对依据不完整');
 if(Object.keys(s).some(k=>!['archive','word','inventory','selected','additionalSelected','candidates','basis','rasterReason'].includes(k)))throw Error('来源核对含未知字段；多源仅使用 additionalSelected');
 for(const p of [s.archive,s.word,s.inventory,s.selected])ref(p,checkFiles);
 const selected=[];
 for(const c of s.candidates){
  ref(c,checkFiles);
  if(!['raster','vector','editable'].includes(c.kind)||!['selected','not-applicable'].includes(c.decision)||!nonempty(c.reason))throw Error('候选源件须逐项说明采用或不适用原因');
  if(c.decision==='selected')selected.push(c);
 }
 const additional=s.additionalSelected??[];
 if(!Array.isArray(additional)||additional.length&&r.method!=='raster-preserve')throw Error('additionalSelected 仅适用于位图组合路线');
 for(const p of additional)ref(p,checkFiles);
 const selectedInputs=[s.selected,...additional];
 if(new Set(selectedInputs.map(p=>path.resolve(p.path))).size!==selectedInputs.length||selected.length!==selectedInputs.length||selectedInputs.some(p=>!selected.some(c=>sameRef(c,p))))throw Error('选中源件须与主源件及 additionalSelected 完整一致且不重复');
 if(new Set(s.candidates.map(c=>path.resolve(c.path))).size!==s.candidates.length)throw Error('候选源件重复');
 if(r.method==='raster-preserve'&&(selected.some(c=>c.kind!=='raster')||!nonempty(s.rasterReason)))throw Error('位图保留路线须说明无法可靠重绘的内容依据，不能只按扩展名');
 if(!q||Object.keys(q).sort().join(',')!=='fontCheck,format,widthMm'||!Number.isFinite(q.widthMm)||q.widthMm<=0)throw Error('路线要求须明确格式、字号检查范围和实际宽度');
 const raster=r.method==='raster-preserve';
 if(q.format!==(raster?'jpg':'pdf')||q.fontCheck!==(raster?'none':'editable'))throw Error('处理路线、交付格式与字号检查要求互相冲突');
 if(!Array.isArray(task.outputNumbers)||!task.outputNumbers.length||new Set(task.outputNumbers).size!==task.outputNumbers.length||task.outputNumbers.some(n=>typeof n!=='string'||!/^\d+(?:[.-]\d+)*$/.test(n)))throw Error('路线任务缺少唯一导出图号');
 return r;
}

export function verifyRasterPlan(task,result,contract){
 const route=task.productionRoute,additional=route.sourceReview.additionalSelected||[];
 const evidence=result.quality?.rasterPlan;
 if(!additional.length&&evidence===undefined)return;
 if(route.method!=='raster-preserve')throw Error('非位图路线不能绑定 raster 计划');
 if(result.outputs.length!==1)throw Error('公共 raster 计划当前每任务只支持一个输出');
 if(!evidence)throw Error('多源位图组合缺少公共 raster 计划');
 ref(evidence,true);const planPath=child(task.attemptDir,evidence.path),plan=JSON.parse(fs.readFileSync(planPath,'utf8'));
 if(!contract.source_inputs.some(p=>sameRef(p,evidence)))throw Error('组合计划必须纳入独立质量合同冻结来源');
 const selected=[route.sourceReview.selected,...additional];
 if(!Array.isArray(plan.inputs)||plan.inputs.length!==selected.length||plan.inputs.some((p,i)=>!sameRef(p,selected[i])))throw Error('组合计划输入及顺序与路线选源不一致');
 if(!samePath(plan.output,result.outputs[0].path)||plan.width_mm!==route.requirements.widthMm||!(additional.length?['row','column','grid']:['single']).includes(plan.layout?.mode))throw Error('组合计划输出、尺寸或布局不符');
}

export function productionInstructions(route){
 const width=`按来源核对确定的宽度 ${route.requirements.widthMm} mm 处理；不得由位图像素字高自动改栏、拆图或重绘。`+(route.sourceReview.additionalSelected?.length?'组合输入按 selected 后接 additionalSelected 顺序使用公共 raster 计划；每任务一个组合输出。计划文件须作为 source_inputs 冻结，回传 quality.rasterPlan 路径和哈希；每个参与源均须独立复核内容。':'');
 switch(route.method){
  case 'raster-preserve':return '位图保留路线：保留原有内容及像素关系，按已核对的Word可见内容处理灰度、必要裁切与尺寸，交付JPG，不包装为PDF。图片内部文字不测量字号、不填字号标签，不套用可编辑正文6pt门槛。'+width+'必须独立检查内容完整、关键文字可辨与灰度后信息保留；真正缺失或语义损失不能以免字号检查掩盖。';
  case 'editable-pdf':return '可编辑图路线：复用公共绘图/换字工具，交付PDF。核对实际可编辑正文，8 pt优先，6 pt为正文下限，上下角标须按明确语义识别。保持原图文字、数据与连接含义；实际渲染后独立检查内容、字体、灰度、裁切与尺寸。'+width;
  default:throw Error('未知制作路线');
 }
}

export function verifyProductionResult(task,result,options={}){
 return verifyResult(task,result,options,false);
}
export function verifyAutomaticCandidate(task,result,options={}){
 if(task.kind==='revision'||task.productionRoute?.method!=='raster-preserve')throw Error('自动候选仅支持常规JPG，PDF及修订仍走原独立复核');
 if(!result.quality?.rasterPlan||!result.selfCheck)throw Error('自动候选缺少冻结raster计划或执行者看图自检记录');
 return verifyResult(task,result,options,true);
}
function verifyResult(task,result,{python}={},automatic){
 const route=assertProductionRoute(task),raster=route.method==='raster-preserve';
 if(!Array.isArray(result.outputs)||result.outputs.length!==task.outputNumbers.length)throw Error('回传导出集合与路线任务不一致');
 const seen=new Set();
 for(const output of result.outputs){
  if(!task.outputNumbers.includes(output.number)||seen.has(output.number))throw Error('回传导出图号不符');seen.add(output.number);
  const actual=child(task.attemptDir,output.path),bytes=fs.readFileSync(actual),extension=path.extname(actual).toLowerCase();
  if(raster?(!['.jpg','.jpeg'].includes(extension)||bytes[0]!==255||bytes[1]!==216):(extension!=='.pdf'||!bytes.subarray(0,5).equals(Buffer.from('%PDF-'))))throw Error(raster?'位图保留路线必须交付实际JPG，不能包装为PDF':'可编辑路线必须交付实际PDF');
  if(digest(actual)!==output.sha256)throw Error('回传产物哈希不一致');
  if(raster&&output.fontLabel!=='')throw Error('位图内部字号不得作为交付标签');
 }
 const evidence=result.quality?.contract;
 if(!evidence)throw Error('缺少独立质量合同及复核回执');
 ref(evidence,true);const contractPath=child(task.attemptDir,evidence.path),contract=JSON.parse(fs.readFileSync(contractPath,'utf8'));
 child(task.attemptDir,contract.workspace);
 if(contract.id!==task.id||!sameRef(contract.source,route.sourceReview.selected))throw Error('独立质量合同绑定了另一任务或源件');
 if(raster?contract.route!=='raster':!['diagram','circuit','source-preserving-chart'].includes(contract.route))throw Error('独立质量合同路线不符');
 if(!Array.isArray(contract.source_inputs)||routeSourceRefs(route).some(p=>!contract.source_inputs.some(c=>sameRef(c,p))))throw Error('独立质量合同未覆盖原包、Word、来源清单及候选源件');
 verifyRasterPlan(task,result,contract);
 if(!Array.isArray(contract.outputs)||contract.outputs.length!==result.outputs.length)throw Error('独立质量合同产物集合不符');
 const bindings=[];
 for(const output of result.outputs){
  const matches=contract.outputs.filter(c=>samePath(path.resolve(contract.workspace,c.path),output.path));
  if(matches.length!==1||matches[0].format!==route.requirements.format||Math.abs(matches[0].width_mm-route.requirements.widthMm)>0.000001)throw Error('独立质量合同产物路径、格式或尺寸与派单不符');
  bindings.push([output,matches[0]]);
 }
 if(!nonempty(python))throw Error('未配置独立质量核验Python，不能回传');
 let checked;
 let selfCheck;
 if(automatic){
  ref(result.selfCheck,true);selfCheck=child(task.attemptDir,result.selfCheck.path);
 }
 try{
  const args=automatic?['-m','automatic_raster',contractPath,result.quality.rasterPlan.path,selfCheck]:['-m','task_quality','verify',contractPath];
  checked=JSON.parse(execFileSync(python,args,{cwd:qualityRoot,env:{...process.env,PYTHONPATH:qualityRoot,PYTHONUTF8:'1'},windowsHide:true,encoding:'utf8',timeout:120000,maxBuffer:1024*1024}));
 }catch(error){throw Error('独立质量核验未通过：'+String(error.stdout||error.message).slice(0,2000));}
 if(automatic){
  if(checked.ok!==true||checked.result?.kind!=='automatic-candidate'||checked.result?.status!=='candidate'||checked.result?.manual_status!=='pending'||digest(selfCheck)!==result.selfCheck.sha256)throw Error('自动候选检查未完成');
 }else if(checked.ok!==true||checked.phase!=='verify'||checked.result?.status!=='verified')throw Error('独立质量核验未完成');
 // The gate rendered these previews itself from the sealed current output bytes.
 for(const [output,expected] of bindings){
  output.preview=child(task.attemptDir,path.join(contract.workspace,'.task-quality',expected.id+'.preview.png'));
  output.previewSha256=digest(output.preview);
  if(digest(output.path)!==output.sha256)throw Error('独立检查期间产物发生变化');
 }
 if(digest(contractPath)!==evidence.sha256)throw Error('独立检查期间合同发生变化');
 return checked.result;
}
