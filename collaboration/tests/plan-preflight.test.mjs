import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {preflightPlan} from '../scripts/plan-preflight.mjs';

const generatorFile = path.join(mkdtempSync(path.join(tmpdir(), 'jfw-generator-contract-')), 'generator.jsx');
writeFileSync(generatorFile, `var PT_PER_MM = 2.83464566929;
var CFG = {MARGIN: 12, SINGLE_COLUMN_WIDTH: 80 * PT_PER_MM};
var availableW = ab[2] - ab[0] - CFG.MARGIN * 2;
var maxW = data.widthClass === "double" ? availableW : Math.min(CFG.SINGLE_COLUMN_WIDTH, availableW);
if (root.fontSize !== undefined && root.fontSize !== 8 && root.fontSize !== 7 && root.fontSize !== 6) throw "fontSize";
if (root.fontSize !== 8) throw "[module-tree]";
`);
const plan = (fontSize=7, widthMm=80) => ({route:'rebuild',fontSize,widthMm,graph:{fontSize,widthClass:widthMm===80?'single':'double',nodes:[{id:'a'}]}});

test('reports generator content capacity after its actual 12 pt margins', () => {
  const single=preflightPlan(plan(),{generatorFile});
  assert.ok(Math.abs(single.contentWidthPt-(80*72/25.4-24))<0.001);
  assert.ok(Math.abs(single.contentWidthMm-(80-24*25.4/72))<0.001);
  const double=preflightPlan(plan(8,160),{generatorFile});
  assert.ok(Math.abs(double.contentWidthPt-(160*72/25.4-24))<0.001);
});

test('stops unsupported or mismatched graph sizes before Adobe', () => {
  assert.throws(()=>preflightPlan(plan(7.5),{generatorFile}),/generator.*6.*7.*8/i);
  const wrong=plan();wrong.graph.fontSize=8;
  assert.throws(()=>preflightPlan(wrong,{generatorFile}),/graph.fontSize.*plan.fontSize/);
  const missing=plan();delete missing.graph.fontSize;
  assert.throws(()=>preflightPlan(missing,{generatorFile}),/graph.fontSize.*plan.fontSize/);
  const tree=plan();tree.graph.treeLayout='module';
  assert.throws(()=>preflightPlan(tree,{generatorFile}),/module.tree.*8 pt/i);
  tree.fontSize=tree.graph.fontSize=8;
  assert.equal(preflightPlan(tree,{generatorFile}).fontSizePt,8);
});

test('fails closed if generator width contract changes', () => {
  const changed=path.join(path.dirname(generatorFile),'changed.jsx');
  writeFileSync(changed,'var CFG = {MARGIN: 10};');
  assert.throws(()=>preflightPlan(plan(),{generatorFile:changed}),/generator.*contract/i);
});

test('rejects invalid text-group rotations on vector plans without altering the plan', () => {
  const vector={route:'vector-reletter',fontSize:7.5,textGroups:[{rotation:45}]};
  const original=structuredClone(vector);
  assert.throws(()=>preflightPlan(vector),/textGroups\[0\]\.rotation/);
  assert.deepEqual(vector,original);
  for(const rotation of [-90,0,90])assert.equal(preflightPlan({...vector,textGroups:[{rotation}]}),null);
});

test('native parallel chains bypass the external generator contract', () => {
  const native={route:'rebuild',nativeLayout:'parallel-chains',fontSize:6.5,widthMm:80,graph:{nodes:[]}};
  const original=structuredClone(native);
  assert.equal(preflightPlan(native),null);
  assert.deepEqual(native,original);
});

test('empty-node freeform uses generator fixed 8 pt even when plan requests 7 pt', () => {
  const freeform=plan(7);freeform.graph.kind='freeform';freeform.graph.nodes=[];
  freeform.graph.freeTexts=[{text:'caption',x:0.5,y:0.5}];
  assert.throws(()=>preflightPlan(freeform,{generatorFile}),/Freeform generator uses fixed 8 pt/);
});
