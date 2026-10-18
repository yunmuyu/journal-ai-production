import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
for(const prefix of ['adobe/','production-runtime/adobe/']){
 const code=fs.readFileSync(new URL('../'+prefix+'illustrator.jsx',import.meta.url),'utf8');
 function harness(){const body=code.slice(code.indexOf('function snapshot('),code.indexOf('function normalizeVector('));return vm.runInNewContext(body+';({snapshot,geometryPreserved})',{labelPlacement:null,JFW:{bounds:b=>Array.from(b),labelPaintMetadata:()=>({})}});}
 function path(name='source'){return {name,closed:false,clipping:false,stroked:true,filled:false,strokeWidth:.5,pathPoints:[{anchor:[1.123456789012345,2],leftDirection:[3,4],rightDirection:[5,6]}]};}
 function doc(paths){return {pageItems:[],textFrames:[],pathItems:paths,artboards:[{artboardRect:[0,10,10,0]}]};}
 test(prefix+'snapshot reads every DOM control coordinate array once without rounding',()=>{const p=path(),point=p.pathPoints[0],counts={};for(const key of ['anchor','leftDirection','rightDirection']){const value=point[key];Object.defineProperty(point,key,{get(){counts[key]=(counts[key]||0)+1;return value;}});}const h=harness(),s=h.snapshot(doc([p]));assert.equal(s.pathGeometry[0].points[0][0][0],1.123456789012345);assert.deepEqual(counts,{anchor:1,leftDirection:1,rightDirection:1});});
 for(const front of [true,false])test(prefix+'only this render legend references excluded, '+(front?'head':'tail'),()=>{const h=harness(),source=path('JFW_LEGEND_SAMPLE_0'),added=path('JFW_LEGEND_SAMPLE_0'),before=h.snapshot(doc([source]));const paths=front?[added,source]:[source,added],after=h.snapshot(doc(paths),undefined,[added]);assert.equal(after.pathGeometry.length,2);assert.equal(h.geometryPreserved(before.pathGeometry,after.protectedPathGeometry,1,0,0),true);source.pathPoints[0].anchor[0]+=1;const changed=h.snapshot(doc(paths),undefined,[added]);assert.equal(h.geometryPreserved(before.pathGeometry,changed.protectedPathGeometry,1,0,0),false);assert.equal(h.geometryPreserved(before.pathGeometry,h.snapshot(doc(paths),undefined,[]).protectedPathGeometry,1,0,0),false);});
}
for(const prefix of ['adobe/','production-runtime/adobe/'])test(prefix+'final geometry validates actual fit including all handles',()=>{
 const code=fs.readFileSync(new URL('../'+prefix+'illustrator.jsx',import.meta.url),'utf8');const body=code.slice(code.indexOf('function geometryPreserved('),code.indexOf('function normalizeVector('));
 const context=vm.createContext({labelPlacement:{frameEdits:[]}});vm.runInContext(body,context);
 const before=[{closed:false,clipping:false,points:[[[1,2,3,4],[5,6]]]}],fit={scale:.75,origin:[-7,20]},after=structuredClone(before);
 for(const point of after[0].points)for(const part of point)for(let i=0;i<part.length;i++)part[i]=fit.origin[i%2]+((part[i]-(i%2?9:8))*2-fit.origin[i%2])*fit.scale;
 assert.equal(context.geometryPreserved(before,after,2,8,9,fit),true);after[0].points[0][1][1]+=.1;assert.equal(context.geometryPreserved(before,after,2,8,9,fit),false);
});
for(const prefix of ['adobe/','production-runtime/adobe/']){
 test(prefix+'overlay creation records actual path references and legend-only plans run overlays',()=>{
  const code=fs.readFileSync(new URL('../'+prefix+'illustrator.jsx',import.meta.url),'utf8'),body=code.slice(code.indexOf('function applyOverlays('),code.indexOf('function saveOutputs('));
  const paths=[],ctx={doc:{pathItems:{add(){const path={setEntirePath(points){this.points=points;}};paths.push(path);return path;}}},addedLegendPaths:[],gray:n=>n};vm.runInNewContext(body+';applyOverlays({lineSamples:[{from:[0,0],to:[1,1],style:"dashed"}]},100,50)',ctx);
  assert.equal(ctx.addedLegendPaths.length,1);assert.equal(ctx.addedLegendPaths[0],paths[0]);assert.equal(paths[0].name,'JFW_LEGEND_SAMPLE_0');assert.deepEqual(Array.from(paths[0].strokeDashes),[3,1.5]);
  assert.ok(code.includes("if((p.masks||[]).length||(p.texts||[]).length||(p.lineSamples||[]).length){var overlayAB"));assert.ok(code.includes('var after=snapshot(doc,undefined,addedLegendPaths,'));assert.ok(!code.includes('geometryPreserved(before.pathGeometry,snapshot(doc)'));
 });
 test(prefix+'native label point capture reads control coordinate arrays once',()=>{
  const code=fs.readFileSync(new URL('../'+prefix+'label-placement-native.jsx',import.meta.url),'utf8'),counts={},point={};for(const key of ['anchor','leftDirection','rightDirection'])Object.defineProperty(point,key,{get(){counts[key]=(counts[key]||0)+1;return [1.123456789012345,2];}});
  const p={name:'curve',stroked:false,filled:false,pathPoints:[point]},ctx={JFW:{bounds:b=>b}};vm.runInNewContext(code,ctx);ctx.JFW.createLabelPlacementSession({pathItems:[p]});assert.deepEqual(counts,{anchor:1,leftDirection:1,rightDirection:1});
 });
}
