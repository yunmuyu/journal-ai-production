import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {validatePlan} from '../lib/core.mjs';
import {validatePlan as validateRuntimePlan} from '../production-runtime/lib/core.mjs';

const plan = layout => ({version:1,figureId:'flayout',sourceHash:'a'.repeat(64),route:'vector-reletter',fontSize:8,widthMm:80,normalizeWidth:true,overlayFrame:'source-artboard',replacements:[],texts:[{text:'Label',x:.5,y:.5,align:'center',valign:'center',layout}]});
for (const [name, validate] of [['source',validatePlan],['runtime',validateRuntimePlan]]) {
  test(`${name}: placement requires explicit owner and bounded search`, () => {
    for (const layout of [{}, {ownerPathIndex:-1}, {ownerPathIndex:0,placements:['anywhere']}, {ownerPathIndex:0,maxDistancePt:100}, {ownerPathIndex:0,allowFrameExpansionPt:100}, {ownerPathIndex:0,rotations:[45]}]) {
      assert.throws(() => validate(plan(layout)), /label layout/);
    }
    assert.equal(validate(plan({ownerPathIndex:0,placements:['inside','left'],maxDistancePt:8})).texts[0].layout.ownerPathIndex,0);
    const invalid=plan({ownerPathIndex:0});invalid.route='compose';
    assert.throws(() => validate(invalid), /label layout/);
  });
}

function nativeHarness(solveResult) {
  const context={JFW:{bounds:b=>Array.from(b)},JFWLabelPlacement:{solve:input=>{context.input=input;return solveResult;}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(new URL('../adobe/label-placement-native.jsx',import.meta.url),'utf8'),context);
  return context;
}
function mockPath() {
  return {name:'frame',closed:true,stroked:true,strokeWidth:.5,filled:false,clipping:false,guides:false,hidden:false,opacity:100,strokeDashes:[3,1],pathPoints:[{anchor:[0,40],leftDirection:[0,40],rightDirection:[0,40]},{anchor:[40,40],leftDirection:[40,40],rightDirection:[40,40]},{anchor:[40,0],leftDirection:[40,0],rightDirection:[40,0]},{anchor:[0,0],leftDirection:[0,0],rightDirection:[0,0]}]};
}
function mockFrame(ink) {
  return {contents:'Label',delta:[0,0],duplicate(){return {createOutline:()=>({visibleBounds:ink.map((v,i)=>v+this.delta[i%2]),remove(){}})};},translate(dx,dy){this.delta=[this.delta[0]+dx,this.delta[1]+dy];}};
}
test('Native session measures actual ink and moves existing text, without exporting', () => {
  const result={ok:true,placements:[{id:'0',dx:3,dy:4,inkBounds:[3,14,23,4]}],frameEdits:[],issues:[]};
  const c=nativeHarness(result),f=mockFrame([0,10,20,0]),fixed=mockFrame([70,80,90,60]);
  const p=mockPath(),doc={pathItems:[p],textFrames:[f,fixed],artboards:[{artboardRect:[0,100,100,0]}]};
  const session=c.JFW.createLabelPlacementSession(doc);
  assert.equal(session.place([{frame:f,layout:{ownerPathIndex:0},id:'0'}]).ok,true);
  assert.deepEqual(f.delta,[3,4]);
  assert.deepEqual(Array.from(c.input.labels[0].inkBounds),[0,10,20,0]);
  assert.equal(c.input.fixedTexts.length,1);
  assert.equal(c.input.paths[0].strokeDashes[0],3);
});
test('Native placement verifies actual moved ink before allowing export', () => {
  const c=nativeHarness({ok:true,placements:[{id:'0',dx:3,dy:4,inkBounds:[3,14,23,4]}],frameEdits:[],issues:[]});
  const f=mockFrame([0,10,20,0]);f.translate=()=>{};
  const doc={pathItems:[mockPath()],textFrames:[f],artboards:[{artboardRect:[0,100,100,0]}]};
  const result=c.JFW.createLabelPlacementSession(doc).place([{frame:f,layout:{ownerPathIndex:0},id:'0'}]);
  assert.equal(result.ok,false);assert.equal(result.issues[0].type,'native_label_position_mismatch');
});
test('Visible clipped images are passed as solid obstacles, preserving source pixels', () => {
  const c=nativeHarness({ok:false,placements:[],frameEdits:[],issues:[]}),f=mockFrame([0,10,20,0]);
  const clip={clipping:true,geometricBounds:[20,80,60,40]};
  const image={visibleBounds:[0,100,100,0],parent:{typename:'GroupItem',clipped:true,pathItems:[clip]}};
  const doc={pathItems:[mockPath()],textFrames:[f],rasterItems:[image],artboards:[{artboardRect:[0,100,100,0]}]};
  c.JFW.createLabelPlacementSession(doc).place([{frame:f,layout:{ownerPathIndex:0},id:'0'}]);
  const p=c.input.paths.at(-1);assert.equal(p.solidObstacle,true);
  assert.deepEqual(Array.from(p.points[0][0]),[20,80,20,80]);
});
test('Native paint metadata preserves hierarchy and rejects transparent or compound fill as an occluder', () => {
  const c=nativeHarness({ok:false,placements:[],frameEdits:[],issues:[]});
  const doc={typename:'Document'},layer={typename:'Layer',name:'Layer',parent:doc};
  const group={typename:'GroupItem',parent:layer,opacity:100};
  const item={typename:'PathItem',parent:group,filled:true,closed:true,opacity:100,fillColor:{typename:'RGBColor'}};
  doc.layers=[layer];layer.pageItems=[group];group.pageItems=[item];
  Object.defineProperty(item,'zOrderPosition',{get(){throw Error('Native host does not expose this order');}});
  const metadata=c.JFW.labelPaintMetadata(item);
  assert.deepEqual(Array.from(metadata.paintStack),[0,0,0]);assert.equal(metadata.opaqueFill,true);
  group.opacity=50;assert.equal(c.JFW.labelPaintMetadata(item).opaqueFill,false);
  group.opacity=100;group.typename='CompoundPathItem';group.pathItems=[item,{parent:group}];assert.equal(c.JFW.labelPaintMetadata(item).opaqueFill,false);
});
test('Native session fails without moving text or exporting when no solution exists', () => {
  const c=nativeHarness({ok:false,placements:[],frameEdits:[],issues:[{type:'no_label_placement'}]});
  const f=mockFrame([0,10,20,0]),p=mockPath(),doc={pathItems:[p],textFrames:[f],artboards:[{artboardRect:[0,100,100,0]}]};
  const result=c.JFW.createLabelPlacementSession(doc).place([{frame:f,layout:{ownerPathIndex:0},id:'0'}]);
  assert.equal(result.ok,false);assert.deepEqual(f.delta,[0,0]);
});
test('Native session offers exact quarter-turn ink bounds while preserving existing text', () => {
  const c=nativeHarness({ok:false,placements:[],frameEdits:[],issues:[]});
  const f=mockFrame([0,10,20,0]),p=mockPath(),doc={pathItems:[p],textFrames:[f],artboards:[{artboardRect:[0,100,100,0]}]};
  c.JFW.createLabelPlacementSession(doc).place([{frame:f,layout:{ownerPathIndex:0,rotations:[0,-90]},id:'0',rotation:0}]);
  assert.deepEqual(Array.from(c.input.labels[0].variants[1].inkBounds),[5,15,15,-5]);
  assert.deepEqual(f.delta,[0,0]);
});
test('Protected geometry allows only the exact frame edit computed from measured source geometry', () => {
  for (const prefix of ['../adobe/','../production-runtime/adobe/']) {
    const code=fs.readFileSync(new URL(prefix+'illustrator.jsx',import.meta.url),'utf8');
    const body=code.match(/function geometryPreserved\([\s\S]*?(?=\r?\n\s*function normalizeVector)/)[0];
    const old=[{closed:true,clipping:false,points:[[[1,2,1,2],[1,2]]]}];
    const next=structuredClone(old);next[0].points[0]=[[2,2,2,2],[2,2]];
    const context={labelPlacement:{frameEdits:[{pathIndex:0,beforePoints:old[0].points,afterPoints:next[0].points}]}};
    vm.createContext(context);vm.runInContext(body,context);
    assert.equal(context.geometryPreserved(old,next,1,0,0),true);
    const changed=structuredClone(next);changed[0].points[0][1][0]=3;
    assert.equal(context.geometryPreserved(old,changed,1,0,0),false);
    const stale=structuredClone(old);stale[0].points[0][0][0]=2;
    assert.equal(context.geometryPreserved(stale,next,1,0,0),false);
  }
});
