import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {createHash} from 'node:crypto';
import {intakeFields,createArchiveIntake} from '../workbench/archive-intake.mjs';
import {registerArchiveArticles,syncRelatedReviews} from '../workbench/archive-articles.mjs';
test('intake fields reject traversal and invalid counts',()=>{
 for(const value of ['../a.zip','CON.zip','bad.txt'])assert.throws(()=>intakeFields(new URL('http://localhost/?'+new URLSearchParams({filename:value,month:'11',editor:'Editor',count:'2'}))));
 assert.throws(()=>intakeFields(new URL('http://localhost/?filename=a.zip&month=13&editor=e&count=2')));
});
test('registration preserves other articles, distinguishes same author articles, and is idempotent',()=>{
 const articles=[{id:'existing',state:'全部通过',figures:[{feedback:{text:'keep'}}]}],old=structuredClone(articles[0]);
 const batch={archiveSha256:'abc',editor:'编辑',manuscripts:['A','B'].map(title=>({author:'作者',title,member:title,wordPath:path.resolve(title+'.docx')}))};
 const ctx={articles,link:uri=>({token:String(uri),path:String(uri)}),wordTokens:new Set()};registerArchiveArticles(ctx,batch);registerArchiveArticles(ctx,batch);
 assert.equal(articles.length,3);assert.deepEqual(articles[0],old);assert.notEqual(articles[1].id,articles[2].id);assert.equal(articles[1].state,'未完成');assert.match(articles[2].label,/B/);
});
test('HTTP intake persists, deduplicates across restart and rejects conflicting archives/origins',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'archive-intake-test-')),config={internalRoot:path.join(root,'internal'),deliveryRoot:path.join(root,'delivery'),powershell:'mock',folderScript:'mock'},registered=[];let calls=0;
 const execute=async(exe,args)=>{calls++;const field=key=>args[args.indexOf(key)+1],hash=createHash('sha256').update(fs.readFileSync(field('-Archive'))).digest('hex');fs.writeFileSync(field('-ManifestPath'),JSON.stringify({archiveSha256:hash,articles:2,authors:2,batch:path.join(config.deliveryRoot,'11月-编辑-2篇'),manuscripts:[]}));};
 let handler,origin;const server=http.createServer((req,res)=>handler.handle(req,res,new URL(req.url,origin)));await new Promise(r=>server.listen(0,'127.0.0.1',r));origin='http://127.0.0.1:'+server.address().port;
 t.after(()=>{server.close();fs.rmSync(root,{recursive:true,force:true});});
 const options={root,config,origin,register:b=>registered.push(b),execute};handler=createArchiveIntake(options);
 const url=origin+'/archive-intake?'+new URLSearchParams({filename:'source.zip',month:11,editor:'编辑',count:2}),post=(body,headers={Origin:origin})=>fetch(url,{method:'POST',headers,body});
 assert.equal((await post('abc',{Origin:'http://attacker'})).status,403);
 let res=await post('abc');assert.equal(res.status,200);assert.equal((await res.json()).batch.articles,2);
 res=await post('abc');assert.equal((await res.json()).batch.duplicate,true);assert.equal(calls,1);
 handler=createArchiveIntake(options);res=await post('abc');assert.equal((await res.json()).batch.duplicate,true);assert.equal(calls,1);
 res=await post('different');assert.equal(res.status,400);assert.match((await res.json()).error,/不同原包/);assert.equal(calls,1);assert.equal(registered.length,2);
 assert.deepEqual(fs.readdirSync(path.join(root,'incoming')),[]);
});
test('existing review matches manuscript path and retains cached progress when disconnected',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'archive-review-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const wordPath=path.join(root,'a.docx'),articles=[{archiveHash:'abc',word:{path:wordPath},state:'未完成'},{archiveHash:'abc',word:{path:path.join(root,'b.docx')},state:'未完成'}];
 const server=http.createServer((req,res)=>res.end(JSON.stringify({articles:[{word:{path:wordPath},state:'待核验',figures:[{}]}]})));await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port,cache=path.join(root,'cache.json');
 await syncRelatedReviews(articles,[url],cache);assert.equal(articles[0].state,'待核验');assert.equal(articles[1].state,'未完成');
 await new Promise(r=>server.close(r));articles[0].state='未完成';await syncRelatedReviews(articles,[url],cache);
 assert.equal(articles[0].state,'待核验');assert.match(articles[0].notices[0].text,/暂未连接/);
});
