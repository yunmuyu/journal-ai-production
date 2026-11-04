import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRevisionJobs} from './revision-jobs.mjs';

test('submission persists, deduplicates and never starts on feedback save alone', async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'revision-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const queue=createRevisionJobs({root,run:async()=>({status:'needs_input',summary:'缺图源',outputs:[]}),publish:()=>{throw Error('must not publish');}});
 assert.equal(queue.list().length,0);
 const input={figureId:'F1',version:'v1',feedback:{revision:1,text:'修正'},outputs:[]};
 const first=queue.submit(input);assert.equal(queue.submit(input).id,first.id);
 await queue.drain();assert.equal(queue.list()[0].state,'needs_input');
 const restored=createRevisionJobs({root,run:async()=>{},publish:()=>{}});
 assert.equal(restored.list()[0].state,'needs_input');
});

test('completed result must publish successfully before becoming ready', async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'revision-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const queue=createRevisionJobs({root,run:async()=>({status:'completed',summary:'修改完',outputs:[]}),publish:()=>{throw Error('版本已变化');}});
 queue.submit({figureId:'F1',version:'v1',feedback:{revision:1},outputs:[]});await queue.drain();
 assert.equal(queue.list()[0].state,'failed');assert.match(queue.list()[0].message,/版本已变化/);
});

test('interrupted tasks do not rerun automatically and retry creates a new attempt', async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'revision-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const queue=createRevisionJobs({root,run:async()=>{throw Error('worker failed');},publish:()=>{}});
 const input={figureId:'F1',version:'v1',feedback:{revision:1},outputs:[]};
 queue.submit(input);await queue.drain();
 assert.throws(()=>queue.submit(input),/重新提交/);
 queue.submit(input,true);assert.equal(queue.list().length,2);
});
