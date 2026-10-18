import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
for(const prefix of ['adobe/','production-runtime/adobe/']){
 const source=fs.readFileSync(new URL('../'+prefix+'illustrator.jsx',import.meta.url),'utf8');
 function harness(){const context={labelPlacement:null,paintReads:0,JFW:{bounds:b=>Array.from(b),labelPaintMetadata(){context.paintReads++;return {paintStack:[0,1],opaqueFill:true};}}};vm.createContext(context);vm.runInContext(source.slice(source.indexOf('function snapshot('),source.indexOf('function normalizeVector(')),context);return context;}
 function path(){return {name:'source',closed:false,clipping:false,guides:false,hidden:false,opacity:100,filled:true,stroked:true,strokeWidth:.5,strokeDashes:[3,1],fillColor:{typename:'GrayColor',gray:50},pathPoints:[{anchor:[1.123456789012345,2],leftDirection:[3,4],rightDirection:[5,6]}]};}
 test(prefix+'geometry-only baseline reads complete coordinates and topology exclusively',()=>{
  const p=path(),minimal={name:p.name,closed:p.closed,clipping:p.clipping,pathPoints:p.pathPoints},doc={pathItems:[minimal]};for(const key of ['pageItems','textFrames','artboards'])Object.defineProperty(doc,key,{get(){throw Error('unconsumed '+key);}});for(const key of ['filled','stroked','fillColor','opacity','strokeWidth','parent'])Object.defineProperty(minimal,key,{get(){throw Error('unconsumed '+key);}});
  const h=harness(),before=h.snapshot(doc,undefined,undefined,'geometry-only');assert.equal(h.paintReads,0);assert.deepEqual(JSON.parse(JSON.stringify(before.pathGeometry)),[{closed:false,clipping:false,points:[[[1.123456789012345,2,3,4],[5,6]]]}]);
  const full=h.snapshot({pageItems:[],textFrames:[],pathItems:[p],artboards:[{artboardRect:[0,10,10,0]}]},undefined,[],'without-paint');assert.equal(h.geometryPreserved(before.pathGeometry,full.protectedPathGeometry,1,0,0),true);full.pathGeometry[0].points[0][1][0]+=.1;assert.equal(h.geometryPreserved(before.pathGeometry,full.protectedPathGeometry,1,0,0),false);
 });
 test(prefix+'ordinary vector after retains all audited metadata without paint traversal',()=>{
  const font={name:'Song',family:'Song'},text={contents:'actual',name:'title',note:'',geometricBounds:[1,9,8,2],textRange:{characterAttributes:{textFont:font,size:8}}},doc={pageItems:[{typename:'PathItem'}],textFrames:[text],pathItems:[path()],artboards:[{artboardRect:[0,10,10,0]}]},h=harness(),full=h.snapshot(doc),after=h.snapshot(doc,undefined,[],'without-paint');assert.equal(h.paintReads,1);const expected=JSON.parse(JSON.stringify(full));for(const p of expected.pathGeometry){delete p.paintStack;delete p.opaqueFill;delete p.paintOrderStatus;}delete after.protectedPathGeometry;assert.deepEqual(JSON.parse(JSON.stringify(after)),expected);assert.equal(after.texts[0].font,'Song');assert.equal(after.pathGeometry[0].fillGray,50);assert.deepEqual(Array.from(after.pathGeometry[0].strokeDashes),[3,1]);
 });
 test(prefix+'call sites scope profiles to ordinary vector and preserve legacy full snapshots',()=>{
  assert.ok(source.includes("before=snapshot(doc,undefined,undefined,'geometry-only')"));assert.ok(source.includes("snapshot(doc,undefined,addedLegendPaths,p.route==='vector-reletter'?'without-paint':undefined)"));assert.ok(source.includes("mode==='inspect'"));assert.ok(source.includes('snapshot:snapshot(doc)'));assert.ok(source.includes('snapshot(doc,reuse?reuse.pathGeometry:undefined)'));
 });
}
