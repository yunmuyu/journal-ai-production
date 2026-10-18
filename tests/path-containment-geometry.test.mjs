import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {auditDiagram as baseAuditDiagram} from '../lib/diagram-audit.mjs';
const auditDiagram=(snapshot)=>baseAuditDiagram(snapshot,{checkPathContainment:true});
const fixtureMissing=(n,kind='rejected')=>!fs.existsSync(new URL(`./fixtures/path-containment/${kind}-figure${n}-snapshot.json`,import.meta.url))&&`Private ${kind} figure ${n} geometry fixture is unavailable`;
const fixture=n=>JSON.parse(fs.readFileSync(new URL(`./fixtures/path-containment/rejected-figure${n}-snapshot.json`,import.meta.url)));
const line=(points,extra={})=>({stroked:true,strokeWidthPt:.5,closed:false,points:points.map(([x,y])=>[[x,y,x,y],[x,y]]),...extra});
for(const n of [5,6])test(`Rejects actual figure ${n} with paths outside cropped artboard`,{skip:fixtureMissing(n)},()=>{
 const snapshot=fixture(n);
 const result=auditDiagram(snapshot);
 assert.ok(result.issues.some(i=>i.type==='visible_path_outside_artboard'));
 assert.equal(result.ok,false);
});
for(const n of [5,6])test(`Allows actual figure ${n} geometry when its full boundary is inside the artboard`,{skip:fixtureMissing(n)},()=>{
  const snapshot=fixture(n);snapshot.artboard=n===5?[1.5,-.5,223.5,-403.5]:[.5,-7.5,224.5,-92.5];
  assert.ok(!auditDiagram(snapshot).issues.some(i=>i.type==='visible_path_outside_artboard'));
});
test('Excludes hidden, transparent, guides and clipping-mask paths',()=>{
 const snapshot={artboard:[0,20,20,0],texts:[],pathGeometry:[
  line([[-20,10],[-10,10]],{hidden:true}),line([[-20,10],[-10,10]],{opacity:0}),
  line([[-20,10],[-10,10]],{guides:true}),line([[-20,10],[-10,10]],{clipping:true})]};
 assert.equal(auditDiagram(snapshot).ok,true);
});
test('Uses declared effective ancestor clipping bounds rather than rejecting clipped-off geometry',()=>{
 const snapshot={artboard:[0,20,20,0],texts:[],pathGeometry:[line([[-10,10],[30,10]],{effectiveClipBounds:[1,19,19,1]})]};
 assert.equal(auditDiagram(snapshot).ok,true);
});
test('Detects an actual cubic extremum and does not reject a harmless outside control handle',()=>{
 const snapshot={artboard:[0,20,20,0],texts:[],pathGeometry:[line([[1,10],[19,10]])]};
 snapshot.pathGeometry[0].points[0][1]=[6,20.1];snapshot.pathGeometry[0].points[1][0][2]=14;snapshot.pathGeometry[0].points[1][0][3]=20.1;
 assert.equal(auditDiagram(snapshot).ok,true);
 snapshot.pathGeometry[0].points[0][1]=[6,40];snapshot.pathGeometry[0].points[1][0][3]=40;
 assert.ok(auditDiagram(snapshot).issues.some(i=>i.type==='visible_path_outside_artboard'));
});
test('Includes stroke half-width at the physical page boundary',()=>{
 const snapshot={artboard:[0,20,20,0],texts:[],pathGeometry:[line([[0,10],[10,10]])]};
 assert.ok(auditDiagram(snapshot).issues.some(i=>i.type==='visible_path_outside_artboard'));
});
for(const n of [5,6])test(`Accepts actually rendered explicit-path figure ${n} with all geometry in page`,{skip:fixtureMissing(n,'corrected')},()=>{
 const snapshot=JSON.parse(fs.readFileSync(new URL(`./fixtures/path-containment/corrected-figure${n}-snapshot.json`,import.meta.url)));
 const result=auditDiagram(snapshot);
 assert.equal(result.ok,true,JSON.stringify(result.issues));
});
