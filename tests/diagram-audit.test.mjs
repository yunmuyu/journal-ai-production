import test from 'node:test';
import assert from 'node:assert/strict';
import {auditDiagram} from '../lib/diagram-audit.mjs';
const text={index:0,name:'AI_FLOW_TEXT_step',text:'采集数据',inkBounds:[5,15,25,7]};
const line=(anchors,extra={})=>({stroked:true,strokeWidthPt:0.5,closed:false,points:anchors.map(([x,y])=>[[x,y,x,y],[x,y]]),...extra});
test('Rejects a connector crossing text even when there is no text overlap',()=>{
 const result=auditDiagram({texts:[text],pathGeometry:[line([[0,10],[30,10]])]});
 assert.equal(result.issues[0].type,'text_path_collision');
});
test('Allows a connector and frame with the measured editorial clearance',()=>{
 const frame=line([[0,20],[30,20],[30,0],[0,0]],{closed:true,name:'AI_FLOW_NODE_step'});
 assert.deepEqual(auditDiagram({texts:[text],pathGeometry:[frame,line([[30,10],[40,10]])]}).issues,[]);
});
test('Rejects inadequate box padding and ignores guides rather than visible connectors',()=>{
 const frame=line([[4,16],[26,16],[26,6],[4,6]],{closed:true,name:'AI_FLOW_NODE_step'});
 assert.ok(auditDiagram({texts:[text],pathGeometry:[frame]}).issues.some(i=>i.type==='node_text_padding'));
 assert.deepEqual(auditDiagram({texts:[text],pathGeometry:[line([[0,10],[30,10]],{guides:true})]}).issues,[]);
});
test('Detects a curved border that bows through the text',()=>{
 const curve=line([[0,20],[30,20]]);curve.points[0][1]=[10,-10];curve.points[1][0][2]=20;curve.points[1][0][3]=-10;
 assert.ok(auditDiagram({texts:[text],pathGeometry:[curve]}).issues.some(i=>i.type==='text_path_collision'));
});
test('Rejects a side caption that almost touches the outer feedback line',()=>{
 const caption={...text,name:'AI_FLOW_FREE_TEXT',note:'JFW_DIAGRAM_SIDE_RIGHT',inkBounds:[31,15,39,7]};
 assert.ok(auditDiagram({texts:[caption],pathGeometry:[line([[30,20],[30,0]],{name:'AI_FLOW_LINE'})]}).issues.some(i=>i.type==='side_label_clearance'));
 assert.deepEqual(auditDiagram({texts:[{...caption,inkBounds:[33.25,15,41.25,7]}],pathGeometry:[line([[30,20],[30,0]],{name:'AI_FLOW_LINE'})]}).issues,[]);
});
test('A missing diagram path inventory is not a successful layout audit',()=>{
 assert.equal(auditDiagram({texts:[text],pathGeometry:[]}).ok,false);
});
