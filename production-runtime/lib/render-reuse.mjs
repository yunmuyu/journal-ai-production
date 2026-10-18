import {existsSync,readdirSync} from 'node:fs';
import path from 'node:path';
import {readJson} from './core.mjs';
import {assertColorAudit} from './color-policy.mjs';
export function renderingPlanKey(plan){
 const visual={...plan};delete visual.widthDecision;
 function ordered(value){
  if(Array.isArray(value))return value.map(ordered);
  if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,ordered(value[k])]));
  return value;
 }
 return JSON.stringify(ordered(visual));
}
export function fitSourcePlanKey(plan){
 const source={...plan};for(const field of ['widthMm','columnConstraint','doubleColumnRationale','singleColumnRevisionEvidence'])delete source[field];
 if(source.graph){source.graph={...source.graph};delete source.graph.widthClass;}
 return renderingPlanKey(source);
}
export function reusableRender(root,figure,plan,tools,{forFit=false}={}){
 const key=forFit?fitSourcePlanKey:renderingPlanKey;
 const directory=path.join(root,'renders',figure.id);if(!existsSync(directory))return null;
 let unverifiable=false;
 for(const name of readdirSync(directory).sort()){
  const file=path.join(directory,name,'render.json');if(!existsSync(file))continue;
  const old=readJson(file);if(!old.ok||old.sourceHash!==plan.sourceHash||!existsSync(old.planFile)||key(readJson(old.planFile))!==key(plan))continue;
  try{
   if(!tools.every(t=>(old.toolHashes||[]).some(prior=>path.basename(prior.file)===path.basename(t.file)&&prior.sha256===t.sha256)))throw Error('Tool revision differs');
   assertColorAudit(old);
   if(old.adobe?.mechanicalIssues?.length)throw Error('Mechanical issues remain');
   return {...old,cached:true,recordFile:file,reuseReason:'identical_artwork_plan_and_verified_artifacts'};
  }catch(invalid){unverifiable=true;}
 }
 if(unverifiable)throw Error('REUSE_UNVERIFIED: matching artwork exists but current artifact/tool evidence cannot be verified; no automatic redraw');
 return null;
}
