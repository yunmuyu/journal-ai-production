import {routeFixture,transportQuality,testRef} from './route-test-fixture.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
import {productionInstructions} from './production-route.mjs';
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function fixture(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'wb-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const source=path.join(root,'source');fs.writeFileSync(source,'source');return {root:path.join(root,'jobs'),input:{key:'pilot',group:'结构图 / 重绘',label:'图1',sources:[{path:source,sha256:hash(source)}],outputNumbers:['1'],productionRoute:routeFixture(root)}};}
test('WorkBuddy claim requires worker, pause handshake, stale lease rejection, retry retains attempts',async t=>{
 const {root,input}=fixture(t);const q=createWorkBuddyQueue({root,publish:()=>{}});q.enqueue(input);q.enqueue(input);assert.equal(q.list().length,1);assert.equal(q.list()[0].state,'queued');assert.equal(q.worker(),null);
 const job=q.claim('WorkBuddy');assert.ok(job.lease);assert.equal(q.claim('second'),null);q.pause(job.id);assert.equal(q.heartbeat(job.id,job.lease).pauseRequested,true);q.acknowledgePause(job.id,job.lease);assert.equal(q.list()[0].state,'paused');assert.throws(()=>q.progress(job.id,job.lease,'late'));
 q.resume(job.id);const next=q.claim('WorkBuddy');assert.equal(next.attempt,2);q.fail(next.id,next.lease,'tool error');q.retry(next.id);assert.equal(q.list()[0].state,'queued');assert.ok(q.events(next.id).some(e=>e.message==='tool error'));
});
test('real returned artifacts activate only after source/path/hash checks; no acceptance',async t=>{
 const {root,input}=fixture(t);let published=0;const q=createWorkBuddyQueue({root,publish:()=>published++,verifyQuality:transportQuality});q.enqueue(input);const j=q.claim('WorkBuddy'),pdf=path.join(j.attemptDir,'out.pdf'),png=path.join(j.attemptDir,'preview.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 const result={quality:{contract:{sha256:'transport-only'}},evidence:'fixture only, not visual approval',outputs:[{number:'1',path:pdf,preview:png,sha256:'bad'}]};await assert.rejects(q.complete(j.id,j.lease,result),/哈希/);assert.equal(published,0);result.outputs[0].sha256=hash(pdf);await q.complete(j.id,j.lease,result);assert.equal(published,1);assert.equal(q.list()[0].state,'ready');assert.equal(q.list()[0].accepted,undefined);assert.equal(q.list()[0].lease,undefined);
});
test('restart and lost heartbeat require explicit stopped confirmation before retry',t=>{
 const {root,input}=fixture(t);let time=0;const q=createWorkBuddyQueue({root,publish:()=>{},now:()=>time});q.enqueue(input);const j=q.claim('WorkBuddy');time=121000;assert.equal(q.list()[0].state,'interrupted');assert.throws(()=>q.retry(j.id),/确认/);q.retry(j.id,true);q.claim('WorkBuddy');const restored=createWorkBuddyQueue({root,publish:()=>{}});assert.equal(restored.list()[0].state,'interrupted');
});
test('slow source inspection can reconnect the same lease without duplicating work',t=>{
 const {root,input}=fixture(t);let time=0;const q=createWorkBuddyQueue({root,publish:()=>{},now:()=>time});q.enqueue(input);const j=q.claim('WorkBuddy');time=121000;assert.equal(q.list()[0].state,'interrupted');assert.equal(q.claim('other'),null);q.heartbeat(j.id,j.lease);assert.equal(q.list()[0].state,'running');assert.equal(q.list()[0].attempt,1);
});
test('blocked inventory stays visible and retryable after the actionable figures are dispatched',async t=>{
 const {root,input}=fixture(t);const q=createWorkBuddyQueue({root,publish:()=>{}});
 q.enqueue({...input,kind:'inventory'});const j=q.claim('WorkBuddy');
 await q.complete(j.id,j.lease,{evidence:'checked',articles:[{articleId:'a',blocked:true,problem:'Word unreadable',figures:[]}]});
 assert.equal(q.list()[0].state,'needs_input');assert.match(q.list()[0].message,/Word unreadable/);
 q.retry(j.id);const next=q.claim('WorkBuddy');assert.equal(next.attempt,2);
 await q.complete(next.id,next.lease,{evidence:'readable now',articles:[{articleId:'a',figures:[]}]});
 assert.equal(q.list()[0].state,'ready');
});

test('legacy queued production without a route is blocked before claim, retaining its evidence',t=>{
 const {root,input}=fixture(t),q=createWorkBuddyQueue({root,publish:()=>{}}),job=q.enqueue(input);
 const file=path.join(root,job.id,'job.json'),legacy=JSON.parse(fs.readFileSync(file,'utf8'));delete legacy.productionRoute;fs.writeFileSync(file,JSON.stringify(legacy));
 const restored=createWorkBuddyQueue({root,publish:()=>{throw Error('must not publish');}});
 assert.equal(restored.claim('new-provider'),null);assert.equal(restored.list()[0].state,'needs_input');
 assert.equal(restored.list()[0].attempt,0);assert.equal(restored.list()[0].key,input.key);
});

test('valid screenshot route rejects old free-form PDF dispatch but retains original revision feedback',t=>{
 const {root,input}=fixture(t);input.productionRoute=routeFixture(path.dirname(root),{raster:true});
 const q=createWorkBuddyQueue({root,publish:()=>{}}),feedback={text:'正文实测低于6pt，请检查原图',annotations:[{text:'这里不能丢'}]};
 assert.throws(()=>q.enqueue({...input,instructions:'截图统一制作PDF，正文低于6pt改双栏'}),/路线合同生成/);
 const job=q.enqueue({...input,feedback,coordinatorDecision:{instructions:'保留原截图内容'}});
 assert.equal(job.instructions,productionInstructions(input.productionRoute));assert.deepEqual(job.feedback,feedback);
 assert.equal(q.claim('WorkBuddy').coordinatorDecision.instructions,'保留原截图内容');
});

test('paused legacy jobs cannot bypass route gating through resume and claim',t=>{
 const {root,input}=fixture(t),q=createWorkBuddyQueue({root,publish:()=>{}}),job=q.enqueue(input);q.pause(job.id);
 const file=path.join(root,job.id,'job.json'),legacy=JSON.parse(fs.readFileSync(file,'utf8'));delete legacy.productionRoute;legacy.instructions='旧PDF模板';fs.writeFileSync(file,JSON.stringify(legacy));
 const restored=createWorkBuddyQueue({root,publish:()=>{throw Error('must not publish');}});restored.resume(job.id);
 assert.equal(restored.claim('any-provider'),null);const blocked=restored.list()[0];assert.equal(blocked.state,'needs_input');assert.equal(blocked.attempt,0);assert.equal(blocked.instructions,'旧PDF模板');assert.equal(blocked.lease,undefined);
});

test('valid PDF bytes and executor completion claim cannot bypass independent quality gate',async t=>{
 const {root,input}=fixture(t);let published=0;const q=createWorkBuddyQueue({root,publish:()=>published++});q.enqueue(input);const j=q.claim('another-agent');
 const pdf=path.join(j.attemptDir,'out.pdf'),png=path.join(j.attemptDir,'preview.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 await assert.rejects(q.complete(j.id,j.lease,{evidence:'AI says everything passed',outputs:[{number:'1',path:pdf,preview:png,sha256:hash(pdf),fontLabel:'字号8 pt'}]}),/独立质量/);
 assert.equal(published,0);assert.equal(q.list()[0].state,'running');
});

test('explicit compatible executor identity survives dispatch and claim',t=>{
 const {root,input}=fixture(t),q=createWorkBuddyQueue({root,publish:()=>{}});
 q.enqueue({...input,executor:'Codex'});const job=q.claim('Codex repair session');
 assert.equal(job.executor,'Codex');assert.match(q.events(job.id).at(-1).message,/Codex/);
});

test('candidate submission releases execution but cannot publish before independent review',async t=>{
 const {root,input}=fixture(t);let published=0;const q=createWorkBuddyQueue({root,publish:()=>published++,verifyQuality:transportQuality});
 q.enqueue(input);q.enqueue({...input,key:'next'});const j=q.claim('producer');
 const pdf=path.join(j.attemptDir,'candidate.pdf'),png=path.join(j.attemptDir,'candidate.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 const candidate={summary:'candidate only',evidence:'producer observations',outputs:[{number:'1',path:pdf,preview:png,sha256:hash(pdf),fontLabel:'字号8 pt'}]};
 q.submitCandidate(j.id,j.lease,candidate);assert.equal(published,0);assert.equal(q.list().find(x=>x.id===j.id).state,'review_pending');
 assert.notEqual(q.claim('producer').id,j.id);assert.throws(()=>q.progress(j.id,j.lease,'late'),/租约/);
 const reviewed={...candidate,quality:{contract:{sha256:'transport-only'}}};
 await assert.rejects(q.reviewCandidate(j.id,{...reviewed,outputs:[{...candidate.outputs[0],sha256:'changed'}]}),/候选/);assert.equal(published,0);
 fs.appendFileSync(pdf,'changed after submission');await assert.rejects(q.reviewCandidate(j.id,reviewed),/哈希/);assert.equal(published,0);
 fs.writeFileSync(pdf,'%PDF-fixture');
 await q.reviewCandidate(j.id,reviewed);assert.equal(published,1);assert.equal(q.list().find(x=>x.id===j.id).state,'ready');
});

test('raster candidate wrapped in PDF is rejected before internal review queue',t=>{
 const {root,input}=fixture(t);input.productionRoute=routeFixture(path.dirname(root),{raster:true});
 const q=createWorkBuddyQueue({root,publish:()=>{throw Error('must not publish');}});q.enqueue(input);const j=q.claim('producer');
 const pdf=path.join(j.attemptDir,'candidate.pdf'),png=path.join(j.attemptDir,'candidate.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 assert.throws(()=>q.submitCandidate(j.id,j.lease,{evidence:'claimed screenshot',outputs:[{number:'1',path:pdf,preview:png,sha256:hash(pdf),fontLabel:''}]}),/JPG/);
 assert.equal(q.list()[0].state,'running');
});

test('independent rejection preserves candidate and reason then retries in a new attempt',t=>{
 const {root,input}=fixture(t),q=createWorkBuddyQueue({root,publish:()=>{throw Error('must not publish');}});q.enqueue(input);const j=q.claim('producer');
 const pdf=path.join(j.attemptDir,'candidate.pdf'),png=path.join(j.attemptDir,'candidate.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 const candidate={evidence:'producer',outputs:[{number:'1',path:pdf,preview:png,sha256:hash(pdf)}]};q.submitCandidate(j.id,j.lease,candidate);
 assert.throws(()=>q.rejectCandidate(j.id,''),/原因/);q.rejectCandidate(j.id,'灰度分类信息丢失');
 assert.equal(q.list()[0].state,'needs_input');assert.equal(q.list()[0].reviewRejections[0].reason,'灰度分类信息丢失');assert.ok(fs.existsSync(path.join(j.attemptDir,'candidate-submission.json')));
 q.retry(j.id);const next=q.claim('producer');assert.equal(next.id,j.id);assert.equal(next.attempt,2);assert.notEqual(next.attemptDir,j.attemptDir);assert.equal(hash(pdf),candidate.outputs[0].sha256);
});
