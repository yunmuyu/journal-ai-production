import{withAdobeSession}from'./desktop-notice.mjs';
import path from 'node:path';
import {readJson,writeJson,logEvent} from './core.mjs';
import {render} from './render.mjs';
export function fit(root,planFile){return withAdobeSession(['Illustrator','Photoshop'],()=>fitInternal(root,planFile));}
function fitInternal(root,planFile){
 const original=readJson(planFile),trials=[];
 const hasDoubleColumnEvidence=typeof original.doubleColumnRationale==='string'&&original.doubleColumnRationale.trim()&&typeof original.singleColumnRevisionEvidence==='string'&&original.singleColumnRevisionEvidence.trim();
 const widths=hasDoubleColumnEvidence?[80,160]:[80];
 for(const widthMm of widths){
  const plan={...original,widthMm};
  if(plan.graph)plan.graph={...plan.graph,widthClass:widthMm===80?'single':'double'};
  const candidate=path.join(root,'fit',plan.figureId,String(widthMm)+'-base.json');writeJson(candidate,plan);
  let result=render(root,candidate),b=result.adobe.snapshot.artboard,actualWidth=(b[2]-b[0])*25.4/72;
  let issues=[...(result.adobe.mechanicalIssues||[])];
  trials.push({widthMm,fontSize:plan.fontSize,actualWidthMm:actualWidth,issues,planHash:result.planHash,pdfPreview:result.pdfPreview,reused:result.cached===true});
  if(!issues.length&&actualWidth>widthMm){
   const factor=widthMm/actualWidth,minFont=Math.min(...(result.adobe.snapshot.texts||[]).map(t=>t.size),plan.fontSize)*factor;
   if(minFont<6){trials.push({widthMm,factor,minFontSize:minFont,issues:[{type:'uniform_scale_below_minimum_font'}]});continue;}
   const scaled={...plan,fontSize:plan.fontSize*factor,uniformScaleFrom:{recordFile:result.recordFile||path.join(path.dirname(result.planFile),'render.json'),ai:result.ai,aiHash:result.aiHash,factor}};
   if(scaled.graph)scaled.graph={...scaled.graph,fontSize:scaled.fontSize};
   const scaledFile=path.join(root,'fit',plan.figureId,String(widthMm)+'-scaled.json');writeJson(scaledFile,scaled);
   result=render(root,scaledFile);b=result.adobe.snapshot.artboard;actualWidth=(b[2]-b[0])*25.4/72;issues=[...(result.adobe.mechanicalIssues||[])];
   if(actualWidth>widthMm+0.01)issues.push({type:'layout_exceeds_column'});
   trials.push({widthMm,fontSize:scaled.fontSize,actualWidthMm:actualWidth,factor,issues,planHash:result.planHash,pdfPreview:result.pdfPreview,reused:result.cached===true});
  }
  if(!issues.length){const fontSize=trials.at(-1).fontSize,decision={widthMm,fontSize,reason:plan.route==='image'?'bitmap_geometry_fits_readability_unverified':widthMm===80?'single_column_fits_by_reuse_or_uniform_scale':'double_column_with_recorded_editorial_evidence',trials,requiresVisualReview:true};writeJson(path.join(root,'fit',plan.figureId,'decision.json'),decision);logEvent(root,{event:'column_fit',id:plan.figureId,...decision});return {decision,render:result};}
 }
 const decision={widthMm:null,reason:'layout_revision_required',trials,requiresVisualReview:true};writeJson(path.join(root,'fit',original.figureId,'decision.json'),decision);return {decision};
}
