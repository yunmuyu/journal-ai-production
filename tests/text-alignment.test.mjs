import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
test('Relettering centers visible glyphs rather than the font advance box',()=>{
 const source=readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');
 const fn=source.slice(source.indexOf('function addText('),source.indexOf('    function saveOutputs'));
 let removed=false,translation;
 const tf={paragraphs:[{paragraphAttributes:{}}],textRange:{characterAttributes:{},paragraphAttributes:{}},duplicate(){return{createOutline(){return{visibleBounds:[8,-10,24,-18],remove(){removed=true;}};}};},translate(x,y){translation=[x,y];}};
 const context={doc:{textFrames:{length:1,add:()=>tf}},JFW:{editorialFont:()=>({}),bounds:b=>b},gray:()=>0,Justification:{LEFT:"left",CENTER:"center",RIGHT:"right"}};
 vm.createContext(context);vm.runInContext(fn,context);
 context.addText({text:'原料制备',x:.5,y:.5,align:'center',valign:'center'},100,100);
 assert.deepEqual(translation,[34,-36]);assert.equal(removed,true);assert.equal(tf.contents,'原料制备');
});
