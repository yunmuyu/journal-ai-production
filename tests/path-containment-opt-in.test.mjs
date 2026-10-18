import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {auditDiagram} from '../lib/diagram-audit.mjs';import {validatePlan} from '../lib/core.mjs';
const fixtureMissing=n=>['rejected','corrected'].some(kind=>!fs.existsSync(new URL(`./fixtures/path-containment/${kind}-figure${n}-snapshot.json`,import.meta.url)))&&`Private rejected/corrected figure ${n} geometry fixture pair is unavailable`;
const fixture=n=>JSON.parse(fs.readFileSync(new URL(`./fixtures/path-containment/rejected-figure${n}-snapshot.json`,import.meta.url)));
const plan={version:1,figureId:'f_test',sourceHash:'a'.repeat(64),route:'vector-reletter',nativeSvg:true,diagramKind:'blockDiagram',fontSize:8,widthMm:79.375,replacements:[]};
for(const n of [5,6])test(`Rejects actual cropped figure ${n} only when plain-diagram path check is explicitly enabled`,{skip:fixtureMissing(n)},()=>{
 assert.equal(auditDiagram(fixture(n)).ok,true);
 assert.ok(auditDiagram(fixture(n),{checkPathContainment:true}).issues.some(i=>i.type==='visible_path_outside_artboard'));
 const correct=JSON.parse(fs.readFileSync(new URL(`./fixtures/path-containment/corrected-figure${n}-snapshot.json`,import.meta.url)));
 assert.equal(auditDiagram(correct,{checkPathContainment:true}).ok,true);
});
test('Accepts boolean opt-in on declared diagram and rejects ambiguous or non-diagram values',()=>{
 assert.equal(validatePlan({...plan,checkPathContainment:true}).checkPathContainment,true);
 assert.throws(()=>validatePlan({...plan,checkPathContainment:'yes'}),/path containment/);
 assert.throws(()=>validatePlan({...plan,diagramKind:undefined,checkPathContainment:true}),/path containment/);
});
test('Opt-in rejects missing actual artboard instead of silently treating it as contained',()=>{
 assert.throws(()=>auditDiagram({texts:[],pathGeometry:[]},{checkPathContainment:true}),/artboard/);
});
