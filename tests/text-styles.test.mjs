import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../adobe/vector-labels.jsx',import.meta.url),'utf8');
function setup(text){
 const context={JFW:{},app:{textFonts:{getByName:name=>({name})}}};
 vm.runInNewContext(source,context);
 const tf={contents:text,characters:Array.from(text,()=>({characterAttributes:{textFont:{name:'composite'},size:8}}))};
 return {context,tf};
}
test('local mathematical style leaves numbers and units in the editorial font',()=>{
 const {context,tf}=setup('K=50 dB');
 context.JFW.styleText(tf,[{start:0,length:1,font:'TimesNewRomanPS-ItalicMT'}]);
 assert.deepEqual(tf.characters.map(c=>c.characterAttributes.textFont.name),['TimesNewRomanPS-ItalicMT',...Array(6).fill('composite')]);
 assert.ok(tf.characters.every(c=>c.characterAttributes.size===8));
});
test('numeric subscripts can use upright Times while the variable stays italic',()=>{
 const {context,tf}=setup('x₁');
 context.JFW.styleText(tf,[{start:0,length:1,font:'TimesNewRomanPS-ItalicMT'},{start:1,length:1,font:'TimesNewRomanPSMT'}]);
 assert.deepEqual(tf.characters.map(c=>c.characterAttributes.textFont.name),['TimesNewRomanPS-ItalicMT','TimesNewRomanPSMT']);
});
test('invalid ranges and overlapping styles reject before mutation',()=>{
 for(const styles of [[{start:1,length:9,font:'TimesNewRomanPS-ItalicMT'}],[{start:0,length:2,font:'TimesNewRomanPS-ItalicMT'},{start:1,length:1,font:'TimesNewRomanPS-ItalicMT'}]]){
  const {context,tf}=setup('K=50');
  assert.throws(()=>context.JFW.styleText(tf,styles));
  assert.ok(tf.characters.every(c=>c.characterAttributes.textFont.name==='composite'));
 }
});

test('ink anchor is measured after styling rather than using font advance width',()=>{
 const driver=fs.readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');
 const fn=driver.slice(driver.indexOf('function addText('),driver.indexOf('    function saveOutputs'));
 let translated;const tf={paragraphs:[{paragraphAttributes:{}}],textRange:{characterAttributes:{},paragraphAttributes:{}},duplicate(){return {createOutline(){return {visibleBounds:[12,-10,25,-18],remove(){}};}};},translate(dx,dy){translated=[dx,dy];}};
 const context={doc:{textFrames:{length:1,add:()=>tf}},JFW:{editorialFont:()=>({}),bounds:b=>b},gray:()=>0,Justification:{LEFT:"left",CENTER:"center",RIGHT:"right"}};vm.createContext(context);vm.runInContext(fn,context);
 context.addText({text:'K=50',x:.5,y:.5,align:'left',anchor:'ink'},100,100,8);
 assert.deepEqual(translated,[38,0]);
});
