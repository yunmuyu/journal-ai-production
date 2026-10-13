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
  for(const fontSize of [8,7,6]){
  const plan={...original,widthMm,fontSize,widthDecision:'Automatic measured trial at '+widthMm+' mm; '+fontSize+' pt'};
  if(plan.graph)plan.graph={...plan.graph,fontSize,widthClass:widthMm===80?'single':'double'};
  const candidate=path.join(root,'fit',plan.figureId,String(widthMm)+'-'+String(fontSize)+'.json');writeJson(candidate,plan);
  const result=render(root,candidate),b=result.adobe.snapshot.artboard;
  const issues=[...(result.adobe.mechanicalIssues||[])];if((b[2]-b[0])*25.4/72>widthMm+0.4)issues.push({type:'layout_exceeds_column'});
  trials.push({widthMm,fontSize,issues,planHash:result.planHash,pdfPreview:result.pdfPreview});
   if(!issues.length){const decision={widthMm,fontSize,reason:plan.route==='image'?'bitmap_geometry_fits_readability_unverified':widthMm===80?'single_column_fits_at_'+fontSize+'pt':'double_column_with_recorded_editorial_evidence_at_'+fontSize+'pt',trials,requiresVisualReview:true};writeJson(path.join(root,'fit',plan.figureId,'decision.json'),decision);logEvent(root,{event:'column_fit',id:plan.figureId,...decision});return {decision,render:result};}
  }
 }
 const decision={widthMm:null,reason:'layout_revision_required',trials,requiresVisualReview:true};writeJson(path.join(root,'fit',original.figureId,'decision.json'),decision);return {decision};
}
