import {COLOR_RULE_VERSION,resolveColorPolicy,colorPlanHash,assertColorAudit} from './color-policy.mjs';
import {auditDiagram} from './diagram-audit.mjs';
import {convertSvg} from './svg.mjs';
import{withAdobeSession}from'./desktop-notice.mjs';
import { mkdirSync,existsSync,copyFileSync,readFileSync } from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { adobe,packageRoot } from './adobe.mjs';
import { readJson,writeJson,fileHash,sha256,validatePlan,exportPadding,resolveInside,logEvent } from './core.mjs';
import { updateFigure } from './jobs.mjs';
import { pythonRuntime } from './ingest.mjs';
export function render(root,planFile){return withAdobeSession(['Illustrator','Photoshop'],()=>renderInternal(root,planFile));}
function renderInternal(root,planFile){
 root=path.resolve(root);const p=validatePlan(readJson(planFile)),state=readJson(path.join(root,'job.json')),figure=state.figures.find(f=>f.id===p.figureId);if(!figure)throw Error('Plan figure not in job');
 const source=resolveInside(root,figure.source);if(fileHash(source)!==p.sourceHash||figure.sourceHash!==p.sourceHash)throw Error('Plan source revision mismatch');
 const colorPolicy=resolveColorPolicy(p,p.sourceHash);p.colorPolicy=colorPolicy.mode;p.grayscale=colorPolicy.mode==='grayscale';p.colorRuleVersion=COLOR_RULE_VERSION;
 const effectiveCrop=p.crop||figure.crop||[0,0,0,0];p.crop=effectiveCrop;validatePlan(p);
 const generator=path.join(process.env.JFW_FLOWCHART_ROOT||path.join(packageRoot,'flowchart'),'assets/AI流程图生成器.jsx');
 const driverFiles=['illustrator.jsx','photoshop.jsx','common.jsx','invoke.js','editorial-generator.jsx','vector-labels.jsx','editorial-parallel.jsx','editorial-bars.jsx'].map(f=>path.join(packageRoot,'adobe',f));driverFiles.push(path.join(packageRoot,'lib/svg.mjs'),path.join(packageRoot,'scripts/svg_page.py'),path.join(packageRoot,'lib/render.mjs'),path.join(packageRoot,'scripts/audit_pdf.py'),path.join(packageRoot,'scripts/ink_bounds.py'));if(p.route==='rebuild')driverFiles.push(generator);
 driverFiles.push(path.join(packageRoot,'lib/data-audit.mjs'),path.join(packageRoot,'lib/core.mjs'),path.join(packageRoot,'lib/color-policy.mjs'),path.join(packageRoot,'scripts/normalize_svg_color.py'),path.join(packageRoot,'scripts/audit_color.py'));
 const toolHashes=driverFiles.map(file=>({file,sha256:fileHash(file)})),planHash=colorPlanHash(p,toolHashes,colorPolicy);
 const rel='renders/'+figure.id+'/'+planHash.slice(0,16),directory=path.join(root,rel);mkdirSync(directory,{recursive:true});
 const cache=path.join(directory,'render.json');if(existsSync(cache)){const old=readJson(cache);if(old.ok&&existsSync(old.output)&&fileHash(old.output)===old.outputHash&&existsSync(old.ai)&&fileHash(old.ai)===old.aiHash&&existsSync(old.preview)&&fileHash(old.preview)===old.previewHash){try{assertColorAudit(old);return {cached:true,...old};}catch(invalidColorCache){}}}
 writeJson(path.join(directory,'plan.json'),p);updateFigure(root,figure.id,{status:'rendering',planHash});const start=Date.now();
 try{
  const input=path.join(directory,'input'+path.extname(source));copyFileSync(source,input);
  let reqInput=input,heightMm,psResult=null,colorNormalization={ok:true,kind:'generated-editorial-gray',geometryPreserved:null};
  const inputExt=path.extname(input).toLowerCase(),normalizer=path.join(packageRoot,'scripts/normalize_svg_color.py');
  if(!['rebuild','chart-redraw'].includes(p.route)){
   const kind=inputExt==='.svg'?'svg':p.route==='vector-reletter'?'pdf':'image',extension=kind==='svg'?'.svg':kind==='pdf'?'.pdf':'.png';
   reqInput=path.join(directory,'normalized-color'+extension);
   colorNormalization=JSON.parse(execFileSync(pythonRuntime(),[normalizer,input,reqInput,'--policy',colorPolicy.mode,'--kind',kind],{encoding:'utf8',windowsHide:true,timeout:60000,env:{...process.env,PYTHONIOENCODING:'utf-8'}}));
  }
  writeJson(path.join(directory,'color-normalization.json'),colorNormalization);
  if(p.nativeSvg&&path.extname(input).toLowerCase()!=='.svg')throw Error('nativeSvg requires an SVG source');
  if(p.route==='vector-reletter'&&path.extname(input).toLowerCase()==='.svg'&&!p.nativeSvg)reqInput=convertSvg(root,reqInput).outputs[0].path;
  if(p.route!=='rebuild'&&p.route!=='vector-reletter'&&p.route!=='chart-redraw'){
   const normalizedInput=reqInput;reqInput=path.join(directory,'prepared.png');psResult=adobe('photoshop',{input:normalizedInput,output:reqInput,format:'png',grayscale:false,rgbForIllustrator:true},path.join(directory,'prepare'));
   const c=p.crop||figure.crop||[0,0,0,0];p.crop=c;heightMm=p.widthMm*(psResult.heightPx*(1-c[1]-c[3]))/(psResult.widthPx*(1-c[0]-c[2]));
  }else heightMm=p.heightMm||100;
  if(p.route==='rebuild'){
   const skill=process.env.JFW_FLOWCHART_ROOT||path.join(packageRoot,'flowchart');const graph=path.join(directory,'graph.json');writeJson(graph,p.graph);
   execFileSync(process.execPath,[path.join(skill,'scripts/validate_flowchart.js'),graph],{encoding:'utf8',windowsHide:true});
  }
  const ai=path.join(directory,'figure.ai'),pdf=path.join(directory,'figure.pdf'),preview=path.join(directory,'preview.png');
  let result=adobe('illustrator',{mode:'render',input:reqInput,plan:p,heightMm,ai,pdf,preview,generator:path.join(process.env.JFW_FLOWCHART_ROOT||path.join(packageRoot,'flowchart'),'assets/AI流程图生成器.jsx')},path.join(directory,'draw'));
  if(['raster-reletter','compose','vector-reletter','chart-redraw'].includes(p.route)&&p.tightExport!==false){
   const measured=JSON.parse(execFileSync(pythonRuntime(),[path.join(packageRoot,'scripts/ink_bounds.py'),preview],{encoding:'utf8',windowsHide:true,timeout:30000}));
   const [l,t,r,b]=result.snapshot.artboard,[x0,y0,x1,y1]=measured.pixels,[pw,ph]=measured.size,dx=(r-l)/pw,dy=(t-b)/ph,pad=exportPadding(p.exportPaddingPt);
   const bounds=[l+x0*dx-pad[0],t-y0*dy+pad[1],l+x1*dx+pad[2],t-y1*dy-pad[3]];
   for(const text of result.snapshot.texts||[]){if(!text.inkBounds)continue;const ink=Array.isArray(text.inkBounds)?text.inkBounds:text.inkBounds.split(/\s+/).map(Number);bounds[0]=Math.min(bounds[0],ink[0]-pad[0]);bounds[1]=Math.max(bounds[1],ink[1]+pad[1]);bounds[2]=Math.max(bounds[2],ink[2]+pad[2]);bounds[3]=Math.min(bounds[3],ink[3]-pad[3]);}
   const previousIssues=result.mechanicalIssues||[],preservedGeometry=result.pathGeometryPreserved;result=adobe('illustrator',{mode:'trim',input:ai,bounds,ai,pdf,preview},path.join(directory,'trim'));result.mechanicalIssues=previousIssues.concat(result.mechanicalIssues||[]);result.pathGeometryPreserved=preservedGeometry;result.exportTrim={before:[l,t,r,b],after:bounds,paddingPt:p.exportPaddingPt===undefined?0.25:p.exportPaddingPt};
  }
  if(p.diagramKind){result.diagramAudit=auditDiagram(result.snapshot);if(!result.diagramAudit.ok)throw Error('Diagram geometry audit failed: '+JSON.stringify(result.diagramAudit.issues));}
  const pdfPreview=path.join(directory,'pdf-preview.png');let pdfAudit;try{pdfAudit=JSON.parse(execFileSync(pythonRuntime(),[path.join(packageRoot,'scripts/audit_pdf.py'),pdf,preview,pdfPreview],{encoding:'utf8',windowsHide:true,timeout:60000,env:{...process.env,PYTHONIOENCODING:'utf-8'}}));}catch(error){throw Error('PDF visual audit failed: '+String(error.stdout||error.message));}
  let output=pdf;
  if(p.route==='image'){
   output=path.join(directory,'figure.jpg');const action=p.action||({80:'单栏',40:'半单栏',25:'三分单栏',160:'双栏',60:'小小'})[p.widthMm];if(!action)throw Error('No verified Photoshop action for width');
   psResult=adobe('photoshop',{input:preview,output,format:'jpg',action,grayscale:false},path.join(directory,'export-jpg'));
   if(psResult.heightPx<10||Math.abs(psResult.widthMm-p.widthMm)>0.15||Math.abs(psResult.heightMm/psResult.widthMm-heightMm/p.widthMm)>0.02)throw Error('JPG dimensions or crop aspect do not match plan');
  }
  for(const file of [ai,output,preview])if(!existsSync(file))throw Error('Expected output missing: '+file);
  const planRecordFile=path.join(directory,'plan.json');
  const record={ok:true,figureId:figure.id,source,sourceHash:figure.sourceHash,planFile:planRecordFile,planFileHash:fileHash(planRecordFile),planHash,toolHashes,colorPolicy,colorNormalization,colorNormalizationFile:path.join(directory,'color-normalization.json'),colorNormalizationHash:fileHash(path.join(directory,'color-normalization.json')),pdf,pdfHash:fileHash(pdf),output,outputHash:fileHash(output),ai,aiHash:fileHash(ai),preview,previewHash:fileHash(preview),durationMs:Date.now()-start,adobe:result,photoshop:psResult,pdfAudit,pdfPreview};
  const bindings={sourceHash:record.sourceHash,planHash,planFileHash:record.planFileHash,pdfHash:record.pdfHash,outputHash:record.outputHash,aiHash:record.aiHash,previewHash:record.previewHash,toolFingerprint:sha256(toolHashes.map(x=>x.sha256).join(''))},colorRequest=path.join(directory,'color-audit-request.json'),colorReport=path.join(directory,'color-audit.json');
  writeJson(colorRequest,{ruleVersion:COLOR_RULE_VERSION,policy:colorPolicy.mode,approval:colorPolicy.approval,bindings,source,planFile:planRecordFile,pdf,output,ai,preview,report:colorReport});
  try{execFileSync(pythonRuntime(),[path.join(packageRoot,'scripts/audit_color.py'),colorRequest],{encoding:'utf8',windowsHide:true,timeout:60000,env:{...process.env,PYTHONIOENCODING:'utf-8'}});}catch(error){throw Error('Final color audit failed: '+String(error.stdout||error.message));}
  record.colorAudit={...readJson(colorReport),auditFile:colorReport,auditHash:fileHash(colorReport)};assertColorAudit(record);
  writeJson(cache,record);updateFigure(root,figure.id,{status:'needs_review',render:rel+'/render.json',planHash});logEvent(root,{event:'rendered',id:figure.id,planHash,durationMs:record.durationMs});return record;
 }catch(error){updateFigure(root,figure.id,{status:'failed',error:error.message,planHash});logEvent(root,{event:'render_failed',id:figure.id,error:error.message});throw error;}
}
export function inspect(root,id){const state=readJson(path.join(root,'job.json')),f=state.figures.find(x=>x.id===id);if(!f)throw Error('Unknown figure');const source=resolveInside(root,f.source),dir=path.resolve(root,'inspect',id);mkdirSync(dir,{recursive:true});const input=path.join(dir,'input'+path.extname(source));copyFileSync(source,input);const prepared=path.extname(input).toLowerCase()==='.svg'?convertSvg(root,input).outputs[0].path:input;return adobe('illustrator',{mode:'inspect',input:prepared},dir);}
