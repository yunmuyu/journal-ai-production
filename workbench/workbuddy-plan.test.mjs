import test from 'node:test';
import assert from 'node:assert/strict';
import {buildFigureTasks} from './workbuddy-plan.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {routeFixture} from './route-test-fixture.mjs';
function setup(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'wb-plan-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const route=routeFixture(root),ref=route.sourceReview.selected;
 const catalog={batchHash:'batch',articles:[{id:'a',author:'A',word:ref},{id:'b',author:'B',word:ref}],archive:ref,groups:['graph','photo'],completedKeys:['batch:a:1'],productionInstructions:''};
 const figure=(number,group)=>({number,group,outputNumbers:[number],productionRoute:routeFixture(root,{raster:group==='photo'}),evidence:'source pairing fixture'});
 const plan=()=>({articles:[{articleId:'a',evidence:'captions fixture',figures:[figure('1','graph'),figure('2','photo')]},{articleId:'b',evidence:'captions fixture',figures:[figure('1','graph')]}]});
 return {catalog,plan};
}
test('retains figure-level type and article identity, skips completed pilot',t=>{
 const {catalog,plan}=setup(t);
 const tasks=buildFigureTasks(catalog,plan());
 assert.deepEqual(tasks.map(t=>[t.articleId,t.figureNumber,t.group]),[['a','2','photo'],['b','1','graph']]);
 assert.deepEqual(tasks[0].sources,[catalog.articles[0].word]);
 assert.match(tasks[0].instructions,/交付JPG/);assert.match(tasks[1].instructions,/交付PDF/);
});
test('rejects missing or duplicate article identities',t=>{
 const {catalog,plan}=setup(t);
 const p=plan();p.articles.pop();assert.throws(()=>buildFigureTasks(catalog,p));
 p.articles.push(p.articles[0]);assert.throws(()=>buildFigureTasks(catalog,p));
});
test('blocked article never becomes a guessed no-figure completion',t=>{
 const {catalog,plan}=setup(t);
 const p=plan();p.articles[1].figures=[];assert.throws(()=>buildFigureTasks(catalog,p));
 Object.assign(p.articles[1],{blocked:true,problem:'source unreadable'});
 assert.equal(buildFigureTasks(catalog,p).length,1);
});
test('rejects output numbered as a different main figure',t=>{
 const {catalog,plan}=setup(t);
 const p=plan();p.articles[0].figures[1].outputNumbers=['1'];
 assert.throws(()=>buildFigureTasks(catalog,p));
});
test('old generic PDF/font dispatch template is rejected even for a correct raster route',t=>{
 const {catalog,plan}=setup(t);catalog.productionInstructions='PDF四边2pt；8pt先紧凑布局，必要时7/6pt，双栏需单栏不可行证据';
 assert.throws(()=>buildFigureTasks(catalog,plan()),/旧通用派单/);
});
