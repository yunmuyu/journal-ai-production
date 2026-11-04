// Validate semantic decisions before opening Office or touching a source copy.
import path from 'node:path';

export function buildPptxPlan(proposal,decision,source){
 if(proposal?.version!==1||proposal.sourceSha256!==source.sha256||decision.sourceSha256!==source.sha256||proposal.slide!==decision.slide)
  throw Error('pptx_plan_source: 候选与语义决定必须绑定当前PPTX');
 if(!Array.isArray(proposal.series)||!proposal.series.length||proposal.unresolved?.length)
  throw Error('pptx_series_bindings_incomplete: '+JSON.stringify(proposal.unresolved??[]));
 if(typeof decision.evidence!=='string'||!decision.evidence.trim()||typeof decision.confirmedDecorativeShadows!=='boolean'||decision.confirmedSeries!==true||decision.autoDistinguish!==true)
  throw Error('pptx_semantic_confirmation_missing: 先核对图号、系列、图例和阴影语义');
 const labels=decision.seriesLabels;
 if(!labels||proposal.series.some(s=>typeof labels[s.color]!=='string'||!labels[s.color].trim())||Object.keys(labels).length!==proposal.series.length)
  throw Error('pptx_series_label_binding: 每个源系列须绑定当前图的文字');
 // Two styles are available. Preserve existing dashes and fail rather than
 // pretend three same-marker/similar-gray series are distinguishable.
 const rows=proposal.series,edges=rows.map(()=>[]);
 for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++)
  if(rows[i].marker===rows[j].marker&&Math.abs(rows[i].gray-rows[j].gray)<64){edges[i].push(j);edges[j].push(i);}
 const styles=Array(rows.length).fill(null);
 for(let root=0;root<rows.length;root++){
  if(styles[root]!==null)continue;
  const color=Array(rows.length).fill(null),members=[],queue=[root];color[root]=0;
  while(queue.length){const i=queue.shift();members.push(i);for(const j of edges[i]){
   if(color[j]===null){color[j]=1-color[i];queue.push(j);}
   else if(color[j]===color[i])throw Error('pptx_series_more_styles_required');
  }}
  const pins=members.filter(i=>rows[i].dash!=='solid').map(i=>1-color[i]);
  if(new Set(pins).size>1)throw Error('pptx_series_existing_style_conflict');
  const flip=pins[0]??0;for(const i of members)styles[i]=(color[i]+flip)%2;
 }
 const dashedSeries=rows.filter((s,i)=>styles[i]===1&&s.dash==='solid').map(s=>({curveShapeIds:s.curveShapeIds,legendShapeIds:s.legendShapeIds}));
 return validatePptxPlan({version:1,sourceSha256:source.sha256,slide:proposal.slide,
  shadowShapeIds:decision.confirmedDecorativeShadows?proposal.shadowCandidates:[],
  stroke:{shapeIds:proposal.strokeShapeIds,sourcePlotWidthPt:proposal.sourcePlotWidthPt,targetPlotWidthPt:decision.targetPlotWidthPt,finalStrokePt:.5},
  dashedSeries,evidence:decision.evidence,seriesBindings:rows.map(s=>({color:s.color,label:labels[s.color],marker:s.marker,pointCount:s.pointCount}))},source,true);
}

export function validatePptxPlan(plan,source,python){
 if(!plan||plan.version!==1||plan.sourceSha256!==source.sha256)throw Error('pptx_plan_source: 制作决定未绑定当前来源');
 if(path.extname(source.path).toLowerCase()!=='.pptx'||!Number.isSafeInteger(plan.slide)||plan.slide<1||typeof plan.evidence!=='string'||!plan.evidence.trim()||!python)
  throw Error('pptx_plan_invalid: 须提供PPTX页号、来源核对依据及配置Python');
 const ids=(value,name,allowEmpty=true)=>{
  if(!Array.isArray(value)||!allowEmpty&&!value.length||value.some(x=>!Number.isSafeInteger(x)||x<1)||new Set(value).size!==value.length)
   throw Error('pptx_plan_shape_ids: '+name);
 };
 ids(plan.shadowShapeIds??[],'shadowShapeIds');
 if(plan.stroke){
  ids(plan.stroke.shapeIds,'stroke.shapeIds',false);
  const {sourcePlotWidthPt,targetPlotWidthPt,finalStrokePt}=plan.stroke;
  if(![sourcePlotWidthPt,targetPlotWidthPt,finalStrokePt].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>0)||
     finalStrokePt!==.5||finalStrokePt*sourcePlotWidthPt/targetPlotWidthPt>50)
   throw Error('pptx_plan_stroke: 须绑定源/目标绘图区宽度和0.5pt最终线宽');
 }
 if(!Array.isArray(plan.dashedSeries??[]))throw Error('pptx_plan_series');
 const used=new Set();
 for(const series of plan.dashedSeries??[]){
  ids(series.curveShapeIds,'curveShapeIds',false);ids(series.legendShapeIds,'legendShapeIds',false);
  for(const id of [...series.curveShapeIds,...series.legendShapeIds]){
   if(used.has(id))throw Error('pptx_plan_series_duplicate');used.add(id);
  }
 }
 return plan;
}
