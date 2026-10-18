import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePlan} from '../lib/core.mjs';
import {auditDiagram} from '../lib/diagram-audit.mjs';
const line=(points,extra={})=>({stroked:true,strokeWidthPt:.5,points:points.map(([x,y])=>[[x,y,x,y],[x,y]]),...extra});
test('explicit owner mapping enforces measured frame padding',()=>{
 const owner=line([[0,20],[30,20],[30,0],[0,0]],{closed:true,name:'ppt-frame'});
 const result=auditDiagram({texts:[{index:0,name:'label',text:'Qd',size:8,inkBounds:[2,18,28,2]}],pathGeometry:[owner]},{owners:[{textIndex:0,pathIndex:0,placement:'inside'}]});
 assert.ok(result.issues.some(i=>i.type==='node_text_padding'));
});
test('unmapped labels explicitly report incomplete owner coverage',()=>{
 const result=auditDiagram({texts:[{index:0,text:'label',size:8,inkBounds:[5,15,25,7]}],pathGeometry:[line([[0,25],[30,25]])]});
 assert.equal(result.coverage.ownerPadding,'incomplete');
});
test('combining hat cannot silently reach native export',()=>{
 assert.throws(()=>validatePlan({version:1,figureId:'ftest',sourceHash:'a'.repeat(64),route:'raster-reletter',fontSize:8,widthMm:80,texts:[{text:'x\u0302',x:.5,y:.5}]}),/COMBINING_MARK_REQUIRES_VECTOR_ACCENT/);
});
