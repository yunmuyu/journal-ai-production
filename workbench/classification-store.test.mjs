import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {createClassificationStore,createClassificationHandler} from './classification-store.mjs';

function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-classification-test-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const file=path.join(dir,'classification.json');
 const initial={schemaVersion:1,revision:0,cards:[{id:'A-123-F1',author:'作者',number:'1',type:'待辨认',route:'待确认',review:'待复核',note:'',sources:[{path:'原件'}],figureTypes:['待辨认']}]};
 fs.writeFileSync(file,JSON.stringify(initial));return {dir,file,initial,store:createClassificationStore(file)};
}
test('stable identity, exact editable fields, revision and atomic history',t=>{
 const {store,file,initial}=fixture(t);
 const updated=store.save({revision:0,changes:[{id:'A-123-F1',type:'电路/接线图',route:'保留原图换字',review:'用户已调整',note:'保持原接线'}]});
 assert.equal(updated.revision,1);assert.equal(updated.cards[0].id,initial.cards[0].id);assert.deepEqual(updated.cards[0].sources,initial.cards[0].sources);
 assert.equal(updated.history[0].changes.length,4);assert.deepEqual(updated.history[0].changes[0],{id:'A-123-F1',field:'type',previous:'待辨认',next:'电路/接线图'});
 assert.equal(updated.cards[0].updatedAt,updated.updatedAt);assert.deepEqual(store.read(),updated);
 const before=fs.readFileSync(file,'utf8');
 assert.throws(()=>store.save({revision:0,changes:[{id:'A-123-F1',note:'旧版'}]}),e=>e.status===409&&e.revision===1);
 for(const changes of [[{id:'missing',note:'x'}],[{id:'A-123-F1',author:'假作者'}],[{id:'A-123-F1',type:'其他'}],[{id:'A-123-F1',route:'自创路线'}],[{id:'A-123-F1',review:true}],[{id:'A-123-F1',note:'x'},{id:'A-123-F1',note:'y'}],[{id:'A-123-F1',note:'x'.repeat(4001)}],[{id:'A-123-F1'}]])assert.throws(()=>store.save({revision:1,changes}),e=>e.status===400);
 assert.equal(fs.readFileSync(file,'utf8'),before);
 assert.equal(fs.readdirSync(path.dirname(file)).filter(x=>x.endsWith('.tmp')).length,0);
});
test('card count supports other issue sizes beyond 242',t=>{
 const {store,file,initial}=fixture(t);
 initial.cards=Array.from({length:250},(_,i)=>({...initial.cards[0],id:'A-123-F'+(i+1)}));
 fs.writeFileSync(file,JSON.stringify(initial));
 assert.equal(store.save({revision:0,changes:initial.cards.map(c=>({id:c.id,note:'已核'}))}).cards.length,250);
 assert.throws(()=>store.save({revision:1,changes:Array.from({length:251},()=>({id:'A-123-F1',note:'x'}))}),e=>e.status===400&&e.message.includes('当前图件数'));
});
test('HTTP origin, content type, size, conflict and restricted assets',async t=>{
 const {store,dir}=fixture(t);fs.mkdirSync(path.join(dir,'classification-assets','images'),{recursive:true});
 fs.writeFileSync(path.join(dir,'classification.html'),'classification');fs.writeFileSync(path.join(dir,'classification-assets','images','one.png'),'png');
 let handler,origin;
 const server=http.createServer((req,res)=>{if(!handler(req,res,new URL(req.url,origin)))res.writeHead(404).end();});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
 handler=createClassificationHandler({store,origin,assetsDirectory:dir});t.after(()=>new Promise(resolve=>server.close(resolve)));
 const send=(body,headers={})=>fetch(origin+'/classification/data',{method:'POST',headers:{'Content-Type':'application/json',Origin:origin,...headers},body});
 assert.equal((await fetch(origin+'/classification/data')).status,200);
 assert.equal((await fetch(origin+'/classification')).status,200);
 assert.equal((await fetch(origin+'/classification/images/one.png')).status,200);
 assert.equal((await fetch(origin+'/classification/images/..%5Cclassification.html')).status,404);
 assert.equal((await fetch(origin+'/classification/images/%2Fclassification.html')).status,404);
 assert.equal((await send('{}',{Origin:'http://other'})).status,403);
 assert.equal((await send('{}',{'Content-Type':'text/plain'})).status,415);
 assert.equal((await send('{broken')).status,400);
 assert.equal((await send(' '.repeat(2*1024*1024+1))).status,413);
 const body=JSON.stringify({revision:0,changes:[{id:'A-123-F1',note:'saved'}]});
 const responses=await Promise.all([send(body),send(body)]);assert.deepEqual(responses.map(x=>x.status).sort(),[200,409]);
 const saved=await (responses.find(x=>x.status===200)).json();assert.equal(saved.cards[0].note,'saved');assert.equal(saved.revision,1);
});
