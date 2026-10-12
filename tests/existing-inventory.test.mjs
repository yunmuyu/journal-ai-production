import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../adobe/existing-export.jsx', import.meta.url), 'utf8');
function inventoryFor(rootCount, textCount) {
  const layer = {typename:'Layer'};
  const roots = [];
  for (let i = 0; i < rootCount; i++) {
    roots.push({typename:i === 0 ? 'GroupItem' : 'CompoundPathItem', name:'root-'+i, parent:layer,
      guides:false, hidden:false, locked:false, visibleBounds:[i,10,i+1,9]});
  }
  const frames = [];
  for (let j = 0; j < textCount; j++) {
    const root = roots[j % rootCount];
    const parent = root.typename === 'GroupItem' ? {typename:'GroupItem', parent:root} : root;
    frames.push({typename:'TextFrame', parent, contents:'text-'+j});
  }
  const counts = {length:0, index:0};
  const textFrames = new Proxy(frames, {get(target, key, receiver) {
    if (key === 'length') counts.length++;
    if (typeof key === 'string' && /^\d+$/.test(key)) counts.index++;
    return Reflect.get(target, key, receiver);
  }});
  const d = {pageItems:roots, textFrames,
    artboards:[{artboardRect:[0,10,rootCount,0]}]};
  const context = {JFW:{bounds(value){return Array.prototype.slice.call(value);}}};
  vm.runInNewContext(source, context);
  return {result:context.JFW.existingInventory(d), counts};
}

test('existing inventory reads text frames once and preserves root text order and fields', () => {
  const {result, counts} = inventoryFor(8, 24);
  assert.ok(counts.length <= 2, `textFrames.length read ${counts.length} times for 8 roots and 24 frames; expected a single enumeration`);
  assert.ok(counts.index <= 24, `textFrames indexed ${counts.index} times; expected one pass`);
  assert.deepEqual(JSON.parse(JSON.stringify(result.items[0])), {index:0,type:'GroupItem',name:'root-0',bounds:[0,10,1,9],hidden:false,locked:false,texts:['text-0','text-8','text-16']});
  assert.deepEqual(JSON.parse(JSON.stringify(result.items[1].texts)), ['text-1','text-9','text-17']);
  assert.equal(result.items[7].index, 7);
  assert.deepEqual(JSON.parse(JSON.stringify(result.artboards)), [[0,10,8,0]]);
});

function exportFor(scale) {
  const layer = {typename:'Layer'};
  const bounds = [5,110,105,10];
  const originalBounds = bounds.slice();
  const sourceItem = {parent:layer, hidden:false, guides:false, visibleBounds:bounds.slice(),
    duplicate(){return {move(){}};}};
  let resizeArgs = null;
  let added = null;
  const group = {
    _bounds:bounds.slice(),
    get visibleBounds(){return this._bounds.slice();},
    resize(){
      resizeArgs = Array.prototype.slice.call(arguments);
      const ratio = arguments[0] / 100;
      const b = this._bounds, cx=(b[0]+b[2])/2, cy=(b[1]+b[3])/2;
      this._bounds=[cx+(b[0]-cx)*ratio,cy+(b[1]-cy)*ratio,cx+(b[2]-cx)*ratio,cy+(b[3]-cy)*ratio];
    },
    translate(dx,dy){this._bounds=[this._bounds[0]+dx,this._bounds[1]+dy,this._bounds[2]+dx,this._bounds[3]+dy];}
  };
  const doc = {layers:[{}],groupItems:{add(){return group;}},artboards:[{artboardRect:null}],activate(){},close(){}};
  const context = {JFW:{bounds(value){return Array.prototype.slice.call(value);}},
    app:{documents:{add(color,width,height){added={color,width,height};return doc;}}},
    ElementPlacement:{PLACEATBEGINNING:1},SaveOptions:{DONOTSAVECHANGES:1}};
  vm.runInNewContext(source, context);
  assert.equal(typeof context.JFW.exportExisting, 'function', 'existing-export.jsx must retain the exportExisting entry point');
  const req={items:[{index:0,bounds:bounds.slice()}]};
  if(scale!==undefined)req.scale=scale;
  const result=context.JFW.exportExisting({pageItems:[sourceItem],documentColorSpace:'RGB'},req);
  assert.deepEqual(sourceItem.visibleBounds, originalBounds, 'scaling the copied group must leave the source item unchanged');
  return {result,resizeArgs,added,doc};
}

test('existing export scales the copied group, strokes and text together, then trims to 0.25pt protection edges', () => {
  const {result,resizeArgs,added,doc}=exportFor(0.75);
  assert.deepEqual(resizeArgs,[75,75,true,true,true,true,75], 'GroupItem.resize must use Illustrator scale percentages and scale line widths');
  assert.deepEqual(added,{color:'RGB',width:75.5,height:75.5});
  assert.deepEqual(JSON.parse(JSON.stringify(result.sourceBounds)),[5,110,105,10]);
  assert.equal(result.scale,0.75);
  assert.deepEqual(JSON.parse(JSON.stringify(result.resultBounds)),[0.25,-0.25,75.25,-75.25]);
  assert.deepEqual(JSON.parse(JSON.stringify(doc.artboards[0].artboardRect)),[0,0,75.5,-75.5]);
});

test('existing export accepts the second explicit scale and defaults to the legacy 100 percent size', () => {
  const reduced=exportFor(0.875);
  assert.equal(reduced.result.scale,0.875);
  assert.equal(reduced.resizeArgs[0],87.5);
  const legacy=exportFor(undefined);
  assert.equal(legacy.result.scale,1);
  assert.equal(legacy.resizeArgs,null);
  assert.deepEqual(legacy.added,{color:'RGB',width:100.5,height:100.5});
});

test('existing export rejects unsupported scales before creating a destination document', () => {
  const context={JFW:{bounds(value){return Array.prototype.slice.call(value);}},
    app:{documents:{add(){throw Error('destination created before validation');}}},
    ElementPlacement:{PLACEATBEGINNING:1},SaveOptions:{DONOTSAVECHANGES:1}};
  vm.runInNewContext(source,context);
  assert.equal(typeof context.JFW.exportExisting,'function');
  assert.throws(()=>context.JFW.exportExisting({pageItems:[],documentColorSpace:'RGB'}, {items:[{index:0,bounds:[5,110,105,10]}],scale:0.8}), /Invalid export scale/);
});
