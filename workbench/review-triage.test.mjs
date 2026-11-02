import {routeFixture,transportQuality,testRef} from './route-test-fixture.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createReviewTriage} from './review-triage.mjs';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
function setup(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'review-triage-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const pdf=path.join(root,'current.pdf');fs.writeFileSync(pdf,'%PDF-fixture');
 const f={productionRoute:routeFixture(root),id:'A-F1',articleId:'A',author:'fixture',number:'1',reviewVersion:'v1',feedback:{text:'equal widths',revision:1},outputs:[{number:'1',file:{path:pdf}}]};let activated=0;
 const queue=createWorkBuddyQueue({root:path.join(root,'queue'),publish:()=>{}});
 const options={root:path.join(root,'triage'),origin:'http://127.0.0.1',token:'fixture',queue,rows:[f],articles:[],refresh:()=>{},activate:()=>activated++};
 return {f,queue,options,service:createReviewTriage(options),activated:()=>activated};
}
test('review submission is deduplicated coordinator work and starts no executor',t=>{
 const {service,queue}=setup(t);const first=service.submit('A-F1','v1');
 assert.equal(first.state,'needs_triage');assert.equal(first.executor,'ChatGPT');
 assert.equal(service.submit('A-F1','v1').id,first.id);assert.equal(queue.list().length,0);
});
test('mixed review blocks on tool repair then dispatches one prioritized WorkBuddy revision',t=>{
 const {service,queue}=setup(t),r=service.submit('A-F1','v1');
 service.resolve(r.id,{kind:'mixed',instructions:'use public group rule'});assert.equal(queue.list().length,0);assert.equal(service.list()[0].state,'waiting_tools');
 const decision={kind:'mixed',instructions:'use public group rule',toolResolved:true,toolCommit:'abc1234',tests:'fixture test passed'};
 service.resolve(r.id,decision);service.resolve(r.id,decision);
 assert.equal(queue.list().length,1);assert.equal(queue.list()[0].executor,'WorkBuddy');assert.equal(queue.list()[0].priority,0);
 assert.equal(queue.list()[0].feedbackRevision,1);
});
test('legacy running job prevents two executors owning the same review',t=>{
 const {options}=setup(t);const service=createReviewTriage({...options,legacyJobs:()=>[{figureId:'A-F1',state:'running'}]});
 assert.throws(()=>service.submit('A-F1','v1'),/旧执行器/);
});
test('new feedback prevents old result publication and review survives service restart',t=>{
 const {f,service,options,queue,activated}=setup(t),r=service.submit('A-F1','v1');
 service.resolve(r.id,{kind:'ordinary',instructions:'edit only requested module'});const job=queue.claim('WorkBuddy');
 f.feedback.revision=2;f.reviewVersion='v2';assert.throws(()=>service.publish(job,{outputs:[]}),/更新/);assert.equal(activated(),0);
 const restored=createReviewTriage(options);assert.equal(restored.list()[0].feedbackRevision,1);assert.equal(restored.list()[0].jobId,job.id);
 restored.decorate();assert.equal(f.revisionJob,null);
});
test('executor failure returns to coordinator and is retried only with a reviewed plan',t=>{
 const {service,queue}=setup(t),r=service.submit('A-F1','v1');
 service.resolve(r.id,{kind:'ordinary',instructions:'first plan'});const job=queue.claim('WorkBuddy');queue.fail(job.id,job.lease,'tool fault');
 assert.equal(service.list()[0].executor,'ChatGPT');assert.equal(service.list()[0].state,'needs_triage');
 service.resolve(r.id,{kind:'mixed',instructions:'fixed plan',toolResolved:true,toolCommit:'123abcd',tests:'regression passed'});
 const next=queue.claim('WorkBuddy');assert.equal(next.id,job.id);assert.equal(next.attempt,2);assert.match(next.revisionNotes,/fixed plan/);assert.equal(next.coordinatorDecision.instructions,'fixed plan');assert.doesNotMatch(next.instructions,/fixed plan/);
});
