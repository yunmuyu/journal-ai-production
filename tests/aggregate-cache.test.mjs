import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {cachedAggregate} from '../lib/aggregate-cache.mjs';

function fixture(){
 const root=mkdtempSync(path.join(tmpdir(),'jfw-summary-cache-'));
 const template=path.join(root,'template.ai'),ai=path.join(root,'input.ai');
 writeFileSync(template,'template');writeFileSync(ai,'figure');
 return {root,ai,request:{mode:'aggregate',layout:'template',template,items:[{author:'A',number:'1',ai}]}};
}
function success(counter){return (_app,request)=>{counter.calls++;for(const file of [request.ai,request.pdf,request.preview])writeFileSync(file,'completed '+counter.calls);return {ok:true,groups:['A-图1'],placements:[{page:1}],pages:1};};}

test('unchanged summary inputs skip Adobe and retain artifact paths',()=>{
 const f=fixture(),counter={calls:0};try{const first=cachedAggregate(f.root,f.request,{invoke:success(counter)}),next=cachedAggregate(f.root,f.request,{invoke:success(counter)});assert.equal(counter.calls,1);assert.equal(next.cached,true);assert.equal(next.ai,first.ai);assert.equal(next.key,first.key);}finally{rmSync(f.root,{recursive:true});}
});
test('page layout changes invalidate cached template summaries',()=>{
 const f=fixture(),counter={calls:0};try{const first=cachedAggregate(f.root,f.request,{invoke:success(counter)}),next=cachedAggregate(f.root,{...f.request,layout:'figure-pages',reviewBadges:true,items:f.request.items.map(item=>({...item,columnLabel:'单栏'}))},{invoke:success(counter)});assert.equal(counter.calls,2);assert.notEqual(first.key,next.key);assert.equal(cachedAggregate(f.root,{...f.request,layout:'figure-pages',reviewBadges:true,items:f.request.items.map(item=>({...item,columnLabel:'单栏'}))},{invoke:success(counter)}).cached,true);}finally{rmSync(f.root,{recursive:true});}
});
test('changed source creates a new summary; reverting reuses the prior one',()=>{
 const f=fixture(),counter={calls:0};try{const first=cachedAggregate(f.root,f.request,{invoke:success(counter)});writeFileSync(f.ai,'changed');const next=cachedAggregate(f.root,f.request,{invoke:success(counter)});assert.notEqual(next.key,first.key);assert.notEqual(next.ai,first.ai);writeFileSync(f.ai,'figure');const reverted=cachedAggregate(f.root,f.request,{invoke:success(counter)});assert.equal(counter.calls,2);assert.equal(reverted.ai,first.ai);}finally{rmSync(f.root,{recursive:true});}
});
test('failed aggregation preserves previously successful output and cache',()=>{
 const f=fixture(),counter={calls:0};try{const first=cachedAggregate(f.root,f.request,{invoke:success(counter)}),old=readFileSync(first.ai);writeFileSync(f.ai,'changed');assert.throws(()=>cachedAggregate(f.root,f.request,{invoke(){throw Error('RPC failed');}}),/RPC failed/);assert.deepEqual(readFileSync(first.ai),old);writeFileSync(f.ai,'figure');assert.equal(cachedAggregate(f.root,f.request,{invoke(){throw Error('Must not execute');}}).cached,true);}finally{rmSync(f.root,{recursive:true});}
});
test('tampered cached artifacts require reaggregation',()=>{
 const f=fixture(),counter={calls:0};try{const first=cachedAggregate(f.root,f.request,{invoke:success(counter)});writeFileSync(first.pdf,'tampered');const next=cachedAggregate(f.root,f.request,{invoke:success(counter)});assert.equal(counter.calls,2);assert.notEqual(next.pdf,first.pdf);}finally{rmSync(f.root,{recursive:true});}
});
test('source changing during aggregation is not cached as a completed summary',()=>{
 const f=fixture(),counter={calls:0};try{assert.throws(()=>cachedAggregate(f.root,f.request,{invoke(...args){const result=success(counter)(...args);writeFileSync(f.ai,'concurrent change');return result;}}),/inputs changed/);assert.throws(()=>cachedAggregate(f.root,f.request,{auditOnly:true}),/No verified cached/);}finally{rmSync(f.root,{recursive:true});}
});
