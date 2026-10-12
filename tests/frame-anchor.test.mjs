import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import {validatePlan} from '../lib/core.mjs';
const code=fs.readFileSync(new URL('../adobe/vector-labels.jsx',import.meta.url),'utf8');
function plan(anchor){return {version:1,figureId:'fanchor',sourceHash:'a'.repeat(64),route:'vector-reletter',fontSize:8,widthMm:79.5,replacements:[],textGroups:[{indices:[0],expected:['Original'],text:'Large\rSmall',align:'center',frameAnchorPt:anchor}]};}
function runtime(){const context={app:{textFonts:{getByName:name=>({name})}},JFW:{editorialFont:()=>({name:'composite'})},Justification:{CENTER:'center'},RGBColor:function(){}};vm.createContext(context);vm.runInContext(code,context);return context.JFW;}
test('Invalid target frame coordinates fail at contract boundary',()=>{assert.throws(()=>validatePlan(plan([20,30,10,0])),/frame anchor/);assert.throws(()=>validatePlan(plan([0,30,20,NaN])),/frame anchor/);});
test('Declared frame in normalized Illustrator points accepts negative Y',()=>assert.equal(validatePlan(plan([25,-28,68,-75])).textGroups[0].frameAnchorPt[1],-28));
test('Multiline actual ink union centers in the target frame, independent of original fragments',()=>{
 const targets=[],refs=[{contents:'Original',geometricBounds:[0,30,10,0],remove(){}}];
 refs.add=()=>{const target={dx:0,dy:0,textRange:{characterAttributes:{},paragraphAttributes:{}},duplicate(){return {createOutline:()=>{const height=this.contents==='Large'?10:2,width=this.contents==='Large'?30:10;return {visibleBounds:[this.dx,10+this.dy,this.dx+width,10-height+this.dy],remove(){}};}};},translate(dx,dy){this.dx+=dx;this.dy+=dy;}};targets.push(target);return target;};
 runtime().reletterGroups({textFrames:refs},plan([20,40,80,0]).textGroups,8);
 const outlines=targets.map(t=>t.duplicate().createOutline().visibleBounds),left=Math.min(...outlines.map(b=>b[0])),right=Math.max(...outlines.map(b=>b[2])),top=Math.max(...outlines.map(b=>b[1])),bottom=Math.min(...outlines.map(b=>b[3]));
 assert.ok(Math.abs((left+right)/2-50)<1e-9);assert.ok(Math.abs((top+bottom)/2-20)<1e-9);
 assert.ok(Math.abs((targets[0].dy+5)-(targets[1].dy+9)-9.6)<1e-9);
});
test('Invalid frame anchor in a later group fails before any mutation',()=>{
 let changes=0;const refs=[{contents:'a',duplicate(){changes++;}},{contents:'b'}];
 assert.throws(()=>runtime().reletterGroups({textFrames:refs},[{indices:[0],expected:['a'],text:'a'},{indices:[1],expected:['b'],text:'b',frameAnchorPt:[0,0,0,0]}]),/frame anchor/);assert.equal(changes,0);
});
