import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {auditDiagram} from '../lib/diagram-audit.mjs';
const fixture=new URL('./fixtures/text-first-boxes.json',import.meta.url);
const missingFixture=!existsSync(fixture)&&'Private measured-artwork fixture tests/fixtures/text-first-boxes.json is unavailable';
const evidence=missingFixture?null:JSON.parse(readFileSync(fixture,'utf8'));
test('rejects the actual text-outside-frame draft even without text overlap',{skip:missingFixture},()=>{
 const audit=auditDiagram(evidence.before);
 assert.equal(audit.ok,false);
 assert.ok(audit.issues.some(i=>i.type==='text_path_collision'));
});
test('accepts the actual measured frame after uniform scaling with fractional type',{skip:missingFixture},()=>{
 assert.ok(evidence.after.texts[0].size>6&&evidence.after.texts[0].size<7);
 assert.deepEqual(auditDiagram(evidence.after).issues,[]);
});
test('reduced clearances require recorded uniform scaling evidence',{skip:missingFixture},()=>{
 const snapshot=structuredClone(evidence.after);delete snapshot.texts[0].layoutScale;
 assert.ok(auditDiagram(snapshot).issues.some(i=>i.type==='node_text_padding'));
});
