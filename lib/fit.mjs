import{withAdobeSession}from'./desktop-notice.mjs';
import path from 'node:path';
import {readJson,writeJson,logEvent} from './core.mjs';
import {render} from './render.mjs';
export function fit(root,planFile){return withAdobeSession(['Illustrator','Photoshop'],()=>fitInternal(root,planFile));}
function fitInternal(root,planFile){
 const original=readJson(planFile),trials=[];
 const doubleEvidence=original.columnConstraint!=='single'&&typeof original.doubleColumnRationale==='string'&&original.doubleColumnRationale.trim()&&typeof original.singleColumnRevisionEvidence==='string'&&original.singleColumnRevisionEvidence.trim();
 function decision(value){writeJson(path.join(root,'fit',original.figureId,'decision.json'),value);logEvent(root,{event:'column_fit',id:original.figureId,...value});return value;}
 for(const widthMm of original.columnConstraint==='double'?[160]:doubleEvidence?[80,160]:[80]){
  const plan={...original,widthMm};
  if(plan.graph)plan.graph={...plan.graph,widthClass:widthMm===80?'single':'double'};
  const candidate=path.join(root,'fit',plan.figureId,String(widthMm)+'-base.json');writeJson(candidate,plan);
  let result;
  try{result=render(root,planFile,{reuseOnly:true,fitSource:true});if(!result)result=render(root,candidate);}catch(error){
   if(!/LAYOUT_REFLOW_REQUIRED|REUSE_UNVERIFIED|MECHANICAL_CHECK_FAILED/.test(error.message))throw error;
   trials.push({widthMm,issues:[{type:/REUSE_UNVERIFIED/.test(error.message)?'reuse_unverified':'layout_reflow_required',message:error.message}]});
   if(/REUSE_UNVERIFIED/.test(error.message))break;
   continue;
  }
  function measured(r){const b=r.adobe.snapshot.artboard;return {actualWidthMm:(b[2]-b[0])*25.4/72,fontSize:Math.min(...(r.adobe.snapshot.texts||[]).map(t=>t.size),plan.fontSize),issues:[...(r.adobe.mechanicalIssues||[])]};}
  let current=measured(result);
  trials.push({widthMm,...current,planHash:result.planHash,pdfPreview:result.pdfPreview,reused:result.cached===true});
  if(!current.issues.length&&current.actualWidthMm>widthMm+.001){
   const factor=widthMm/current.actualWidthMm,minimum=current.fontSize*factor;
   if(minimum<6-1e-8){trials.push({widthMm,factor,minFontSize:minimum,issues:[{type:'uniform_scale_below_minimum_font'}]});continue;}
   const basePlan=result.planFile?readJson(result.planFile):plan;
   const scaled={...basePlan,widthMm,columnConstraint:original.columnConstraint,fontSize:Math.max(6,basePlan.fontSize*factor),uniformScaleFrom:{recordFile:result.recordFile||path.join(path.dirname(result.planFile),'render.json'),ai:result.ai,aiHash:result.aiHash,factor}};
   if(scaled.graph)scaled.graph={...scaled.graph,fontSize:scaled.fontSize};
   const file=path.join(root,'fit',plan.figureId,String(widthMm)+'-scaled.json');writeJson(file,scaled);
   result=render(root,file);current=measured(result);
   if(current.actualWidthMm>widthMm+.001)current.issues.push({type:'layout_exceeds_column'});
   trials.push({widthMm,...current,factor,planHash:result.planHash,pdfPreview:result.pdfPreview,reused:result.cached===true});
  }
  if(current.fontSize<6-1e-8)current.issues.push({type:'font_below_minimum'});
  if(!current.issues.length)return {decision:decision({widthMm,fontSize:current.fontSize,baseFontSize:plan.fontSize,reason:plan.route==='image'?'bitmap_geometry_fits_readability_unverified':widthMm===80?'single_column_fits_by_reuse_or_uniform_scale':'double_column_with_recorded_editorial_evidence',trials,requiresVisualReview:true}),render:result};
 }
 return {decision:decision({widthMm:null,reason:'layout_revision_required',trials,requiresVisualReview:true})};
}
