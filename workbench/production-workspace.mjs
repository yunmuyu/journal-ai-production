// Mechanical contract assembly only. Decisions and review evidence belong to the executor.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {assertProductionRoute,routeSourceRefs,verifyRasterPlan} from './production-route.mjs';

const repo=fileURLToPath(new URL('../',import.meta.url));
const tools=path.join(repo,'portable-production');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
function reference(value){
 const p=typeof value==='string'?value:value.path;
 const actual={path:fs.realpathSync(p),sha256:createHash('sha256').update(fs.readFileSync(p)).digest('hex')};
 if(typeof value==='object'&&value.sha256!==actual.sha256)throw Error('证据哈希变化: '+p);
 return actual;
}
function inside(root,p){
 // Resolve existing ancestors to prevent a junction from escaping the attempt.
 let existing=path.resolve(p),tail=[];
 while(!fs.existsSync(existing)){tail.unshift(path.basename(existing));const up=path.dirname(existing);if(up===existing)throw Error('路径不存在');existing=up;}
 const actual=path.join(fs.realpathSync(existing),...tail),relative=path.relative(fs.realpathSync(root),actual);
 if(!relative||relative.startsWith('..')||path.isAbsolute(relative))throw Error('路径必须在当前attempt内部: '+p);
 return actual;
}
const required=['producer','history','frozen_manifest','author_roots','delivery_target','runtime','allowed_changes','immutable_content','failure_policy'];
const dimensionsCode=`import json,sys
from raster.render import load_input,compose,positive
p=json.load(open(sys.argv[1],encoding='utf-8-sig'))
images=[load_input(i,p.get('grayscale_weights'))[0] for i in p['inputs']]
canvas,_=compose(images,p['layout'])
w,h=canvas.size
if p.get('target_dpi') is not None:
    new=round(p['width_mm']/25.4*positive(p['target_dpi'],'target_dpi'))
    h=max(1,round(h*new/w));w=new
print(json.dumps({'pixels':[w,h],'dpi':w*25.4/p['width_mm']}))`;

/** Existing task and executor-authored plan + evidence. Does not render or run precheck. */
export function prepareProductionWorkspace(taskPath,planPath,evidence={},contractPath){
 const task=read(taskPath),route=assertProductionRoute(task);
 if(route.method!=='raster-preserve'||task.outputNumbers.length!==1)throw Error('当前入口仅组装每任务一个输出的公共raster合同');
 const attempt=fs.realpathSync(task.attemptDir);
 inside(attempt,taskPath);inside(attempt,planPath);
 const plan=read(planPath),planRef=reference(planPath),output=inside(attempt,plan.output);
 if(path.extname(output).toLowerCase()!=='.jpg')throw Error('输出必须是JPG');
 const workspace=path.dirname(output);
 if(workspace===attempt)throw Error('输出须放入独立candidate子目录');
 const sourceInputs=[...routeSourceRefs(route).map(reference),reference(taskPath),planRef];
 verifyRasterPlan(task,{outputs:[{path:output}],quality:{rasterPlan:planRef}},{source_inputs:sourceInputs});
 const missing=required.filter(k=>evidence[k]===undefined);
 for(const [group,keys] of [['runtime',['python','font_profile']],['history',['evidence','conclusion','reusable','revision_authorization']]]){
  if(evidence[group])for(const key of keys)if(evidence[group][key]===undefined)missing.push(group+'.'+key);
 }
 if(missing.length)return {status:'needs_evidence',missing,
  guidance:'执行者提供实际历史核对记录引用、保护文件清单、运行环境和交付位置；工具不生成checked或视觉结论。',
  mechanical:{id:task.id,workspace,source_inputs:sourceInputs,plan:planRef}};
 const python=reference(evidence.runtime.python),profile=reference(evidence.runtime.font_profile);
 const history={...evidence.history,evidence:reference(evidence.history.evidence)};
 const frozen=reference(evidence.frozen_manifest);
 const env={...process.env,PYTHONPATH:tools,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
 const run=(code,args=[],input)=>execFileSync(python.path,['-X','utf8','-c',code,...args],{
  env,encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer:1024*1024,input});
 // Public raster primitives compute declared crop/layout dimensions in memory; no artifact is produced.
 const measured=JSON.parse(run(dimensionsCode,[planPath]));
 const code=fs.readdirSync(path.join(tools,'raster')).filter(n=>n.endsWith('.py')).map(n=>reference(path.join(tools,'raster',n)));
 code.push(reference(fileURLToPath(import.meta.url)));
 const contract={id:task.id,producer:evidence.producer,route:'raster',source:route.sourceReview.selected,
  source_inputs:[...new Map(sourceInputs.map(r=>[r.path,r])).values()],history,frozen_manifest:frozen,
  workspace,author_roots:evidence.author_roots,runtime:{python,code_root:repo,code,font_profile:profile},
  outputs:[{id:'fig'+task.outputNumbers[0].replace(/[.-]/g,'_'),path:path.basename(output),delivery_target:evidence.delivery_target,
   format:'jpg',width_mm:plan.width_mm,pixels:measured.pixels,dpi:measured.dpi,stroke_pt:null}],
  mechanical:['dimensions','pixels','dpi','artifact_set','preview_hashes'],
  manual_review:['source_content','visual','runtime_provenance','readability','grayscale_semantics'],
  allowed_changes:evidence.allowed_changes,immutable_content:evidence.immutable_content,failure_policy:evidence.failure_policy};
 // Reuse the strict quality schema, but do not create an envelope or claim any review happened.
 run('import json,sys\nfrom task_quality.models import Contract\nContract.parse(json.load(sys.stdin))',[],JSON.stringify(contract));
 if(!contractPath)return {status:'prepared',contract,plan:planRef,next:'Write contract, then run task_quality precheck; no quality check has run.'};
 const target=inside(attempt,contractPath);
 if(target===output||target.startsWith(workspace+path.sep))throw Error('合同不能写入产物目录');
 fs.writeFileSync(target,JSON.stringify(contract,null,2)+'\n',{encoding:'utf8',flag:'wx'});
 return {status:'prepared',contract:reference(target),plan:planRef,next:'Run task_quality precheck before production; independent review is still required.'};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  const [task,plan,evidence,target]=process.argv.slice(2);
  if(!task||!plan)throw Error('Usage: node production-workspace.mjs task.json raster-plan.json [existing-evidence.json] [quality-contract.json]');
  console.log(JSON.stringify(prepareProductionWorkspace(task,plan,evidence?read(evidence):{},target),null,2));
 }catch(error){console.error(error.message);process.exitCode=1;}
}
