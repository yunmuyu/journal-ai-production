import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync} from 'node:fs';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {test} from 'node:test';
import vm from 'node:vm';
import {fileHash} from '../lib/core.mjs';
import {buildTrimGeometryReuse} from '../lib/trim-geometry-reuse.mjs';
function fixture(){
 const dir=mkdtempSync(path.join(tmpdir(),'jfw-trim-reuse-'));const ai=path.join(dir,'controlled.ai'),drawResultFile=path.join(dir,'draw-result.json');
 const paths=[{name:'curve',guides:false,hidden:false,opacity:100,strokeWidthPt:.5,closed:false,clipping:false,filled:false,stroked:true,fillType:null,fillGray:null,points:[[[1.1234567890123,2,3,4],[5,6]]]}];
 const result={ok:true,pathGeometryPreserved:true,mechanicalIssues:[],snapshot:{pathGeometry:paths}};
 const tool=path.join(dir,'tool.jsx');writeFileSync(tool,'controlled driver');writeFileSync(ai,'controlled AI bytes');writeFileSync(drawResultFile,JSON.stringify(result));
 return {plan:{route:'vector-reletter',trimGeometryReuseExperiment:true},result,ai,drawResultFile,expectedSavedAiHash:fileHash(ai),expectedDrawResultHash:fileHash(drawResultFile),expectedToolHashes:[{file:tool,sha256:fileHash(tool)}]};
}
test('legacy and opt-out do not access files or change path protection',()=>{
 assert.equal(buildTrimGeometryReuse({plan:{}}),null);assert.equal(buildTrimGeometryReuse({plan:{trimGeometryReuseExperiment:false}}),null);
});
test('opt-in reuses all plain control points and explicit hash provenance',()=>{
 const input=fixture(),evidence=buildTrimGeometryReuse(input);assert.equal(evidence.kind,'controlled-trim-v1');
 assert.deepEqual(evidence.pathGeometry,input.result.snapshot.pathGeometry);assert.notEqual(evidence.pathGeometry,input.result.snapshot.pathGeometry);
 assert.equal(evidence.savedAiHash,input.expectedSavedAiHash);assert.equal(evidence.drawResultHash,input.expectedDrawResultHash);assert.equal(evidence.operation,'artboard-only');
});
test('changed AI or draw evidence rejects before Adobe',()=>{
 const input=fixture();writeFileSync(input.ai,'user change');assert.throws(()=>buildTrimGeometryReuse(input),/AI changed/);
 const next=fixture();writeFileSync(next.drawResultFile,'changed');assert.throws(()=>buildTrimGeometryReuse(next),/evidence changed/);
});
test('missing hashes, unprotected route, failed geometry or issues reject',()=>{
 for(const mutate of [i=>delete i.expectedSavedAiHash,i=>delete i.expectedDrawResultHash,i=>i.plan.route='compose',i=>i.result.pathGeometryPreserved=false,i=>i.result.mechanicalIssues=[{type:'text_overlap'}]]){
  const i=fixture();mutate(i);assert.throws(()=>buildTrimGeometryReuse(i));
 }
});
test('saved geometry mismatch and failed close cannot qualify',()=>{
 const i=fixture();i.result.snapshot.pathGeometry[0].points[0][0][0]=99;assert.throws(()=>buildTrimGeometryReuse(i),/evidence differs/);
 const next=fixture();const saved={...next.result,closeError:'busy'};writeFileSync(next.drawResultFile,JSON.stringify(saved));next.expectedDrawResultHash=fileHash(next.drawResultFile);assert.throws(()=>buildTrimGeometryReuse(next),/close cleanly/);
});
const source=readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');
const fn=source.slice(source.indexOf('function snapshot('),source.indexOf('function geometryPreserved'));
function doc(){
 const font={name:'TimesNewRomanPSMT',family:'Times New Roman'},d={pageItems:[],textFrames:[{contents:'actual current text',note:'',name:'title',textRange:{characterAttributes:{textFont:font,size:8}},geometricBounds:[1,2,3,4]}],artboards:[{artboardRect:[-10,20,30,-40]}]};
 return d;
}
test('reuse reads actual current text and artboard but does not touch pathItems',()=>{
 const d=doc();Object.defineProperty(d,'pathItems',{get(){throw Error('DOM geometry should not be read');}});const reused=fixture().result.snapshot.pathGeometry;
 const snapshot=vm.runInNewContext(fn+';snapshot(d,reused)',{d,reused,JFW:{bounds:v=>Array.from(v,Number)}});
 assert.equal(snapshot.texts[0].text,'actual current text');assert.equal(snapshot.texts[0].size,8);assert.deepEqual(Array.from(snapshot.artboard),[-10,20,30,-40]);assert.equal(snapshot.pathGeometry,reused);
});
test('legacy still requires a full actual DOM path scan',()=>{
 const d=doc();Object.defineProperty(d,'pathItems',{get(){throw Error('full actual path scan');}});
 assert.throws(()=>vm.runInNewContext(fn+';snapshot(d)',{d,JFW:{bounds:v=>Array.from(v,Number)}}),/full actual path scan/);
});
test('original before/after geometry check and actual PDF audit remain present',()=>{
 assert.ok(source.includes('if(before&&!geometryPreserved(before.pathGeometry,after.protectedPathGeometry'));
 assert.ok(source.includes("origin:'draw before/after geometryPreserved; paths not re-read in trim'"));
 const render=readFileSync(new URL('../lib/render.mjs',import.meta.url),'utf8');assert.ok(render.includes("scripts/audit_pdf.py"));assert.ok(render.includes('expectedSavedAiHash:drawSavedAiHash'));
 const adobe=readFileSync(new URL('../lib/adobe.mjs',import.meta.url),'utf8');assert.ok(adobe.includes('fileHash(request.input)!==request.preflightInputHash'));
});
import {buildTrimGeometryReuse as buildSource,assertTrimGeometryReuseRequest as assertSource} from '../lib/trim-geometry-reuse.mjs';
import {buildTrimGeometryReuse as buildRuntime,assertTrimGeometryReuseRequest as assertRuntime} from '../production-runtime/lib/trim-geometry-reuse.mjs';
for(const [name,build,check] of [['source',buildSource,assertSource],['runtime',buildRuntime,assertRuntime]]){
 test(name+': tool fingerprint and invocation reject mutations',()=>{
  const input=fixture(),reuse=build(input),request={mode:'trim',input:input.ai,preflightInputHash:reuse.savedAiHash,geometryReuse:reuse};check(request);
  writeFileSync(input.expectedToolHashes[0].file,'different tool');assert.throws(()=>check(request),/tools changed/);assert.throws(()=>build(input),/tools changed/);
  const aiInput=fixture(),aiReuse=build(aiInput),aiReq={mode:'trim',input:aiInput.ai,preflightInputHash:aiReuse.savedAiHash,geometryReuse:aiReuse};writeFileSync(aiInput.ai,'changed AI');assert.throws(()=>check(aiReq),/input changed/);
  const evidence=fixture(),ev=build(evidence),evReq={mode:'trim',input:evidence.ai,preflightInputHash:ev.savedAiHash,geometryReuse:ev};writeFileSync(evidence.drawResultFile,'changed evidence');assert.throws(()=>check(evReq),/draw evidence changed/);
  const geometry=fixture(),geo=build(geometry);geo.pathGeometry[0].points[0][1][0]++;assert.throws(()=>check({mode:'trim',input:geometry.ai,preflightInputHash:geo.savedAiHash,geometryReuse:geo}),/geometry evidence changed/);
  assert.doesNotThrow(()=>check({mode:'trim'}));
 });
 test(name+': reused trim reads current native font and artboard; legacy rereads geometry',()=>{
  const src=readFileSync(new URL('../'+(name==='runtime'?'production-runtime/':'')+'adobe/illustrator.jsx',import.meta.url),'utf8'),body=src.slice(src.indexOf('function snapshot('),src.indexOf('function geometryPreserved'));
  const d=doc();Object.defineProperty(d,'pathItems',{get(){throw Error('full native geometry');}});const reused=fixture().result.snapshot.pathGeometry;
  const snapshot=vm.runInNewContext(body+';snapshot(d,reused)',{d,reused,JFW:{bounds:v=>Array.from(v,Number)}});assert.equal(snapshot.texts[0].font,'TimesNewRomanPSMT');assert.equal(snapshot.texts[0].size,8);assert.deepEqual(Array.from(snapshot.artboard),[-10,20,30,-40]);assert.equal(snapshot.pathGeometry,reused);
  assert.throws(()=>vm.runInNewContext(body+';snapshot(d)',{d,JFW:{bounds:v=>Array.from(v,Number)}}),/full native geometry/);
 });
}
