import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {prepareOfficeSource} from './office-source-preparation.mjs';
import {runProductionRequests} from './production-intake.mjs';
import {buildPptxPlan} from '../lib/pptx-plan.mjs';

const sha=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');

test('source-bound PPTX preparation removes approved shadows and sets measured stroke while preserving geometry',
 {skip:!process.env.JFW_TEST_PPTX_SOURCE||!process.env.WORKSPACE_TEST_PYTHON},async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'pptx-preparation-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const original=process.env.JFW_TEST_PPTX_SOURCE,python=process.env.WORKSPACE_TEST_PYTHON,source={path:original,sha256:sha(original)};
 const scan=`import zipfile,sys,json,xml.etree.ElementTree as E\nn={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}\nr=E.fromstring(zipfile.ZipFile(sys.argv[1]).read('ppt/slides/slide1.xml'))\nshapes=[];lines=[];green=[]\nfor s in r.findall('.//p:sp',n)+r.findall('.//p:cxnSp',n):\n v=s.find('./p:nvSpPr/p:cNvPr',n)\n if v is None:v=s.find('./p:nvCxnSpPr/p:cNvPr',n)\n if v is None:continue\n i=int(v.get('id'));shapes.append(i)\n if s.tag.endswith('cxnSp'):\n  lines.append(i)\n  c=s.find('./p:spPr/a:ln/a:solidFill/a:srgbClr',n)\n  if c is not None and c.get('val')=='2CA02C':green.append(i)\nprint(json.dumps({'shapes':shapes,'lines':lines,'green':green}))`;
 const ids=JSON.parse(execFileSync(python,['-c',scan,original],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
 assert.equal(ids.green.length,6);assert.ok(ids.shapes.length>80);
 const plan={version:1,sourceSha256:source.sha256,slide:1,shadowShapeIds:ids.shapes,
  stroke:{shapeIds:ids.lines,sourcePlotWidthPt:733.5,targetPlotWidthPt:160,finalStrokePt:.5},
  dashedSeries:[{curveShapeIds:ids.green.slice(0,5),legendShapeIds:ids.green.slice(5)}],
  evidence:'已核对阴影为装饰，虚线系列及图例属于同一源曲线'};
 const first=await prepareOfficeSource({source,workbenchRoot:root,python,pptxPlan:plan,grayscale:true});
 assert.equal(first.status,'prepared-intermediate');assert.equal(first.geometry.unchanged,true);
 assert.equal(first.geometry.shapeCount,ids.shapes.length);assert.equal(sha(original),source.sha256);
 assert.ok(first.outputs[0].path.endsWith('.pdf'));
 const report=JSON.parse(execFileSync(python,['-c',`import fitz,sys,json\nd=fitz.open(sys.argv[1]);p=d[0];print(json.dumps({'images':len(p.get_image_info()),'paths':len(p.get_drawings()),'grays':all(max(c)-min(c)<.01 for x in p.get_drawings() for c in (x.get('color'),x.get('fill')) if c)}))`,first.outputs[0].path],{encoding:'utf8'}));
 assert.equal(report.images,0);assert.equal(report.grays,true);assert.ok(report.paths>=60);
 const second=await prepareOfficeSource({source,workbenchRoot:root,python,pptxPlan:plan,grayscale:true});
 assert.equal(second.outputs[0].sha256,first.outputs[0].sha256);
 const decision={sourceSha256:source.sha256,slide:1,plotRectPt:[160.5,133,894,499.5],legendRectPt:[160,95,700,125],
  targetPlotWidthPt:160,confirmedDecorativeShadows:true,confirmedSeries:true,autoDistinguish:true,
  seriesLabels:{'1F77B4':'CMA预报特征组','D62728':'本地实测特征组','2CA02C':'虾塘水温特征组'},evidence:'已核对源图例和三个连续系列'};
 const automatic=await prepareOfficeSource({source,workbenchRoot:root,python,pptxDecision:decision,grayscale:true});
 assert.equal(automatic.geometry.unchanged,true);
 assert.equal(automatic.objectCandidates.series.length,3);
 assert.equal(automatic.objectCandidates.unresolved.length,0);
 assert.deepEqual(automatic.appliedPlan.dashedSeries,[{curveShapeIds:ids.green.slice(0,5),legendShapeIds:ids.green.slice(5)}]);
 assert.ok(automatic.appliedPlan.stroke.shapeIds.length>35);
 const prior=globalThis.fetch;globalThis.fetch=async()=>({ok:true,json:async()=>({rows:[{id:'F1',articleId:'A',number:'1',type:'统计图表',outputs:[]}],articles:[]})});
 try{
  let discovered;
  const result=await runProductionRequests({origin:'http://fixture',python,workbenchRoot:root},
   {requestedAt:new Date().toISOString(),requests:[{figureId:'F1',source,pptxPlan:plan,grayscale:true}]},
   {executeChartRequest:async(_config,request)=>{discovered=request.source;return {status:'needs_bindings',reason:'需要绑定坐标和系列'};}});
  assert.equal(discovered.sha256,first.outputs[0].sha256);
  assert.equal(result.admission.held[0].sourcePreparation.source.sha256,source.sha256);
  assert.equal(result.returnedOutputs,0);
 }finally{globalThis.fetch=prior;}
 const partial=structuredClone(plan);partial.dashedSeries[0].curveShapeIds.shift();
 await assert.rejects(prepareOfficeSource({source,workbenchRoot:root,python,pptxPlan:partial,grayscale:true}),/pptx_plan_series_incomplete/);
});

test('three indistinguishable same-marker series are blocked when two styles cannot distinguish them',()=>{
 const source={path:'chart.pptx',sha256:'a'.repeat(64)};
 const rows=[0,1,2].map((n)=>({color:['111111','222222','333333'][n],gray:n*10,marker:'triangle',dash:'solid',pointCount:2,curveShapeIds:[n+1],legendShapeIds:[n+4]}));
 const proposal={version:1,sourceSha256:source.sha256,slide:1,series:rows,unresolved:[],shadowCandidates:[],strokeShapeIds:[1,2,3,4,5,6],sourcePlotWidthPt:100};
 const decision={sourceSha256:source.sha256,slide:1,evidence:'confirmed',confirmedDecorativeShadows:false,confirmedSeries:true,autoDistinguish:true,targetPlotWidthPt:80,seriesLabels:{'111111':'A','222222':'B','333333':'C'}};
 assert.throws(()=>buildPptxPlan(proposal,decision,source),/pptx_series_more_styles_required/);
});

test('PPTX preparation rejects unbound or incomplete style decisions before Office',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'pptx-preflight-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const p=path.join(root,'source.pptx');fs.writeFileSync(p,'fixture');
 await assert.rejects(prepareOfficeSource({source:{path:p,sha256:sha(p)},workbenchRoot:root,python:'python',
  pptxPlan:{version:1,sourceSha256:'wrong',slide:1,shadowShapeIds:[1],evidence:'known'}}),/pptx_plan_source/);
});
