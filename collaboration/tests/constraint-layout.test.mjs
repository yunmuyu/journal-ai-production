import test from 'node:test';import assert from 'node:assert/strict';
import {solveLayout} from '../scripts/constraint-layout.mjs';
const scene=(elements,extra={})=>({version:1,units:'pt',canvas:{widthPt:220,heightPt:120},elements,...extra});
const text=(id,x,y,extra={})=>({id,kind:'text',x,y,widthPt:30,heightPt:10,fontSizePt:8,...extra});
test('moves chart legend around actual curve without moving scientific geometry',()=>{
 const input=scene([text('legend',20,30,{candidates:[{x:20,y:30},{x:160,y:10}]})],{obstacles:[{id:'curve',points:[[0,35],[200,35]]}]});const before=structuredClone(input),r=solveLayout(input);
 assert.equal(r.status,'solved');assert.equal(r.placements[0].x,160);assert.deepEqual(input,before);assert.equal(r.violations.length,0);
});
test('preserves pinned elements and searches coupled choices rather than greedy placement',()=>{
 const r=solveLayout(scene([text('pin',0,0,{fixed:true}),text('a',50,0,{candidates:[{x:50,y:0},{x:100,y:0}]}),text('b',50,0,{candidates:[{x:50,y:0}]})]));
 assert.equal(r.status,'solved');assert.equal(r.placements.find(p=>p.id==='a').x,100);assert.equal(r.placements.find(p=>p.id==='pin').x,0);assert.equal(r.optimalWithinDomains,true);
});
test('cannot shrink font or enlarge user canvas to hide an impossible placement',()=>{
 const r=solveLayout(scene([text('too-wide',0,0,{widthPt:300,candidates:[{x:0,y:0}]})]));assert.equal(r.status,'infeasible');
 assert.equal(solveLayout(scene([text('tiny',0,0,{fontSizePt:5})])).status,'needs-measurement');
});
test('routes arrow around protected image and keeps endpoint ports',()=>{
 const r=solveLayout(scene([{id:'a',kind:'shape',x:0,y:30,widthPt:20,heightPt:20,fixed:true},{id:'obstacle',kind:'image',x:70,y:25,widthPt:40,heightPt:30,fixed:true},{id:'b',kind:'shape',x:180,y:30,widthPt:20,heightPt:20,fixed:true}],{connections:[{id:'ab',from:'a',to:'b',fromPort:'right',toPort:'left'}]}));
 assert.equal(r.status,'solved');assert.deepEqual(r.routes[0].points[0],[20,40]);assert.deepEqual(r.routes[0].points.at(-1),[180,40]);assert.ok(r.routes[0].points.some(p=>p[1]<25||p[1]>55));
});
test('reports exhausted budget honestly and never fabricates a pass',()=>{
 let t=0;const r=solveLayout(scene([text('a',0,0)]),{budgetMs:1,clock:()=>t++});assert.equal(r.status,'budget-exhausted');assert.equal(r.optimalWithinDomains,false);
});
test('alignment constraints are hard requirements',()=>{
 const r=solveLayout(scene([text('a',10,10,{fixed:true}),text('b',70,50,{candidates:[{x:70,y:50},{x:10,y:50}]})],{constraints:[{type:'align-left',ids:['a','b']}]}));assert.equal(r.status,'solved');assert.equal(r.placements.find(p=>p.id==='b').x,10);
});

test('allowed row/column variants are searched without changing labels',()=>{
 const tree={kind:'row',allowReflow:true,children:Array.from({length:4},(_,i)=>({kind:'box',id:'n'+i,text:'label'+i}))};
 const measurements=Object.fromEntries(tree.children.map(n=>[n.id,{text:n.text,font:'现 宋体 1',fontSizePt:8,widthPt:70,heightPt:8}]));
 const r=solveLayout({version:1,font:'现 宋体 1',fontSizePt:8,widthMm:80,tree,measurements});assert.equal(r.status,'solved');assert.equal(r.search.testedVariants,2);assert.equal(r.layout.finalFontSizePt,8);assert.equal(new Set(r.execution.shapes.map(n=>n.x)).size,1);
});
test('plot frame permits its own data series while labels still avoid the series',()=>{
 const r=solveLayout(scene([{id:'plot',kind:'plot',geometry:'outline',x:2,y:2,widthPt:210,heightPt:110,fixed:true},text('legend',20,30,{candidates:[{x:20,y:30},{x:160,y:10}]})],{obstacles:[{id:'series',ownerId:'plot',points:[[10,35],[200,35]]}]}));assert.equal(r.status,'solved');assert.equal(r.placements.find(p=>p.id==='legend').x,160);
});

test('matching objective agrees with exhaustive permutation check',()=>{
 const starts=[48,2,23],slots=[0,25,50];const input=scene(starts.map((x,i)=>text('label'+i,x,10,{widthPt:18,heightPt:8,candidates:slots.map(x=>({x,y:10}))})));
 const r=solveLayout(input),permutations=[[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]],minimum=Math.min(...permutations.map(p=>p.reduce((sum,j,i)=>sum+Math.abs(slots[j]-starts[i]),0)));
 assert.equal(r.search.algorithm,'min-cost matching');assert.equal(r.optimalWithinDomains,true);assert.ok(Math.abs(r.score-(minimum+68*18*.0001))<1e-8);
});
test('truncated domains cannot assert that the full problem is infeasible',()=>{
 const input=scene([text('a',0,0,{candidates:[{x:0,y:0},{x:80,y:0}]})],{obstacles:[{id:'block',x:0,y:0,widthPt:50,heightPt:20}]});
 const r=solveLayout(input,{maxCandidates:1});assert.equal(r.status,'candidate-domain-exhausted');assert.equal(r.optimalWithinDomains,false);
});
test('missing tree measurements remain unknown rather than mathematically infeasible',()=>{
 const r=solveLayout({version:1,font:'现 宋体 1',fontSizePt:8,widthMm:80,tree:{kind:'box',id:'a',text:'x'},measurements:{}});assert.equal(r.status,'needs-measurement');assert.equal(r.optimalWithinDomains,false);
});
