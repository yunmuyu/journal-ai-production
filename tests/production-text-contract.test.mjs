import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {validatePlan} from '../production-runtime/lib/core.mjs';

const labels=readFileSync(new URL('../production-runtime/adobe/vector-labels.jsx',import.meta.url),'utf8');
const driver=readFileSync(new URL('../production-runtime/adobe/illustrator.jsx',import.meta.url),'utf8');
const italic={start:0,length:1,font:'TimesNewRomanPS-ItalicMT'};
const sub={start:1,length:1,font:'TimesNewRomanPSMT',script:'subscript'};
const base=()=>({version:1,figureId:'f_text',sourceHash:'a'.repeat(64),route:'vector-reletter',widthMm:80,fontSize:8,replacements:[]});
function context(){
 const ctx={JFW:{editorialFont:()=>({name:'composite'}),bounds:b=>b},app:{textFonts:{getByName:name=>({name})}},FontBaselineOption:{SUBSCRIPT:'native-sub',SUPERSCRIPT:'native-super'},RGBColor:function(){this.red=this.green=this.blue=255;},Justification:{CENTER:'center',LEFT:'left',RIGHT:'right'}};
 vm.createContext(ctx);vm.runInContext(labels,ctx);return ctx;
}
function frame(text){
 const tf={contents:text,geometricBounds:[0,10,20,0],textRange:{characterAttributes:{},paragraphAttributes:{}},characters:[],duplicate(){return {createOutline:()=>({visibleBounds:[0,8,20,0],remove(){}})};},translate(){},remove(){}};
 Object.defineProperty(tf,'contents',{get(){return this.value;},set(value){this.value=value;this.characters=Array.from(value,character=>({contents:character,characterAttributes:{size:8}}));}});
 tf.contents=text;return tf;
}
test('production plan validates styles on overlays, groups and replacements',()=>{
 const p=base();p.texts=[{text:'X1',x:.5,y:.5,styles:[italic,sub]}];p.textGroups=[{text:'X1',styles:[italic,sub]}];p.replacements=[{index:0,expected:'old',text:'X1',styles:[italic,sub]}];
 assert.doesNotThrow(()=>validatePlan(p));
 for(const field of ['texts','textGroups','replacements']){
  const bad=structuredClone(p);bad[field][0].styles[1].script='unknown';
  assert.throws(()=>validatePlan(bad),/local text style/);
  const unknown=structuredClone(p);unknown[field][0].styles[0].invented=true;
  assert.throws(()=>validatePlan(unknown),/local text style/);
 }
 const gray=base();gray.texts=[{text:'label',x:.5,y:.5,gray:40}];
 assert.throws(()=>validatePlan(gray),/pure black/);
});
test('production grouped text receives native script and black fill even without grayscale flag',()=>{
 const ctx=context(),source=frame('old'),target=frame('');
 source.duplicate=()=>target;
 const refs=[source];refs.add=()=>target;
 ctx.JFW.reletterGroups({textFrames:refs},[{indices:[0],expected:['old'],text:'X1',styles:[italic,sub]}],8);
 assert.equal(target.characters[1].characterAttributes.baselinePosition,'native-sub');
 assert.equal(target.characters[0].characterAttributes.textFont.name,'TimesNewRomanPS-ItalicMT');
 assert.equal(target.textRange.characterAttributes.fillColor.red,0);
 assert.equal(target.note,'JFW_STYLED_TEXT');
});
test('production overlay text uses the same native style and black fill',()=>{
 const ctx=context(),tf=frame('');
 tf.paragraphs=[{paragraphAttributes:{}}];
 ctx.doc={textFrames:{length:0,add:()=>tf}};
 ctx.gray=value=>({red:value,green:value,blue:value});
 const start=driver.indexOf('function addText(');
 const end=driver.indexOf('    function applyOverlays',start);
 vm.runInContext(driver.slice(start,end),ctx);
 ctx.addText({text:'X1',x:.5,y:.5,styles:[italic,sub]},100,100,8);
 assert.equal(tf.textRange.characterAttributes.fillColor.red,0);
 assert.equal(tf.characters[1].characterAttributes.baselinePosition,'native-sub');
});
test('production replacement applies styles and resets inherited color to black',()=>{
 const ctx=context(),tf=frame('old');tf.textRange.characterAttributes.fillColor={red:255};
 ctx.doc={textFrames:[tf]};ctx.p={fontSize:8,replacements:[{index:0,expected:'old',text:'X1',styles:[italic,sub]}]};
 ctx.gray=value=>({red:value,green:value,blue:value});
 const start=driver.indexOf('for(var ri=0;ri<p.replacements.length;ri++)');
 const end=driver.indexOf('\n            }else{',start);
 assert.ok(start>0&&end>start);
 vm.runInContext(driver.slice(start,end),ctx);
 assert.equal(tf.textRange.characterAttributes.fillColor.red,0);
 assert.equal(tf.characters[1].characterAttributes.baselinePosition,'native-sub');
 assert.equal(tf.note,'JFW_STYLED_TEXT');
});
test('production snapshot reports native baseline position for styled characters',()=>{
 const start=driver.indexOf('function snapshot(d)');
 const end=driver.indexOf('    function geometryPreserved',start);
 const ctx=context(),tf=frame('X1');
 tf.note='JFW_STYLED_TEXT';tf.characters[1].characterAttributes.baselinePosition='native-sub';
 tf.characters.forEach(c=>{c.characterAttributes.textFont={name:'TimesNewRomanPSMT',family:'Times'};c.characterAttributes.size=8;});
 tf.textRange.characterAttributes.textFont={name:'composite',family:'Song'};tf.textRange.characterAttributes.size=8;tf.name='test';
 ctx.JFW.bounds=b=>b;
 vm.runInContext(driver.slice(start,end),ctx);
 const result=ctx.snapshot({pageItems:[],textFrames:[tf],pathItems:[],artboards:[{artboardRect:[0,0,20,-10]}]});
 assert.equal(result.texts[0].characterStyles[1].baselinePosition,'native-sub');
});
