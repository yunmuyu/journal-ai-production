import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
function api(){
 const ctx={JFW:{},app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('production-runtime/adobe/editorial-generator.jsx','utf8'),ctx);
 let code=ctx.JFW.adaptEditorialGenerator(fs.readFileSync('production-runtime/flowchart/assets/AI流程图生成器.jsx','utf8')).replace(/^#target[^\n]*\n/,'');
 code=code.replace('var sample = readSibling(', 'var calls=[];this.api={measure:measureLayout,position:positionLayout,draw:drawNodes,calls:calls};drawArrowSymbol=function(){};createText=function(text,x,y){calls.push({text:text,x:x,y:y});return {};};measureContainerTitle=measureText=function(text){var lines=text.split(String.fromCharCode(13));return {w:Math.max.apply(null,lines.map(function(t){return t.length*8;})),h:lines.length*8};};return;var sample = readSibling(');
 vm.runInContext(code,ctx);return {...ctx.api,JFW:ctx.JFW};
}
const node=(id,row,column,shape='process')=>({id,row,column,shape,text:'模块',arrowDirection:shape==='arrow'?'down':undefined});
test('arrow label and symbol occupy one compact block fully enclosed by its container',()=>{
 const a=api(),layout=a.measure({nodes:[{...node('layer',0,0,'arrow'),text:'数据\n输入层'}],edges:[],containers:[{id:'band',members:['layer'],padding:'minimal'}]},8,{});
 a.position(layout,[0,300,300,0]);const n=layout.byId.layer,frame=layout.containers[0];
 assert.ok(n.w>=24,'three-character label must reserve column width');
 assert.equal(layout.rowH[0],n.h,'label height must not be counted twice');
 const symbol=a.JFW.editorialArrowSymbol(n);assert.ok(symbol.w<n.w,'label reserve must not stretch the narrow arrow');
 assert.equal(symbol.bottom,n.bottom);assert.ok(n.top-symbol.top>=19,'label ink and gap stay above symbol');
 a.draw([n],{},null,null,[],8,{});const label=a.calls[0];assert.equal(label.y+8,n.top,'drawn label must stay inside measured block');
 assert.ok(frame.left<=n.left-2.8&&frame.top>=n.top+2.8,'frame encloses full label footprint');
});
test('adjacent disjoint containers reserve both frame pads and a visible gap',()=>{
 const a=api(),layout=a.measure({layoutMode:'compact',nodes:[node('a',0,0),node('b',0,1)],edges:[],containers:[{id:'left',members:['a'],padding:'minimal'},{id:'right',members:['b'],padding:'minimal'}]},8,{});
 a.position(layout,[0,300,300,0]);assert.ok(layout.containers[1].left-layout.containers[0].right>=3-1e-8,'adjacent frames must not touch or overlap');
});
test('explicit exterior arrow labels retain their existing dimensions',()=>{
 const a=api(),layout=a.measure({nodes:[{...node('a',0,0,'arrow'),arrowLabelSide:'left'}],edges:[]},8,{}),n=layout.byId.a;
 assert.equal(n.arrowSymbol,undefined);assert.equal(a.JFW.editorialArrowSymbol(n),n);
});
