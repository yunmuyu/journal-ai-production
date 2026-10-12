import path from 'node:path';
import {convertSvg} from './svg.mjs';
import {addFigure} from './jobs.mjs';
import {render} from './render.mjs';
import {readJson,writeJson} from './core.mjs';

export function chartLabels(panel,snapshot){
 const [W,H]=panel.pageSizePt,[left,top,right,bottom]=panel.plotBoundsPt;
 const numericY=top+(bottom-top)/2;
 const texts=panel.labels.filter(t=>t.role!=='panel-title'||!/^[（(][a-zA-Z][）)]/.test(t.text)).map(label=>{
  let {text,x,y}=label,align='left',rotation=0;
  if(label.role.endsWith('title'))text=text.replace(/\s*\(([^()]+)\)\s*$/,'/$1');
  if(label.role==='annotation')text=text.replace(/(\d+[.])(\d{4,})/g,(_,prefix,digits)=>prefix+digits.match(/.{1,3}/g).join(' '));
  if(/[一-鿿]/.test(text))text=text.replace(/ *[(]/g,'（').replace(/[)]/g,'）');
  if(label.role==='x-tick'){y=bottom+3.5*panel.sourceScale+2.5+2.75;align='center';}
  if(label.role==='y-tick'){x=left-3.5*panel.sourceScale-2.5;align='right';}
  if(label.role==='x-title'){x=(left+right)/2;y=bottom+3.5*panel.sourceScale+2.5+5.5+3+2.84;align='center';}
  if(label.role==='panel-title'){x=(left+right)/2;y=top-7;align='center';}
  if(label.role==='y-title'){x=6;y=numericY;align='center';rotation=90;}
  const t={text,x:x/W,y:y/H,align,valign:'center',anchor:'ink',rotation};
  if(text.startsWith('R²'))t.styles=[{start:0,length:1,font:'TimesNewRomanPS-ItalicMT'}];
  if(/y=x/.test(text)){const n=text.indexOf('y=x');t.styles=[{start:n,length:1,font:'TimesNewRomanPS-ItalicMT'},{start:n+2,length:1,font:'TimesNewRomanPS-ItalicMT'}];}
  return {...t,role:label.role};
 });
 const annotations=texts.filter(t=>t.role==='annotation');
 if(annotations.length){const start=top+9;annotations.forEach((t,i)=>{t.x=(left+6)/W;t.y=(start+i*9.6)/H;});}
 if(snapshot){
  const find=t=>snapshot.texts.find(s=>s.name==='JFW_TEXT_'+(texts.indexOf(t)+1));
  const yTicks=texts.filter(t=>t.role==='y-tick'),xTicks=texts.filter(t=>t.role==='x-tick');
  const yTitle=texts.find(t=>t.role==='y-title'),xTitle=texts.find(t=>t.role==='x-title');
  if(yTitle){const ink=find(yTitle).inkBounds;const min=Math.min(...yTicks.map(t=>find(t).inkBounds[0]));yTitle.x=(min-3-(ink[2]-ink[0])/2)/W;}
  if(xTitle){const ink=find(xTitle).inkBounds;const bottomTick=Math.min(...xTicks.map(t=>find(t).inkBounds[3]));xTitle.y=(-bottomTick+3+(ink[1]-ink[3])/2)/H;}
 }
 return texts;
}

export function checkChartTypography(panel,plan,snapshot){
 const [l,t,r,b]=panel.plotBoundsPt,expected=[l,-t,r,-b];
 const realFrame=snapshot.pathGeometry.find(p=>{if(!p.closed||p.points.length<4)return false;const xs=p.points.map(v=>v[0][0]),ys=p.points.map(v=>v[0][1]);const bounds=[Math.min(...xs),Math.max(...ys),Math.max(...xs),Math.min(...ys)];return bounds.every((v,i)=>Math.abs(v-expected[i])<.05);});
 if(!realFrame)throw Error('Actual plot frame does not match the label coordinate system');
 const find=(t,i)=>snapshot.texts.find(s=>s.name==='JFW_TEXT_'+(i+1));
 const rows=plan.texts.map((t,i)=>({...t,ink:find(t,i).inkBounds}));
 const expectedLabels=chartLabels(panel),titleRoles=['x-title','y-title'];
 for(let index=0;index<plan.texts.length;index++){const label=plan.texts[index];if(['x-title','y-title','x-tick','y-tick','legend'].includes(label.role)){const actual=find(label,index);if(!actual||actual.text!==label.text)throw Error('Actual chart label identity mismatch');}}
 const titleIdentity=labels=>labels.filter(label=>titleRoles.includes(label.role)).map(label=>JSON.stringify([label.role,label.text])).sort();
 if(JSON.stringify(titleIdentity(expectedLabels))!==JSON.stringify(titleIdentity(plan.texts)))throw Error('Axis title source multiset mismatch');
 for(const role of titleRoles)if(expectedLabels.filter(label=>label.role===role).length>1)throw Error('Source axis title identity is ambiguous');
 for(const role of ['x-tick','y-tick']){
  const sourceTicks=panel.labels.filter(label=>label.role===role),actualTicks=rows.filter(label=>label.role===role);
  if(sourceTicks.length!==actualTicks.length)throw Error('Tick source count mismatch');
  const used=new Set();
  for(const tick of sourceTicks){const matches=actualTicks.filter(label=>label.text===tick.text);if(matches.length!==1||used.has(matches[0]))throw Error('Tick source identity is ambiguous');const actual=matches[0];used.add(actual);const center=role==='y-tick'?-(actual.ink[1]+actual.ink[3])/2:(actual.ink[0]+actual.ink[2])/2,expected=role==='y-tick'?tick.y:tick.x;if(!Number.isFinite(center)||!Number.isFinite(expected)||Math.abs(center-expected)>.02)throw Error('Tick ink center does not match source marker');}
 }
 const sourceLegend=expectedLabels.filter(label=>label.role==='legend'),actualLegend=rows.filter(label=>label.role==='legend');
 if(sourceLegend.length!==actualLegend.length)throw Error('Legend label source count mismatch');
 for(const label of sourceLegend){const matches=actualLegend.filter(actual=>actual.text===label.text);if(matches.length!==1)throw Error('Legend label source identity is ambiguous');const center=-(matches[0].ink[1]+matches[0].ink[3])/2;if(!Number.isFinite(center)||!Number.isFinite(label.y)||Math.abs(center-label.y*panel.pageSizePt[1])>.02)throw Error('Legend label ink center does not match prepared source sample row');}
 const yTitle=rows.find(t=>t.role==='y-title'),xTitle=rows.find(t=>t.role==='x-title');
 const gaps={};
 if(yTitle)gaps.yTitlePt=Math.min(...rows.filter(t=>t.role==='y-tick').map(t=>t.ink[0]))-yTitle.ink[2];
 if(xTitle)gaps.xTitlePt=Math.min(...rows.filter(t=>t.role==='x-tick').map(t=>t.ink[3]))-xTitle.ink[1];
 if(Object.values(gaps).some(v=>Math.abs(v-3)>.02))throw Error('Axis title ink gap failed: '+JSON.stringify(gaps));
 const legend=rows.filter(t=>t.role==='legend');
 if(legend.length>1&&Math.max(...legend.map(t=>t.ink[0]))-Math.min(...legend.map(t=>t.ink[0]))>.02)throw Error('Legend left alignment failed');
 return {gaps,actualPlotFrameVerified:true,plotWidthMm:(r-l)*25.4/72,plotHeightMm:(b-t)*25.4/72,texts:rows.length,legendRows:legend.length,axisTitleMultisetVerified:true,tickInkCentersVerified:true,legendLabelRowsVerified:true,actualLegendSampleIdentityVerified:false,legendAuditScope:'Label ink center against prepared sample_y only; actual sample geometry/identity requires independent dataAudit'};
}

export function renderOutlinedChart(root,panel,metadata){
 const start=performance.now();
 const f=addFigure(root,{...metadata,source:panel.svg});
 const [W,H]=panel.pageSizePt;
 const plan={version:1,figureId:f.id,sourceHash:f.sourceHash,route:'vector-reletter',nativeSvg:true,normalizeWidth:false,widthMm:W*25.4/72,heightMm:H*25.4/72,fontSize:8,grayscale:true,replacements:[],strokeWidthPt:.5,texts:chartLabels(panel),tightExport:false,crop:[0,0,0,0]};
 const target=path.resolve(root,'plan-'+metadata.number+'.json');writeJson(target,plan);
 const initial=render(root,target);
 if(!initial.ok)throw Error('Initial chart rendering failed');
 plan.texts=chartLabels(panel,initial.adobe.snapshot);writeJson(target,plan);
 const result=render(root,target);
 if(!result.ok||!result.pdfAudit.ok||result.adobe.mechanicalIssues.length)throw Error('Final chart verification failed: '+JSON.stringify(result.adobe.mechanicalIssues));
 result.chartCheck=checkChartTypography(panel,plan,result.adobe.snapshot);
 result.processingSeconds=(performance.now()-start)/1000;
 result.conversionSeconds=0;
 writeJson(path.resolve(root,'result-'+metadata.number+'.json'),result);
 return result;
}
