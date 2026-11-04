import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyChartRoutes} from './chart-route-discovery.mjs';

test('native PDF chart enumerates all public routes and exposes missing bindings',()=>{
 const result=classifyChartRoutes({pageCount:1,textSpans:22,vectorPaths:47,images:0},{hasPlan:false});
 assert.equal(result.status,'needs_bindings');
 assert.deepEqual(result.routes.map(r=>r.id),['source-vector-reletter','chart-layout','chart-panels']);
 assert.ok(result.routes.every(r=>r.missing.length>0));
});

test('unsupported is reserved for proved missing usable PDF objects',()=>{
 assert.equal(classifyChartRoutes({pageCount:1,textSpans:0,vectorPaths:0,images:0},{hasPlan:false}).status,'needs_bindings');
 assert.equal(classifyChartRoutes({pageCount:1,textSpans:0,vectorPaths:0,images:0,unsupportedVerified:true},{hasPlan:false}).status,'unsupported');
 assert.equal(classifyChartRoutes({pageCount:1,textSpans:0,vectorPaths:0,images:1},{hasPlan:false}).status,'needs_bindings');
 assert.equal(classifyChartRoutes({pageCount:1,textSpans:3,vectorPaths:4,images:0},{hasPlan:true}).status,'ready');
});

test('existing workbench candidate is returned before source inspection',async()=>{
 const {discoverPdfChart}=await import('./chart-route-discovery.mjs');
 const figure={id:'figure-2',outputs:[{number:'2',file:{meta:{sha256:'abc'}}}]};
 const result=await discoverPdfChart({figure,source:null,python:'missing'});
 assert.equal(result.status,'existing_candidate');assert.equal(result.outputs[0].number,'2');
});

test('confirmed plan is reused only while source, manuscript and spec remain byte-identical',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const {discoverPdfChart}=await import('./chart-route-discovery.mjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'chart-route-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const ref=name=>{const p=path.join(root,name);fs.writeFileSync(p,name);return {path:p,sha256:crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')}};
 const source=ref('figure.pdf'),word=ref('manuscript.docx'),archive=ref('archive.zip');
 const jsonRef=(name,value)=>{const p=path.join(root,name);fs.writeFileSync(p,JSON.stringify(value));return {path:p,sha256:crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')}};
 const spec=jsonRef('spec.json',{kind:'chart'}),history=jsonRef('history.json',{checked:true,conclusion:'new',reusable:false,observation:'source verified'});
 const figure={id:'f',articleId:'a',number:'2.2',reviewVersion:'v',outputs:[]};
 const plan={figureId:'f',baseVersion:'v',articleEvidence:'bound',allowedChanges:['text'],immutableContent:['curves'],history:{evidence:history,conclusion:'new',reusable:false},outputRoutes:[{number:'2.2',productionRoute:{processing:{basis:'reviewed'},requirements:{widthMm:80},sourceReview:{selected:source,word,archive}}}],render:[{number:'2.2',spec}]};
 const inspect=async()=>({pageCount:1,textSpans:3,vectorPaths:4,images:0});
 const invoke=()=>discoverPdfChart({figure,article:{id:'a',word,archiveHash:archive.sha256},source,python:'unused',plan,engineSignature:'engine-v1',inspect});
 const first=await invoke();assert.equal(first.status,'ready');assert.equal(first.planBinding.engineSignature,'engine-v1');
 const {saveBoundChartPlan,loadBoundChartPlan}=await import('./chart-route-discovery.mjs');
 const registry=path.join(root,'plans');saveBoundChartPlan(registry,{figure,source,discovery:first,plan});
 assert.equal(loadBoundChartPlan(registry,{figure,source,engineSignature:'engine-v1',requirements:[{widthMm:80}]}).figureId,'f');
 assert.equal(loadBoundChartPlan(registry,{figure,source,engineSignature:'engine-v2',requirements:[{widthMm:80}]}),null);
 assert.equal(loadBoundChartPlan(registry,{figure,source,engineSignature:'engine-v1',requirements:[{widthMm:160}]}),null);
 fs.writeFileSync(word.path,'changed');assert.equal((await invoke()).status,'needs_bindings');
 fs.writeFileSync(source.path,'changed');await assert.rejects(invoke,/source_changed/);
});

test('expired chart request is recorded without dispatch',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path');
 const {runChartRequest}=await import('./production-runner.mjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'chart-deadline-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const result=await runChartRequest({workbenchRoot:root},{figureId:'figure-2',requestedAt:new Date(Date.now()-181000).toISOString()});
 assert.equal(result.status,'deadline_exceeded');assert.equal(result.stage,'preflight');
 assert.equal(JSON.parse(fs.readFileSync(result.recordPath,'utf8')).status,'deadline_exceeded');
});

test('known source and binding failure blocks the identical attempt but permits a changed binding',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const {discoverPdfChart}=await import('./chart-route-discovery.mjs');const {sourceBindingFingerprint}=await import('./figure-case-index.mjs');const root=fs.mkdtempSync(path.join(os.tmpdir(),'case-guard-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
 const ref=(name,body)=>{let p=path.join(root,name);fs.writeFileSync(p,body);return {path:p,sha256:digest(fs.readFileSync(p))}};
 const source=ref('source.pdf','pdf'),word=ref('word.docx','word'),archive=ref('archive.zip','zip'),history=ref('history.json',JSON.stringify({checked:true,conclusion:'new',reusable:false,observation:'checked'}));
 let binding=[{source_text:'x',source_bbox:[1,2,3,4],target_text_id:'x'}];
 const makeSpec=b=>ref('spec.json',JSON.stringify({kind:'scene',chart_vector_layout:{body_id:'body'},assets:[{source_vector_body:true,path:source.path,page:0,clip:[0,0,10,10],text_replacements:b}]}));
 let spec=makeSpec(binding),evidence=ref('fail.json','failure');
 const cases=path.join(root,'cases.json');fs.writeFileSync(cases,JSON.stringify({version:1,cases:[{id:'old-failure',outcome:'failure',features:{kind:'chart',format:'pdf'},entry:'source-vector',evidence,guard:{sourceSha256:source.sha256,engineSignature:'v',operation:'source-vector-reletter',bindingSha256:sourceBindingFingerprint({page:0,clip:[0,0,10,10],text_replacements:binding})}}]}));
 const figure={id:'f',articleId:'a',number:'2',reviewVersion:'r',outputs:[]},article={id:'a',word,archiveHash:archive.sha256};
 const plan={figureId:'f',baseVersion:'r',articleEvidence:'checked',allowedChanges:['text'],immutableContent:['data'],history:{evidence:history,conclusion:'new',reusable:false},outputRoutes:[{number:'2',productionRoute:{processing:{basis:'checked'},requirements:{widthMm:80},sourceReview:{selected:source,word,archive}}}],render:[{number:'2',spec,sourceRoot:root}]};
 const invoke=()=>discoverPdfChart({figure,article,source,plan,engineSignature:'v',inspect:async()=>({pageCount:1,textSpans:1,vectorPaths:1,images:0}),caseIndexPath:cases});
 assert.equal((await invoke()).status,'blocked_known_failure');
 binding=[{...binding[0],target_text_id:'changed'}];spec=makeSpec(binding);plan.render[0].spec=spec;
 assert.equal((await invoke()).status,'blocked_known_failure');
 binding=[{...binding[0],source_bbox:[1,2,3,5]}];spec=makeSpec(binding);plan.render[0].spec=spec;
 assert.equal((await invoke()).status,'ready');
});

test('source discovery inspects SVG and bitmap without inventing native text for pixels',{skip:!process.env.WORKSPACE_TEST_PYTHON},async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const {discoverPdfChart}=await import('./chart-route-discovery.mjs');const root=fs.mkdtempSync(path.join(os.tmpdir(),'case-formats-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const put=(name,bytes)=>{let p=path.join(root,name);fs.writeFileSync(p,bytes);return {path:p,sha256:crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')}};
 const svg=put('source.svg','<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd"><svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"><g id="axes_1"><path d="M 0 0 L 20 20" stroke="#ff0000"/><text>温度</text></g><g id="legend_1"><text>曲线</text></g></svg>');
 const png=put('source.png',Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=','base64'));
 const figure={id:'f',type:'统计曲线图',outputs:[]},args={figure,python:process.env.WORKSPACE_TEST_PYTHON,engineSignature:'v',caseIndexPath:path.join(root,'missing.json')};
 const a=await discoverPdfChart({...args,source:svg});assert.equal(a.featureCandidates.format,'svg');assert.equal(a.facts.textSpans,2);assert.equal(a.facts.pages[0].panelCandidates.length,1);assert.equal(a.facts.pages[0].legendCandidates.length,1);
 const b=await discoverPdfChart({...args,source:png});assert.equal(b.featureCandidates.format,'png');assert.equal(b.facts.images,1);assert.equal(b.facts.textSpans,0);assert.equal(b.facts.pixelTextRecognition,'not_performed');
});
