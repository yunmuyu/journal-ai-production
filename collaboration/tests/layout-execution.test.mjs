import {tmpdir} from 'node:os';import path from 'node:path';import {createHash} from 'node:crypto';
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
import {solveLayout} from '../scripts/constraint-layout.mjs';import {buildMoveRequest} from '../scripts/layout-execution.mjs';
const sourceFile=path.join(fs.mkdtempSync(path.join(tmpdir(),'solver-source-test-')),'example.ai');fs.writeFileSync(sourceFile,'synthetic source identity fixture');const sourceHash=createHash('sha256').update(fs.readFileSync(sourceFile)).digest('hex');
const scene=()=>({version:1,units:'pt',canvas:{widthPt:200,heightPt:100},elements:[{id:'label',kind:'text',x:10,y:10,widthPt:30,heightPt:10,fontSizePt:8,candidates:[{x:80,y:30}]}],sourceBinding:{sourcePath:sourceFile,sourceSha256:sourceHash,canvasOrigin:[0,100],items:[{id:'label',name:'label',text:'label',fontName:'TimesNewRomanPSMT',fontSizePt:8,bounds:[10,90,40,80]}]}});
const code=fs.readFileSync(new URL('../adobe/solved-layout.jsx',import.meta.url),'utf8');
function native(item){let moves=0;const obj={name:'label',contents:'label',textRange:{characterAttributes:{textFont:{name:'TimesNewRomanPSMT'},size:8}},geometricBounds:item.bounds.slice(),parent:null,translate(dx,dy){moves++;this.geometricBounds=this.geometricBounds.map((v,i)=>v+(i%2?dy:dx));}};const doc={fullName:{fsName:sourceFile},pageItems:[obj],activeLayer:{}};obj.parent=doc;const context={JFW:{},RGBColor:function(){}};vm.runInNewContext(code,context);return {doc,obj,context,moves:()=>moves};}
test('bound solution produces final displacement and applies it exactly once',()=>{
 const input=scene(),solution=solveLayout(input),request=buildMoveRequest(input,solution),n=native(request.items[0]);
 const r=n.context.JFW.applySolvedMoves(n.doc,request);assert.equal(n.moves(),1);assert.equal(r.iterations,1);assert.deepEqual(n.obj.geometricBounds,[80,70,110,60]);
});
test('source bounds or content changes abort before any move',()=>{
 const input=scene(),request=buildMoveRequest(input,solveLayout(input));for(const field of ['bounds','text']){
  const n=native(request.items[0]);if(field==='bounds')n.obj.geometricBounds[0]++;else n.obj.contents='different';assert.throws(()=>n.context.JFW.applySolvedMoves(n.doc,request),/changed/);assert.equal(n.moves(),0);
 }
});
test('unbound or stale solution cannot create an execution request',()=>{
 const input=scene(),sol=solveLayout(input);input.canvas.widthPt++;assert.throws(()=>buildMoveRequest(input,sol),/exact input/);
 const next=scene();next.sourceBinding.items=[];assert.throws(()=>buildMoveRequest(next,solveLayout(next)),/Missing source/);
});

test('native adapter moves once and saves separate AI/PDF without replacing source',()=>{
 const input=scene(),request=buildMoveRequest(input,solveLayout(input)),n=native(request.items[0]),saved=[];
 n.context.File=function(name){this.fsName=name;this.exists=false;};n.context.IllustratorSaveOptions=function(){};n.context.PDFSaveOptions=function(){};n.doc.saveAs=(file)=>saved.push(file.fsName);
 const r=n.context.JFW.executeSolvedExport(n.doc,{...request,outputAI:'result.ai',outputPDF:'result.pdf'});assert.equal(r.iterations,1);assert.equal(n.moves(),1);assert.deepEqual(saved,['result.ai','result.pdf']);
 const other=native(request.items[0]);other.context.File=function(name){this.fsName=name;this.exists=name==='existing.ai';};assert.throws(()=>other.context.JFW.executeSolvedExport(other.doc,{...request,outputAI:'existing.ai',outputPDF:'result.pdf'}),/replace/);assert.equal(other.moves(),0);
});

test('new solved drawing uses fixed coordinates and verifies final text ink once',()=>{
 const context={JFW:{editorialFont:()=>({name:'editorial'}),drawArrow5:()=>{}},RGBColor:function(){}};vm.runInNewContext(code,context);
 let textMoves=0,rectangles=0;const doc={textFrames:{add(){return {textRange:{characterAttributes:{}},duplicate(){return{createOutline(){return{visibleBounds:[0,0,30,-10],remove(){}};}};},translate(dx,dy){textMoves++;this.delta=[dx,dy];}};}},pathItems:{rectangle(){rectangles++;return{};}},artboards:[{}]};
 const request={kind:'draw',font:'现 宋体 1',fontSizePt:8,canvas:{widthPt:100,heightPt:80},texts:[{id:'t',text:'x',x:10,y:20,expectedInk:{widthPt:30,heightPt:10}}],shapes:[{id:'box',shape:'rectangle',x:5,y:15,widthPt:40,heightPt:20}],connections:[]};
 const r=context.JFW.drawSolvedLayout(doc,request);assert.equal(r.iterations,1);assert.equal(textMoves,1);assert.equal(rectangles,1);
 request.texts[0].expectedInk.widthPt=40;assert.throws(()=>context.JFW.drawSolvedLayout(doc,request),/measurement changed/);
});

test('anonymous text frames can bind by stable collection index and count',()=>{
 const input=scene();delete input.sourceBinding.items[0].name;Object.assign(input.sourceBinding.items[0],{collection:'textFrames',index:0});input.sourceBinding.collectionCounts={textFrames:1};
 const request=buildMoveRequest(input,solveLayout(input)),n=native(request.items[0]);n.obj.name='';n.doc.textFrames=[n.obj];const r=n.context.JFW.applySolvedMoves(n.doc,request);assert.equal(r.ok,true);assert.equal(n.moves(),1);
 const other=native(request.items[0]);other.doc.textFrames=[other.obj,{}];assert.throws(()=>other.context.JFW.applySolvedMoves(other.doc,request),/collection count/);assert.equal(other.moves(),0);
});

test('native host verifies source fingerprint before opening any Adobe session',async()=>{
 const {validateSolvedRequest}=await import('../../production-runtime/lib/adobe.mjs');
 const request={mode:'solved-layout',execution:{kind:'move',sourcePath:sourceFile,sourceSha256:sourceHash}};
 assert.equal(validateSolvedRequest(request).execution.verifiedSourceSha256,sourceHash);
 assert.throws(()=>validateSolvedRequest({...request,execution:{...request.execution,sourceSha256:'0'.repeat(64)}}),/before Adobe/);
});

test('execution binding cannot hide an oversized source font behind valid scene metadata',()=>{
 const input=scene();input.sourceBinding.items[0].fontSizePt=17;assert.throws(()=>buildMoveRequest(input,solveLayout(input)),/Source font/);
});
