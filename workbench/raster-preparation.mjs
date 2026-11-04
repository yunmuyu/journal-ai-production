// Absorbs journal-runner's plan preparation idea, using the current shared engine.
// This module never chooses a processing route, publishes, or approves an output.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {processingRequirement} from './processing-evidence.mjs';
const exec=promisify(execFile),root=fileURLToPath(new URL('../portable-production/',import.meta.url));
const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;
const fingerprint=value=>createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const measureCode=`import json,sys
from raster.render import load_input
image, facts = load_input(json.loads(sys.argv[1]))
print(json.dumps(facts))
image.close()`;

export async function prepareRasterPlan({route,options,python,cache=new Map()}){
 processingRequirement(route);
 if(route.method!=='raster-preserve')throw Error('auto_plan_requires_preserve');
 if(!options||!Object.hasOwn(options,'crop'))throw Error('explicit_crop_required');
 if(Object.keys(options).some(k=>!['crop','quality'].includes(k)))throw Error('unsupported_auto_plan_option');
 const crop=options.crop;
 if(crop!==null&&(!Array.isArray(crop)||crop.length!==4||crop.some(v=>!Number.isSafeInteger(v))))throw Error('crop_bounds');
 if(route.sourceReview?.additionalSelected?.length)throw Error('composition_requires_explicit_plan');
 const source=route.sourceReview?.selected,width=route.requirements?.widthMm,quality=options.quality??95;
 if(!source?.path||!source.sha256||hash(source.path)!==source.sha256)throw Error('source_hash_changed');
 if(!Number.isFinite(width)||width<=0)throw Error('invalid_width');
 if(!Number.isInteger(quality)||quality<90||quality>100)throw Error('invalid_quality');
 const interpreter=typeof python==='string'?python:python?.path;
 if(!interpreter||!path.isAbsolute(interpreter))throw Error('explicit_python_required');
 const pythonSha256=hash(interpreter);
 if(typeof python==='object'&&python.sha256!==pythonSha256)throw Error('python_hash_changed');
 const input={path:fs.realpathSync(source.path),sha256:source.sha256,crop};
 const runtime={pythonSha256,engineSha256:hash(path.join(root,'raster','render.py'))};
 const key=fingerprint({input,runtime});
 if(!cache.has(key))cache.set(key,exec(interpreter,['-X','utf8','-c',measureCode,JSON.stringify(input)],{cwd:root,env:{...process.env,PYTHONPATH:root,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'},windowsHide:true,timeout:120000,maxBuffer:1024*1024}).then(r=>JSON.parse(r.stdout)).catch(e=>{cache.delete(key);throw Error(String(e.stderr||e.message));}));
 const facts=await cache.get(key);
 if(hash(source.path)!==source.sha256)throw Error('source_changed_during_measurement');
 return {plan:{version:1,inputs:[input],layout:{mode:'single',gap_px:0},width_mm:width,quality,target_dpi:null},
  measurement:{...facts,effective_source_dpi:facts.cropped_pixels[0]*25.4/width,semantic_verified:false},runtime};
}

// Reuse is a proposal only. Callers must supply current authoritative acceptance,
// not a cached 'approved' event; no second ledger or automatic acceptance is created.
export function rasterReuseKey({identity,wordSha256,processing,plan,runtime,policySha256}){
 if(!['batchHash','articleId','figureId','number'].every(k=>typeof identity?.[k]==='string'&&identity[k])||!wordSha256||!processing?.operation||!plan?.inputs?.length||!runtime?.pythonSha256||!runtime?.engineSha256||!policySha256)throw Error('reuse_context_incomplete');
 return fingerprint({version:1,identity,wordSha256,processing,policySha256,runtime,
  plan:{inputs:plan.inputs.map(i=>({sha256:i.sha256,crop:i.crop})),layout:plan.layout,width_mm:plan.width_mm,quality:plan.quality??95,target_dpi:plan.target_dpi??null,grayscale_weights:plan.grayscale_weights??null}});
}
export function findAcceptedRasterReuse(context,records,currentAcceptance){
 const key=rasterReuseKey(context),accepted=currentAcceptance[context.identity.figureId];
 if(accepted?.accepted!==true)return null;
 for(const record of [...records].reverse()){
  if(record.key!==key||record.figureId!==context.identity.figureId||!record.acceptanceVersion||record.acceptanceVersion!==accepted.version)continue;
  try{if(record.output?.path&&hash(record.output.path)===record.output.sha256)return structuredClone(record);}catch(error){if(error.code!=='ENOENT')throw error;}
 }
 return null;
}
