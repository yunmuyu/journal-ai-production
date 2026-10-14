import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {validatePlan} from '../lib/core.mjs';
test('positive-y SVG artboard normalizes without scaling the source curve',()=>{
 const source=fs.readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');
 const fn=source.slice(source.indexOf('function normalizeVector('),source.indexOf('    function imageBackground'));
 const layer={pageItems:[]},item={parent:layer,geometricBounds:[35,180,200,20],resize(x,y){assert.equal(x,100);assert.equal(y,100);},translate(x,y){this.geometricBounds=this.geometricBounds.map((v,i)=>v+(i%2?y:x));}};
 layer.pageItems.push(item);const doc={layers:[layer],artboards:[{artboardRect:[0,200,250,0]}]},ctx={doc};vm.createContext(ctx);vm.runInContext(fn,ctx);
 assert.equal(ctx.normalizeVector(250,doc.artboards[0].artboardRect),1);
 assert.deepEqual(item.geometricBounds,[35,-20,200,-180]);
 assert.deepEqual(Array.from(doc.artboards[0].artboardRect),[0,0,250,-200]);
});
test('native SVG option rejects nonboolean and nonvector plans',()=>{
 const p={version:1,figureId:'ftest',sourceHash:'a'.repeat(64),route:'vector-reletter',widthMm:80,fontSize:8,replacements:[]};
 assert.equal(validatePlan({...p,nativeSvg:true}).nativeSvg,true);
 assert.throws(()=>validatePlan({...p,nativeSvg:'yes'}),/nativeSvg/);
 assert.throws(()=>validatePlan({...p,route:'image',nativeSvg:true}),/nativeSvg/);
});
test('PDF overlay plans normalize a nonzero artboard before taking the geometry baseline',()=>{
 const source=fs.readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');
 const branch=source.slice(source.indexOf('doc=app.open(new File(req.input));if(p.grayscale'),source.indexOf('before=snapshot(doc);'));
 for(const overlay of [{texts:[{}]},{masks:[{}]},{lineSamples:[{}]}]){
  const doc={artboards:[{artboardRect:[12,137,237,0]}]},calls=[];
  const ctx={p:overlay,req:{input:'source.pdf'},File:function(value){return value;},app:{open(){return doc;}},normalizeVector(w,b){calls.push([w,Array.from(b)]);doc.artboards[0].artboardRect=[0,0,w,-137];}};
  vm.runInNewContext(branch,ctx);
  assert.deepEqual(calls,[[225,[12,137,237,0]]]);
  assert.deepEqual(doc.artboards[0].artboardRect,[0,0,225,-137]);
 }
});
