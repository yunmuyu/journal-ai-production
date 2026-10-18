import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFileSync} from 'node:fs';import path from 'node:path';
const source=readFileSync(process.env.JFW_FLOWCHART_ROOT?path.join(process.env.JFW_FLOWCHART_ROOT,'assets/AI流程图生成器.jsx'):new URL('../production-runtime/flowchart/assets/AI流程图生成器.jsx',import.meta.url),'utf8');
const context={JFW:{},app:{textFonts:{getByName(name){if(name!=='ATC-73b000205b8b4f530020*1')throw Error('missing');return {name,family:'现 宋体 1'};}}}};vm.createContext(context);vm.runInContext(readFileSync(new URL('../adobe/editorial-generator.jsx',import.meta.url),'utf8'),context);const adapted=context.JFW.adaptEditorialGenerator(source);
function functionCode(name,code=adapted){const start=code.indexOf('function '+name+'('),end=code.indexOf('\n    function ',start+9);return code.slice(start,end);}
test('Measured adapter compiles and cannot silently fall back to SimSun',()=>{new vm.Script(adapted.replace(/^#target[^\n]*\n/,''));assert.equal(context.JFW.editorialFont().family,'现 宋体 1');assert.throws(()=>context.JFW.adaptEditorialGenerator('changed generator'),/boundary/);});
test('Diamond branch starts at vertex even when bounding boxes overlap',()=>{const c={};vm.createContext(c);vm.runInContext(functionCode('shapeBoundaryPoint')+functionCode('portPoint')+functionCode('opposingHorizontalPortPoints'),c);const a={shape:'decision',cx:20,cy:30,left:0,right:40,top:50,bottom:10,w:40,h:40},b={shape:'process',cx:70,cy:45,left:50,right:90,top:52,bottom:38,w:40,h:14};assert.equal(c.opposingHorizontalPortPoints(a,b,'right','left')[0][1],30);});
test('Compacting XYZ keeps the parent row aligned with the middle box',()=>{const c={CFG:{GAP_MINIMAL:3,GAP:9}};vm.createContext(c);vm.runInContext(functionCode('applyVerticalStacks'),c);const nodes={x:{cy:50,h:14,top:57,bottom:43},y:{cy:25,h:14,top:32,bottom:18},z:{cy:0,h:14,top:7,bottom:-7}};c.applyVerticalStacks([{members:['x','y','z'],gap:'minimal'}],nodes);assert.equal(nodes.y.cy,25);assert.equal(nodes.x.bottom-nodes.y.top,3);assert.equal(nodes.y.bottom-nodes.z.top,3);});
test('Long bottom-right container titles stay inside the actual frame',()=>{
 const moves=[],tf={duplicate(){return{createOutline(){return{visibleBounds:[72,18,128,10],remove(){}};}};},translate(x,y){moves.push([x,y]);}};
 context.JFW.alignContainerLabel(tf,{left:0,right:100,top:40,bottom:0,labelPosition:'bottomRight'},8);
 assert.deepEqual(moves,[[-31,0]]);
});
test('An oversized container title must stop rather than overlap its frame',()=>{
 const tf={duplicate(){return{createOutline(){return{visibleBounds:[0,18,120,10],remove(){}};}};},translate(){throw Error('must not move');}};
 assert.throws(()=>context.JFW.alignContainerLabel(tf,{left:0,right:100,top:40,bottom:0,labelPosition:'bottomRight'},8),/Container title exceeds/);
});
test('Diagram labels reserve their measured height and container title band',()=>{
 const c={data:{fontSize:8},CFG:{CONTAINER_PAD_MINIMAL:3,CONTAINER_PAD_TIGHT:9,CONTAINER_PAD_NORMAL:18},measureContainerTitle(){return{w:16,h:17};},resolveFont(){return{font:{}};}};
 vm.createContext(c);vm.runInContext(functionCode('displayText')+functionCode('containerPaddingY')+functionCode('containerPaddingBottom')+functionCode('edgeLabelPoint'),c);
 assert.equal(c.containerPaddingBottom({label:'区域',labelPosition:'bottomRight',padding:'minimal',titleHeight:17,titleGap:3},20),23);
 const p=c.edgeLabelPoint({label:'串口通信',labelSegment:0,labelSide:'above'},[[0,0],[40,0]],{},'right','left',8,{});
 assert.equal(p[1],11.5);
});
test('Side notes clear the outer feedback line rather than only the nearest node',()=>{
 const moves=[],tf={duplicate(){return{createOutline(){return{visibleBounds:[98,20,106,0],remove(){}};}};},translate(x,y){moves.push([x,y]);}};
 const doc={pathItems:[{name:'AI_FLOW_NODE_a',geometricBounds:[0,30,80,0],stroked:true,strokeWidth:.5},{name:'AI_FLOW_LINE',geometricBounds:[100,30,110,0],stroked:true,strokeWidth:.5}]};
 assert.equal(typeof context.JFW.positionDiagramSideLabel,'function');
 context.JFW.positionDiagramSideLabel(tf,'right',doc,8);assert.deepEqual(moves,[[15.25,0]]);
});
for(const adapter of ['../adobe/editorial-generator.jsx','../production-runtime/adobe/editorial-generator.jsx'])test(adapter+' via route cannot erase the clearance reserved for a long connection label',()=>{
 const adapterContext={JFW:{}};vm.runInNewContext(readFileSync(new URL(adapter,import.meta.url),'utf8'),adapterContext);const code=adapterContext.JFW.adaptEditorialGenerator(source);
 const c={data:{fontSize:8},CFG:{GAP:8.5,BUS_LEG:5.7},measureText(){return{w:40,h:8};},resolveFont(){return{font:{}};},shaftRouteGap(){return 8.5;}};vm.createContext(c);vm.runInContext(functionCode('displayText',code)+functionCode('columnTrackGaps',code),c);
 const byId={a:{id:'a',row:0,column:0},b:{id:'b',row:0,column:1}};
 const gaps=c.columnTrackGaps([],byId,[{from:'a',to:'b',fromPort:'right',toPort:'left',label:'连接说明',via:[{x:'from+gap',y:'from'},{x:'to-gap',y:'to'}]}],2,4);
 assert.ok(gaps[0]>=46,'The full label width and 6pt clearance must survive via routing');
 const unlabelled=c.columnTrackGaps([],byId,[{from:'a',to:'b',fromPort:'right',toPort:'left',via:[{x:'from+gap',y:'from'}]}],2,4);
 assert.equal(unlabelled[0],17,'Unlabelled via routing retains its original geometric gap');
});
