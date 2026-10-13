import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import vm from 'node:vm';
import {repoRoot} from '../scripts/common.mjs';
import {configureWorkbench} from '../scripts/start-workbench.mjs';

test('machine pdfjsRoot resolves externally and passes to workbench environment',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-pdfjs-config-')),file=path.join(root,'machine.json');
 const previous={cwd:process.cwd(),env:{...process.env}};
 t.after(()=>{process.chdir(previous.cwd);for(const k of Object.keys(process.env))if(!(k in previous.env))delete process.env[k];Object.assign(process.env,previous.env);fs.rmSync(root,{recursive:true,force:true});});
 const config={runtimePath:root,workspaceRoot:root,recordRoot:root,pathMapFile:path.join(root,'map.json'),python:process.execPath,flowchartRoot:root,pdfjsRoot:'pdfjs'};
 fs.writeFileSync(file,JSON.stringify(config));configureWorkbench(['--config',file]);
 assert.equal(process.env.JFW_PDFJS_ROOT,path.join(root,'pdfjs'));
 fs.writeFileSync(file,JSON.stringify({...config,pdfjsRoot:42}));assert.throws(()=>configureWorkbench(['--config',file]),/pdfjsRoot/);
});

test('actual server PDFjs route reads configured modules/fonts and refuses traversal',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-pdfjs-route-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.mkdirSync(path.join(root,'build'));fs.mkdirSync(path.join(root,'standard_fonts'));
 fs.writeFileSync(path.join(root,'build/pdf.mjs'),'module-main');fs.writeFileSync(path.join(root,'build/pdf.worker.mjs'),'module-worker');fs.writeFileSync(path.join(root,'standard_fonts/FoxitSerif.pfb'),'font-bytes');
 const source=fs.readFileSync(path.join(repoRoot,'workbench/server.mjs'),'utf8');
 const route=source.split('\n').find(line=>line.includes("if(url.pathname.startsWith('/pdfjs/'))"));assert.ok(route);
 const script=new vm.Script('(function(url,res){'+route+'})');
 const env={JFW_PDFJS_ROOT:root};
 const handler=script.runInNewContext({fs,path,process:{env}});
 const server=http.createServer((req,res)=>handler(new URL(req.url,'http://127.0.0.1'),res));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
 const base='http://127.0.0.1:'+server.address().port;
 for(const [url,expected] of [['pdf.mjs','module-main'],['pdf.worker.mjs','module-worker'],['fonts/FoxitSerif.pfb','font-bytes']]){
  const response=await fetch(base+'/pdfjs/'+url);assert.equal(response.status,200);assert.equal(await response.text(),expected);
 }
 for(const url of ['fonts/..%2Foutside','fonts/missing.pfb','unknown.mjs'])assert.equal((await fetch(base+'/pdfjs/'+url)).status,404);
 if(process.env.JFW_TEST_PDFJS_ROOT){
  env.JFW_PDFJS_ROOT=process.env.JFW_TEST_PDFJS_ROOT;
  const font=fs.readdirSync(path.join(env.JFW_PDFJS_ROOT,'standard_fonts')).find(name=>name.endsWith('.pfb'));
  assert.ok(font);
  for(const [url,relative] of [['pdf.mjs','build/pdf.mjs'],['pdf.worker.mjs','build/pdf.worker.mjs'],['fonts/'+font,'standard_fonts/'+font]]){
   const response=await fetch(base+'/pdfjs/'+url);assert.equal(response.status,200);assert.deepEqual(Buffer.from(await response.arrayBuffer()),fs.readFileSync(path.join(env.JFW_PDFJS_ROOT,relative)));
  }
 }
});
