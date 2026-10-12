import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');
const fn=source.slice(source.indexOf('function addText('),source.indexOf('    function saveOutputs'));
for(const align of ['left','right'])test('Multiline '+align+' labels align each paragraph before measuring ink',()=>{
 const paragraphs=[{paragraphAttributes:{justification:'left'}},{paragraphAttributes:{justification:'left'}}];
 const justification={LEFT:'left',CENTER:'center',RIGHT:'right'};
 let measured=false;
 const tf={paragraphs,textRange:{characterAttributes:{},paragraphAttributes:paragraphs[0].paragraphAttributes},
  duplicate(){for(const p of paragraphs)assert.equal(p.paragraphAttributes.justification,align,'Aligning the outer text box must also align its unequal-length lines');measured=true;return{createOutline:()=>({visibleBounds:[0,0,32,-17],remove(){}})};},translate(){}};
 const context={doc:{textFrames:{length:1,add:()=>tf}},JFW:{editorialFont:()=>({}),bounds:b=>b},gray:()=>0,Justification:justification};
 vm.createContext(context);vm.runInContext(fn,context);
 context.addText({text:'下层处理\r模块1',x:.5,y:.5,align,valign:'center',anchor:'ink'},100,100,8);
 assert.equal(measured,true);assert.equal(tf.contents,'下层处理\r模块1');
});
test('centered multiline labels use independent ink anchors for unequal line lengths',()=>{
 const frames=[];
 const context={doc:{textFrames:{get length(){return frames.length;},add(){
  const tf={paragraphs:[{paragraphAttributes:{}}],textRange:{characterAttributes:{}},left:0,top:0,
   duplicate(){return{createOutline:()=>({visibleBounds:[tf.left,tf.top,tf.left+tf.contents.length*8,tf.top-8],remove(){}})};},
   translate(dx,dy){tf.left+=dx;tf.top+=dy;}};
  frames.push(tf);return tf;
 } }},JFW:{editorialFont:()=>({}),bounds:b=>b},gray:()=>0,Justification:{LEFT:'left',CENTER:'center',RIGHT:'right'}};
 vm.createContext(context);vm.runInContext(fn,context);
 context.addText({text:'下层处理\r模块1',x:.5,y:.5,align:'center',valign:'center'},100,100,8);
 assert.equal(frames.length,2);
 for(const tf of frames)assert.equal(tf.left+tf.contents.length*4,50);
 assert.ok(Math.abs(frames[0].top-frames[1].top-9.6)<1e-8);
});
