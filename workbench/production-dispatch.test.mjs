import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {routeFixture} from './route-test-fixture.mjs';
import {dispatchInstructions} from './production-dispatch.mjs';
import {productionInstructions} from './production-route.mjs';
import {createWorkBuddyQueue} from './workbuddy-queue.mjs';
test('recognized old generated instructions refresh without changing feedback or saved task',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'dispatch-policy-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const route=routeFixture(root),current=productionInstructions(route);
 const old=current.replace(/\n已确认制作规则（[^]*?）：\n[^]*?\n(?=必须独立检查|$)/,'');
 assert.notEqual(old,current);
 const task={productionRoute:route,outputNumbers:['1'],instructions:old,feedback:{text:'retain exact correction',revision:3}};
 const before=structuredClone(task);assert.equal(dispatchInstructions(task),current);assert.deepEqual(task,before);
 assert.throws(()=>dispatchInstructions({...task,instructions:'arbitrary old author instructions'}),/自由文本/);
});

test('restored queued task delivers current rules when claimed and preserves old generated instructions',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'claim-policy-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const route=routeFixture(root),queueRoot=path.join(root,'jobs');
 const queue=createWorkBuddyQueue({root:queueRoot,publish:()=>{}});
 const created=queue.enqueue({key:'legacy-policy',group:'fixture',productionRoute:route,outputNumbers:['1'],sources:[route.sourceReview.word],feedback:{text:'preserve exact feedback',revision:3}});
 const storedPath=path.join(queueRoot,created.id,'job.json'),stored=JSON.parse(fs.readFileSync(storedPath,'utf8'));
 const old=productionInstructions(route,{includeRoutingPolicy:false});stored.instructions=old;fs.writeFileSync(storedPath,JSON.stringify(stored));
 const restored=createWorkBuddyQueue({root:queueRoot,publish:()=>{}}),claimed=restored.claim('fixture');
 assert.equal(claimed.instructions,productionInstructions(route));
 assert.equal(claimed.previousGeneratedInstructions,old);
 assert.deepEqual(claimed.feedback,stored.feedback);
 assert.deepEqual(claimed.productionRoute,stored.productionRoute);
 assert.equal(JSON.parse(fs.readFileSync(storedPath,'utf8')).instructions,claimed.instructions);
});
