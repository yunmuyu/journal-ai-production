import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
function api(){
 const ctx={JFW:{},app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('production-runtime/adobe/editorial-generator.jsx','utf8'),ctx);
 let code=ctx.JFW.adaptEditorialGenerator(fs.readFileSync('production-runtime/flowchart/assets/AI流程图生成器.jsx','utf8')).replace(/^#target[^\n]*\n/,'');
 code=code.replace('var sample = readSibling(', 'this.api={size:calibratedBoxSize,measure:measureLayout,position:positionLayout}; measureText=function(){return {w:40,h:8};}; return; var sample = readSibling(');
 vm.runInContext(code,ctx);return ctx.api;
}
test('ordinary and IO nodes use the same measured vertical padding',()=>{
 const a=api();for(const shape of ['process','inputOutput','predefinedProcess']){
 const box=a.size({shape,text:'text'},{w:40,h:8},8);assert.equal(box.h,13.4,shape);
 }
});
test('half column between occupied same-row columns reserves nonoverlapping space',()=>{
 const a=api(),layout=a.measure({nodes:[0,.5,1].map((column,i)=>({id:'n'+i,shape:'process',text:'text',row:0,column})),edges:[]},8,{});
 a.position(layout,[0,200,300,0]);
 for(let i=1;i<layout.nodes.length;i++)assert.ok(layout.nodes[i].left-layout.nodes[i-1].right>=3-1e-6,'same row gap must reserve complete node widths');
});
test('whole-layout fitting allows fractional type, never enlarges and blocks below 6pt',()=>{
 const ctx={JFW:{}};vm.runInNewContext(fs.readFileSync('production-runtime/adobe/editorial-layout.jsx','utf8'),ctx);
 assert.equal(ctx.JFW.layoutFitScale(100,150,8),1);
 assert.ok(Math.abs(ctx.JFW.layoutFitScale(300,240.5,8)*8-6.4)<1e-10);
 assert.throws(()=>ctx.JFW.layoutFitScale(400,240.5,8),/LAYOUT_REFLOW_REQUIRED/);
});
test('compact container members keep a 3pt gap without stretching empty space',()=>{
 const file='production-runtime/flowchart/assets/AI流程图生成器.jsx';let code=fs.readFileSync(file,'utf8').replace(/^#target[^\n]*\n/,'');
 code=code.replace('var sample = readSibling(', 'this.distribute=distributeContainerMembers; CFG.GAP_MINIMAL=3; return; var sample = readSibling(');
 const ctx={app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};vm.runInNewContext(code,ctx);
 const a={cx:10,cy:0,w:20,h:10,left:0,right:20,top:5,bottom:-5},b={...a,cx:90,left:80,right:100};
 ctx.distribute([{id:'f',members:['a','b'],memberDistribution:'compact',padding:'minimal'}],[{id:'f',left:0,right:100,w:100,cx:50}],{a,b});
 assert.equal(b.left-a.right,3);assert.equal((a.left+b.right)/2,50);
});
test('final node collision is rejected rather than exported',()=>{
 let code=fs.readFileSync('production-runtime/flowchart/assets/AI流程图生成器.jsx','utf8').replace(/^#target[^\n]*\n/,'');code=code.replace('var sample = readSibling(', 'this.check=assertNodeSeparation;return;var sample = readSibling(');
 const ctx={app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};vm.runInNewContext(code,ctx);
 const a={id:'a',shape:'process',left:0,right:20,top:10,bottom:0};assert.throws(()=>ctx.check([a,{...a,id:'b',left:19,right:39}]),/overlapping nodes/);ctx.check([a,{...a,id:'b',left:23,right:43}]);
});
test('exterior arrow label clears return lane even when node itself does not touch it',()=>{const ctx={JFW:{}};vm.runInNewContext(fs.readFileSync('production-runtime/adobe/editorial-layout.jsx','utf8'),ctx);let dx=0;const t={name:'AI_FLOW_ARROW_LABEL_ext',textRange:{characterAttributes:{size:8}},duplicate:()=>({createOutline:()=>({visibleBounds:[0,20,12,10],remove(){}})}),translate(x){dx=x;}};ctx.JFW.placeExteriorArrowLabels({pathItems:[{name:'AI_FLOW_LINE',visibleBounds:[10,100,11,0]},{name:'AI_FLOW_NODE_ext',visibleBounds:[0,5,30,0]}],textFrames:[t]},[{id:'ext',shape:'arrow',arrowLabelSide:'left'}]);assert.equal(12+dx,7);});
