import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {convertOffice} from '../lib/convert.mjs';

test('SVG page selection rejects invalid and non-Visio requests before Office',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-visio-export-'));
 try{
  for(const page of [0,-1,1.5,'1'])assert.throws(()=>convertOffice(root,'missing.vsd',{visioSvg:{page}}),/Invalid.*Visio/);
  assert.throws(()=>convertOffice(root,'missing.pptx',{visioSvg:{page:1}}),/Invalid.*Visio/);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
function execute(selection){
 const calls=[],req={input:'copy.vsdx',directory:'out',result:'result.json',visioSvg:selection};let result,exit;
 const doc={Pages:{Count:3,Item(page){calls.push(['page',page]);return{Name:'Page '+page,Export(file){calls.push(['svg',file]);}}}},ExportAsFixedFormat(...args){calls.push(['pdf',...args]);},Close(){calls.push(['close']);}};
 const app={Documents:{OpenEx(file,flags){calls.push(['open',file,flags]);return doc;}},Quit(){calls.push(['quit']);}};
 const code=fs.readFileSync(new URL('../scripts/convert-office.js',import.meta.url),'utf8');
 vm.runInNewContext(code.slice(code.indexOf('var json=stringify;')),{stringify:JSON.stringify,readUtf8:()=>JSON.stringify(req),writeUtf8:(_,s)=>{result=JSON.parse(s)},ActiveXObject:function(name){assert.equal(name,'Visio.InvisibleApp');return app},fso:{GetExtensionName:()=> 'vsdx',BuildPath:(...a)=>a.join('/'),FileExists:()=>true},WScript:{Arguments:()=>'',Quit:c=>{exit=c}}});
 return{calls,result,exit};
}
test('explicit SVG exports only selected page; default keeps PDF',()=>{
 const svg=execute({page:2});assert.equal(svg.exit,0);assert.equal(svg.result.outputs.length,1);assert.equal(svg.result.outputs[0].kind,'svg');assert.equal(svg.result.outputs[0].page,2);assert.ok(svg.calls.some(x=>x[0]==='svg'));assert.ok(!svg.calls.some(x=>x[0]==='pdf'));
 const pdf=execute(undefined);assert.equal(pdf.result.outputs[0].kind,'pdf');assert.ok(pdf.calls.some(x=>x[0]==='pdf'));
});
test('out-of-range page fails instead of exporting another page',()=>{
 const actual=execute({page:4});assert.equal(actual.exit,1);assert.match(actual.result.error,/page/i);assert.ok(!actual.calls.some(x=>x[0]==='svg'||x[0]==='pdf'));
});
