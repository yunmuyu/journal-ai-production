import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {runRasterBatch} from './raster-batch.mjs';

test('raster batch stops a confirmed redraw before preparation while another item continues',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'route-guard-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const put=(name,value)=>{const p=path.join(dir,name);fs.writeFileSync(p,JSON.stringify(value));return p;};
 const route=put('route.json',{method:'raster-preserve',processing:{operation:'preserve',basis:'fixture'}});
 const config=put('config.json',{origin:'http://fixture',workerToken:'fixture'});
 const manifest=put('batch.json',{version:1,concurrency:2,items:[
  {id:'a',figureId:'A',routeFile:route,outputName:'a.jpg'},
  {id:'b',figureId:'B',routeFile:route,outputName:'b.jpg'}]});
 const original=globalThis.fetch;const posts=[];
 t.after(()=>{globalThis.fetch=original;});
 globalThis.fetch=async (url,options)=>{
  if(String(url).endsWith('/data'))return new Response(JSON.stringify({rows:[
   {id:'A',decision:{attributes:{method:{state:'confirmed',value:'完整重绘'}}}},
   {id:'B',decision:{attributes:{method:{state:'confirmed',value:'PS直出'}}}}]}));
  posts.push(JSON.parse(options.body).id);return new Response(JSON.stringify({error:'fixture stop'}),{status:409});
 };
 const result=await runRasterBatch(config,manifest);
 assert.match(result.results.find(r=>r.id==='a').error,/confirmed_route_conflict/);
 assert.match(result.results.find(r=>r.id==='b').error,/fixture stop/);
 assert.deepEqual(posts,['b']);
});

test('raster batch rejects a live chart before POST and still processes a photo',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'chart-route-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const put=(name,value)=>{const p=path.join(dir,name);fs.writeFileSync(p,JSON.stringify(value));return p;};
 const route=put('route.json',{method:'raster-preserve',processing:{operation:'preserve',basis:'fixture'}});
 const config=put('config.json',{origin:'http://fixture',workerToken:'fixture'});
 const manifest=put('batch.json',{version:1,concurrency:2,items:[{id:'a',figureId:'A',routeFile:route,outputName:'a.jpg'},{id:'b',figureId:'B',routeFile:route,outputName:'b.jpg'}]});
 const original=globalThis.fetch;const posts=[];t.after(()=>{globalThis.fetch=original;});
 globalThis.fetch=async(url,options)=>{
  if(String(url).endsWith('/data'))return new Response(JSON.stringify({rows:[{id:'A',type:'统计曲线图'},{id:'B',type:'截图照片'}]}));
  posts.push(JSON.parse(options.body).id);return new Response(JSON.stringify({error:'fixture stop'}),{status:409});
 };
 const result=await runRasterBatch(config,manifest);
 assert.match(result.results.find(r=>r.id==='a').error,/chart_preserve_conflict/);
 assert.deepEqual(posts,['b']);
});

test('unresolvable legacy task identity stops before any preparation',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'route-identity-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const put=(name,value)=>{const p=path.join(dir,name);fs.writeFileSync(p,JSON.stringify(value));return p;};
 const route=put('route.json',{method:'raster-preserve',processing:{operation:'preserve',basis:'fixture'}});
 const config=put('config.json',{origin:'http://fixture',workerToken:'fixture'});
 const manifest=put('batch.json',{version:1,items:[{id:'old',routeFile:route,outputName:'a.jpg'}]});
 const original=globalThis.fetch;t.after(()=>{globalThis.fetch=original;});let posted=false;
 globalThis.fetch=async (url,options)=>{
  if(options?.method==='POST')posted=true;
  return new Response(JSON.stringify({jobs:[{id:'old'}]}));
 };
 const result=await runRasterBatch(config,manifest);
 assert.match(result.results[0].error,/Task figure identity missing/);
 assert.equal(posted,false);
});

test('legacy task resolves a unique article and figure number before admission',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'route-legacy-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const put=(name,value)=>{const p=path.join(dir,name);fs.writeFileSync(p,JSON.stringify(value));return p;};
 const route=put('route.json',{method:'raster-preserve',processing:{operation:'preserve',basis:'fixture'}});
 const config=put('config.json',{origin:'http://fixture',workerToken:'fixture'});
 const manifest=put('batch.json',{version:1,items:[{id:'old',routeFile:route,outputName:'a.jpg'}]});
 const original=globalThis.fetch;t.after(()=>{globalThis.fetch=original;});let posted=false;
 globalThis.fetch=async (url,options)=>{
  if(String(url).endsWith('/workbuddy/status'))return new Response(JSON.stringify({jobs:[{id:'old',articleId:'article',figureNumber:'1'}]}));
  if(String(url).endsWith('/data'))return new Response(JSON.stringify({rows:[{id:'F1',articleId:'article',number:'1'}]}));
  posted=true;return new Response(JSON.stringify({error:'fixture stop'}),{status:409});
 };
 const result=await runRasterBatch(config,manifest);
 assert.match(result.results[0].error,/fixture stop/);
 assert.equal(posted,true);
});
