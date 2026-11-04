// Boundary checks absorbed from side-unified-delivery; not a second runner or lock.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
const exec=promisify(execFile),repo=fileURLToPath(new URL('../',import.meta.url));
export async function fixedProductionRuntime(config){
 const lock=config.runtimeLock;
 if(!lock?.engineSignature)throw Error('runtime_lock_required');
 for(const [key,p] of [['python',config.python],['fontProfile',config.fontProfile]]){
  const r=lock[key];
  if(!r?.path||path.relative(fs.realpathSync(r.path),fs.realpathSync(p))!==''||createHash('sha256').update(fs.readFileSync(p)).digest('hex')!==r.sha256)throw Error('runtime_artifact_hash_changed: '+key);
 }
 const engineRoot=path.join(repo,'portable-production','direct-pdf');
 const result=await exec(config.python,['-c','import json,journal_pdf; from journal_pdf.editorial import engine_signature; print(json.dumps({"module":journal_pdf.__file__,"signature":engine_signature()}))'],{cwd:engineRoot,env:{...process.env,PYTHONPATH:engineRoot,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'},windowsHide:true,timeout:30000});
 const engine=JSON.parse(result.stdout),relative=path.relative(fs.realpathSync(engineRoot),fs.realpathSync(engine.module));
 if(relative.startsWith('..'+path.sep)||relative==='..'||path.isAbsolute(relative)||engine.signature!==lock.engineSignature)throw Error('engine_version_mismatch');
 return engine;
}

export function assertRenderedBoundary(report,output,route,signature){
 if(report.status!=='candidate-rendered'||report.pdf_sha256!==output.sha256||report.engine_signature!==signature)throw Error('renderer_report_mismatch');
 const actual=report.pdf_audit?.width_mm;
 if(!Number.isFinite(actual)||actual<=0||actual>route.requirements.widthMm+.01)throw Error('rendered_width_exceeds_plan');
 return actual;
}

export function assertPlanSources(spec,sourceRoot,outputRoot){
 const root=fs.realpathSync(sourceRoot),within=p=>{const r=path.relative(root,p);return r===''||(!r.startsWith('..'+path.sep)&&r!=='..'&&!path.isAbsolute(r));};
 if(within(fs.realpathSync(outputRoot)))throw Error('output_source_overlap');
 if(!Array.isArray(spec.sources)||!spec.sources.length||spec.synthetic)throw Error('bound_real_sources_required');
 for(const source of spec.sources){
  const p=fs.realpathSync(path.resolve(root,source.path));
  if(!within(p))throw Error('source_outside_root');
  if(createHash('sha256').update(fs.readFileSync(p)).digest('hex')!==source.sha256)throw Error('source_hash_changed');
 }
}
