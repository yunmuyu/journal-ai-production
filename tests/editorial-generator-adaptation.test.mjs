import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../production-runtime/flowchart/assets/AI流程图生成器.jsx',import.meta.url),'utf8');
for(const location of ['adobe','production-runtime/adobe']){
 function adapt(code,metrics={padX:4.5,padY:2.7}){const c={JFW:{layoutMetrics:metrics}};vm.runInNewContext(fs.readFileSync(new URL('../'+location+'/editorial-generator.jsx',import.meta.url),'utf8'),c);return c.JFW.adaptEditorialGenerator(code);}
 test(location+' adapts the real generator with bounded text-first rectangle dimensions',()=>{const c={JFW:{},app:{documents:[{}],activeDocument:{activeLayer:{locked:false,visible:true}}}};vm.runInNewContext(fs.readFileSync(new URL('../'+location+'/editorial-generator.jsx',import.meta.url),'utf8'),c);const code=c.JFW.adaptEditorialGenerator(source).replace(/^#target[^\n]*\n/,'').replace('var sample = readSibling(', 'this.size=calibratedBoxSize; return; var sample = readSibling(');vm.runInNewContext(code,c);const box=c.size({shape:'process',text:'test'},{w:40,h:8},8);assert.equal(box.w,49);assert.equal(box.h,13.4);assert.equal(typeof c.JFW.reserveContainerColumns,'function');assert.equal(typeof c.JFW.editorialArrowSymbol,'function');});
 test(location+' accepts uniquely declared equivalent padding formatting',()=>{const result=adapt(source.replace('PAD_X: 4.5,','PAD_X : 4.50,').replace('PAD_Y: 2.7,','PAD_Y: 2.70,'));assert.match(result,/PAD_X: 4\.5,/);assert.match(result,/PAD_Y: 2\.7,/);});
 test(location+' accepts uniquely declared padding already at requested target',()=>{const result=adapt(source.replace('PAD_X: 4.5,','PAD_X: 3,').replace('PAD_Y: 2.7,','PAD_Y: 2,'),{padX:3,padY:2});assert.match(result,/PAD_X: 3,/);assert.match(result,/PAD_Y: 2,/);});
 test(location+' rejects missing duplicate or unknown padding boundaries',()=>{for(const code of [source.replace('PAD_X: 4.5,','PAD_XX: 4.5,'),source.replace('PAD_X: 4.5,','PAD_X: 4.5, PAD_X: 4.5,'),source.replace('PAD_X: 4.5,','PAD_X: 19,')])assert.throws(()=>adapt(code),/Generator adaptation boundary changed: PAD_X/);});
}
