import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
test('SVG inspection uses the browser PDF before Illustrator opens it',()=>{
 const source=fs.readFileSync(new URL('../lib/render.mjs',import.meta.url),'utf8');const fn=source.slice(source.indexOf('export function inspect(')).replace('export function','function');let conversion=0,opened;
 const c={readJson:()=>({figures:[{id:'x',source:'sources/x.SVG'}]}),path:{join:(...p)=>p.join('/'),resolve:(...p)=>p.join('/'),extname:()=>'.SVG'},resolveInside:(a,b)=>a+'/'+b,mkdirSync(){},copyFileSync(){},convertSvg:(root,input)=>{conversion++;return {outputs:[{path:'/converted.pdf'}]};},adobe:(app,req)=>{opened=req.input;}};
 vm.runInNewContext(fn+';inspect("/job","x");',c);assert.equal(conversion,1);assert.equal(opened,'/converted.pdf');
});
