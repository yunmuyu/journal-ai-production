import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createReviewTriage} from './review-triage.mjs';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
import {routeFixture,testRef} from './route-test-fixture.mjs';

function setup(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'common-revision-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const source=path.join(root,'source');fs.mkdirSync(source);const route=routeFixture(source);
 route.processing={operation:'rebuild',basis:'Use shared graph layout'};
 const old=path.join(root,'old.pdf');fs.writeFileSync(old,'%PDF-old');
 const figure={id:'A-F1',articleId:'A',author:'fixture',number:'1',reviewVersion:'v1',productionRoute:route,feedback:{revision:3,text:'redraw'},outputs:[{number:'1',file:{path:old}}]};
 const queue=createWorkBuddyQueue({root:path.join(root,'queue'),publish:()=>{throw Error('No execution allowed');}});
 const options={root:path.join(root,'reviews'),origin:'http://local',token:'test',queue,rows:[figure],articles:[],refresh:()=>{},activate:()=>{throw Error('Invalid candidate activated');}};
 const service=createReviewTriage(options),record=service.submit(figure.id,figure.reviewVersion);
 return {root,figure,service,record,queue,options};
}
test('common revision preparation freezes current feedback and route without dispatching any executor',t=>{
 const {service,record,figure,queue}=setup(t),route=structuredClone(figure.productionRoute);route.requirements.widthMm=60;
 const prepared=service.prepareCandidate(record.id,{productionRoute:route});
 const task=JSON.parse(fs.readFileSync(prepared.commonCandidate.task.path));
 assert.equal(task.kind,'revision');assert.equal(task.productionRoute.requirements.widthMm,60);
 assert.equal(task.feedback.text,'redraw');assert.equal(task.feedbackRevision,3);
 assert.deepEqual(task.baseOutputs,record.baseOutputs);assert.equal(queue.list().length,0);
 assert.equal(service.prepareCandidate(record.id,{productionRoute:route}).commonCandidate.task.sha256,prepared.commonCandidate.task.sha256);
 assert.equal(figure.productionRoute.requirements.widthMm,80);
});
test('common revision rejects stale feedback, changed article anchors and old task attempts',t=>{
 const {service,record,figure,root}=setup(t),route=structuredClone(figure.productionRoute);
 const prepared=service.prepareCandidate(record.id,{productionRoute:route});
 service.prepareCandidate(record.id,{productionRoute:route,newAttempt:true});
 assert.throws(()=>service.importCandidate(record.id,{attempt:prepared.commonCandidate.attempt}),/尝试/);
 const other=path.join(root,'other');fs.writeFileSync(other,'other');route.sourceReview.word=testRef(other);
 assert.throws(()=>service.prepareCandidate(record.id,{productionRoute:route,newAttempt:true}),/来源身份/);
 figure.feedback.text='new feedback';
 assert.throws(()=>service.prepareCandidate(record.id,{productionRoute:figure.productionRoute}),/批注/);
});
test('producer correction accepts no feedback and detects feedback added afterward',t=>{
 const {service,figure}=setup(t);figure.feedback=null;
 const record=service.submit(figure.id,figure.reviewVersion,'制作侧修正定位');
 assert.equal(record.feedback,null);assert.equal(record.feedbackRevision,null);
 const prepared=service.prepareCandidate(record.id,{productionRoute:figure.productionRoute});
 assert.equal(JSON.parse(fs.readFileSync(prepared.commonCandidate.task.path)).feedback,null);
 figure.feedback={revision:1,text:'new user review'};
 assert.throws(()=>service.prepareCandidate(record.id,{productionRoute:figure.productionRoute}),/批注/);
});
