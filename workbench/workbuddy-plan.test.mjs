import test from 'node:test';
import assert from 'node:assert/strict';
import {buildFigureTasks} from './workbuddy-plan.mjs';
const catalog={batchHash:'batch',articles:[{id:'a',author:'A',word:{path:'a.docx',sha256:'a'}},{id:'b',author:'B',word:{path:'b.docx',sha256:'b'}}],archive:{path:'source.zip',sha256:'z'},groups:['graph','photo'],completedKeys:['batch:a:1'],productionInstructions:'fixture'};
const figure=(number,group)=>({number,group,outputNumbers:[number],evidence:'source pairing fixture'});
const plan=()=>({articles:[{articleId:'a',evidence:'captions fixture',figures:[figure('1','graph'),figure('2','photo')]},{articleId:'b',evidence:'captions fixture',figures:[figure('1','graph')]}]});
test('retains figure-level type and article identity, skips completed pilot',()=>{
 const tasks=buildFigureTasks(catalog,plan());
 assert.deepEqual(tasks.map(t=>[t.articleId,t.figureNumber,t.group]),[['a','2','photo'],['b','1','graph']]);
 assert.deepEqual(tasks[0].sources,[catalog.articles[0].word,catalog.archive]);
});
test('rejects missing or duplicate article identities',()=>{
 const p=plan();p.articles.pop();assert.throws(()=>buildFigureTasks(catalog,p));
 p.articles.push(p.articles[0]);assert.throws(()=>buildFigureTasks(catalog,p));
});
test('blocked article never becomes a guessed no-figure completion',()=>{
 const p=plan();p.articles[1].figures=[];assert.throws(()=>buildFigureTasks(catalog,p));
 Object.assign(p.articles[1],{blocked:true,problem:'source unreadable'});
 assert.equal(buildFigureTasks(catalog,p).length,1);
});
test('rejects output numbered as a different main figure',()=>{
 const p=plan();p.articles[0].figures[1].outputNumbers=['1'];
 assert.throws(()=>buildFigureTasks(catalog,p));
});
