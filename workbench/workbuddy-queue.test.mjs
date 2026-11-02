import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function fixture(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),'wb-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const source=path.join(root,'source');fs.writeFileSync(source,'source');return {root:path.join(root,'jobs'),input:{key:'pilot',group:'结构图 / 重绘',label:'图1',sources:[{path:source,sha256:hash(source)}],outputNumbers:['1']}};}
test('WorkBuddy claim requires worker, pause handshake, stale lease rejection, retry retains attempts',async t=>{
 const {root,input}=fixture(t);const q=createWorkBuddyQueue({root,publish:()=>{}});q.enqueue(input);q.enqueue(input);assert.equal(q.list().length,1);assert.equal(q.list()[0].state,'queued');assert.equal(q.worker(),null);
 const job=q.claim('WorkBuddy');assert.ok(job.lease);assert.equal(q.claim('second'),null);q.pause(job.id);assert.equal(q.heartbeat(job.id,job.lease).pauseRequested,true);q.acknowledgePause(job.id,job.lease);assert.equal(q.list()[0].state,'paused');assert.throws(()=>q.progress(job.id,job.lease,'late'));
 q.resume(job.id);const next=q.claim('WorkBuddy');assert.equal(next.attempt,2);q.fail(next.id,next.lease,'tool error');q.retry(next.id);assert.equal(q.list()[0].state,'queued');assert.ok(q.events(next.id).some(e=>e.message==='tool error'));
});
test('real returned artifacts activate only after source/path/hash checks; no acceptance',async t=>{
 const {root,input}=fixture(t);let published=0;const q=createWorkBuddyQueue({root,publish:()=>published++});q.enqueue(input);const j=q.claim('WorkBuddy'),pdf=path.join(j.attemptDir,'out.pdf'),png=path.join(j.attemptDir,'preview.png');fs.writeFileSync(pdf,'%PDF-fixture');fs.writeFileSync(png,Buffer.from([137,80,78,71,13,10,26,10]));
 const result={evidence:'fixture only, not visual approval',outputs:[{number:'1',path:pdf,preview:png,sha256:'bad'}]};await assert.rejects(q.complete(j.id,j.lease,result),/哈希/);assert.equal(published,0);result.outputs[0].sha256=hash(pdf);await q.complete(j.id,j.lease,result);assert.equal(published,1);assert.equal(q.list()[0].state,'ready');assert.equal(q.list()[0].accepted,undefined);assert.equal(q.list()[0].lease,undefined);
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
