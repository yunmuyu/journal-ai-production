import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {auditDiagram} from '../production-runtime/lib/diagram-audit.mjs';

const runtimeRender=readFileSync(new URL('../production-runtime/lib/render.mjs',import.meta.url),'utf8');

test('Production renderer wires diagram audits and hashes both audit dependencies',()=>{
 assert.match(runtimeRender,/import \{auditDiagram\} from '\.\/diagram-audit\.mjs'/);
 assert.match(runtimeRender,/lib\/diagram-audit\.mjs/);
 assert.match(runtimeRender,/lib\/path-containment\.mjs/);
 assert.match(runtimeRender,/p\.diagramKind\|\|p\.route==='rebuild'/);
 assert.match(runtimeRender,/checkPathContainment:p\.checkPathContainment===true/);
});

test('Production containment audit rejects a visible path extending beyond the artboard',()=>{
 const snapshot={artboard:[0,100,100,0],texts:[],pathGeometry:[{
  name:'AI_FLOW_LINE',stroked:true,strokeWidthPt:0,closed:false,filled:false,
  points:[[[90,50,90,50],[90,50]],[[110,50,110,50],[110,50]]]
 }]};
 const result=auditDiagram(snapshot,{checkPathContainment:true});
 assert.ok(result.issues.some(issue=>issue.type==='visible_path_outside_artboard'));
});
