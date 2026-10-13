import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
for(const file of ['../adobe/illustrator.jsx','../production-runtime/adobe/illustrator.jsx'])test(file+' normalizes only grayscale imported vectors and verifies document mode',()=>{
 const source=fs.readFileSync(new URL(file,import.meta.url),'utf8'),guard=source.match(/if\(p\.grayscale&&doc\.documentColorSpace!==DocumentColorSpace\.RGB\)\{[\s\S]*?throw Error\("Vector grayscale document must be RGB"\);\}/)?.[0];assert.ok(guard,'Imported vector grayscale guard missing');
 function run(grayscale,mode,convert=true){const calls=[],context={p:{grayscale},doc:{documentColorSpace:mode},DocumentColorSpace:{RGB:'RGB'},app:{executeMenuCommand(name){calls.push(name);if(convert)context.doc.documentColorSpace='RGB';}}};vm.createContext(context);vm.runInContext(guard,context);return{calls,mode:context.doc.documentColorSpace};}
 assert.deepEqual(run(true,'CMYK'),{calls:['doc-color-rgb'],mode:'RGB'});assert.deepEqual(run(true,'RGB'),{calls:[],mode:'RGB'});assert.deepEqual(run(false,'CMYK'),{calls:[],mode:'CMYK'});assert.throws(()=>run(true,'CMYK',false),/must be RGB/);
});
