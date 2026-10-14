import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {preflightPlan} from '../scripts/plan-preflight.mjs';
const root=fileURLToPath(new URL('../../production-runtime/flowchart/',import.meta.url));
const generator=path.join(root,'assets/AI流程图生成器.jsx');
test('packaged validator accepts new v3 shapes and rejects them in v2',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-shapes-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const graph={schemaVersion:3,kind:'flowchart',flowShapePolicy:'sourceVisible',fontSize:8,nodes:[{id:'input',shape:'inputOutput',text:'输入',row:0,column:0},{id:'process',shape:'predefinedProcess',text:'处理',row:1,column:0}],edges:[{from:'input',to:'process'}]};
 const file=path.join(dir,'graph.json');fs.writeFileSync(file,JSON.stringify(graph));
 const run=()=>spawnSync(process.execPath,[path.join(root,'scripts/validate_flowchart.js'),file],{encoding:'utf8'});
 let result=run();assert.equal(result.status,0,result.stderr+result.stdout);
 graph.schemaVersion=2;fs.writeFileSync(file,JSON.stringify(graph));assert.notEqual(run().status,0);
});
test('official preflight accepts bundled generator at supported font sizes',()=>{
 for(const fontSize of [6,7,8]){const result=preflightPlan({route:'rebuild',fontSize,widthMm:80,graph:{fontSize,widthClass:'single',nodes:[{id:'input'}]}},{generatorFile:generator});assert.equal(result.fontSizePt,fontSize);assert.ok(result.contentWidthMm>56);}
});
test('text moves by actual outlined ink center while retaining editable original',()=>{
 const source=fs.readFileSync(generator,'utf8');const start=source.indexOf('    function centerText('),end=source.indexOf('\n    function ',start+1);const ctx={};vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 let removed=0,translated;const tf={visibleBounds:[0,50,20,0],duplicate:()=>({createOutline:()=>({visibleBounds:[3,20,13,10],remove:()=>removed++})}),translate:(x,y)=>translated=[x,y]};
 ctx.centerText(tf,30,40);assert.deepEqual(translated,[22,25]);assert.equal(removed,1);assert.equal(typeof tf.translate,'function');
});
test('layout retains block-arrow direction and heads through native drawing',()=>{
 let source=fs.readFileSync(generator,'utf8').replace(/^#target[^\n]*\n/,'');
 source=source.replace('var sample = readSibling(', 'this.api={measureLayout:measureLayout,drawArrowSymbol:drawArrowSymbol}; measureText=function(){return {w:20,h:8};}; return; var sample = readSibling(');
 const ctx={app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};vm.createContext(ctx);vm.runInContext(source,ctx);
 for(const direction of ['left','right','up','down'])for(const heads of ['end','both']){
  const layout=ctx.api.measureLayout({nodes:[{id:'a',shape:'arrow',text:'链路',row:0,column:0,arrowDirection:direction,arrowHeads:heads}],edges:[]},8,{});
  const n=layout.nodes[0];assert.equal(n.arrowDirection,direction);assert.equal(n.arrowHeads,heads);
  Object.assign(n,{left:0,right:n.w,top:n.h,bottom:0});let points;const item={setEntirePath:p=>{points=p;}};ctx.api.drawArrowSymbol(n,{pathItems:{add:()=>item}},{},[]);
  assert.equal(points.length,heads==='both'?10:7);assert.equal(item.closed,true);
  const tips=points.filter(p=>direction==='left'||direction==='right'?p[1]===n.h/2:p[0]===n.w/2);
  assert.equal(tips.length,heads==='both'?2:1);
  if(heads==='end')assert.deepEqual(Array.from(tips[0]),direction==='left'?[0,n.h/2]:direction==='right'?[n.w,n.h/2]:direction==='up'?[n.w/2,n.h]:[n.w/2,0]);
 }
});
test('container title gets a measured band before frame and connector spacing',()=>{
 let source=fs.readFileSync(generator,'utf8').replace(/^#target[^\n]*\n/,'');source=source.replace('var sample = readSibling(', 'this.api={measureLayout:measureLayout,measureContainers:measureContainers,containerLabelPoint:containerLabelPoint}; measureText=function(t){return {w:t.length*4,h:16};}; measureContainerTitle=measureText; return; var sample = readSibling(');
 const ctx={app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};vm.createContext(ctx);vm.runInContext(source,ctx);
 for(const labelPosition of ['topCenter','bottomRight']){
  const spec={id:'frame',members:['n'],label:'A long container title',labelPosition,padding:'minimal'};
  const layout=ctx.api.measureLayout({nodes:[{id:'n',text:'node',shape:'process',row:1,column:0}],edges:[],containers:[spec]},8,{});
  Object.assign(layout.nodes[0],{left:0,right:25,top:0,bottom:-20});
  const frame=ctx.api.measureContainers([spec],layout.byId)[0],point=ctx.api.containerLabelPoint(frame);
  assert.ok(frame.right-frame.left>=spec.titleWidth+2*2.83464566929-0.001);
  if(labelPosition==='topCenter'){assert.ok(point[1]-8>=3);assert.ok(layout.rowGaps[0]>=22);}else assert.ok(point[1]+8<=-23);
 }
});
test('entry title follows the vertical connector with 3pt ink clearance, independent of outer width',()=>{
 let source=fs.readFileSync(generator,'utf8').replace(/^#target[^\n]*\n/,'');source=source.replace('var sample = readSibling(', 'this.api={measureContainers:measureContainers,containerLabelPoint:containerLabelPoint}; return; var sample = readSibling(');
 const ctx={app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};vm.createContext(ctx);vm.runInContext(source,ctx);
 for(const right of [80,200]){
  const byId={start:{shape:'process',row:0,column:0,cx:20,cy:50,left:10,right:30,top:60,bottom:40,w:20,h:20},init:{shape:'process',row:1,column:0,cx:20,cy:0,left:5,right:35,top:10,bottom:-10,w:30,h:20},other:{shape:'process',row:2,column:1,cx:right-10,cy:-30,left:right-20,right,top:-20,bottom:-40,w:20,h:20}};
  const frame=ctx.api.measureContainers([{id:'f',members:['init','other'],label:'title',titleWidth:60,titleHeight:8,titleGap:3}],byId,[{from:'start',to:'init',fromPort:'bottom',toPort:'top'}])[0];
  const p=ctx.api.containerLabelPoint(frame);assert.equal(p[0]-30-(20+0.25),3);assert.ok(frame.right>=p[0]+30+3);assert.ok(p[1]-4>=13);
 }
});
test('free text applies paragraph alignment before positioning multiline ink',()=>{
 const source=fs.readFileSync(generator,'utf8'),start=source.indexOf('    function createFreeText('),end=source.indexOf('\n    function ',start+1);
 for(const align of [undefined,'left','center','right']){
  const paragraphAttributes={},tf={textRange:{characterAttributes:{},paragraphAttributes},visibleBounds:[0,10,20,0]};
  const ctx={doc:{textFrames:{add:()=>tf}},parseRichText:t=>({text:t}),resolveFont:()=>({font:{}}),applyRichStyles:()=>{},centerText:()=>{},Justification:{LEFT:'left',CENTER:'center',RIGHT:'right'}};
  vm.runInNewContext(source.slice(start,end),ctx);ctx.createFreeText({t:'短行\n较长文字',align},10,10,8,{});assert.equal(paragraphAttributes.justification,align||'center');
 }
});
test('offset ellipse and diamond ports lie on shape boundaries rather than bounding boxes',()=>{
 const source=fs.readFileSync(generator,'utf8'),start=source.indexOf('    function shapeBoundaryPoint('),end=source.indexOf('\n    function ',start+1),ctx={};vm.runInNewContext(source.slice(start,end),ctx);
 const n={cx:50,cy:20,w:100,h:40,left:0,right:100,top:40,bottom:0};
 const e=ctx.shapeBoundaryPoint({...n,shape:'ellipse'},'top',75);assert.ok(Math.abs(((e[0]-50)/50)**2+((e[1]-20)/20)**2-1)<1e-10);
 const d=ctx.shapeBoundaryPoint({...n,shape:'decision'},'left',10);assert.equal(d[0],25);assert.equal(d[1],10);
});
