import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {verifyProcessingEvidence} from './processing-evidence.mjs';
import {renderedFixture} from './processing-test-fixture.mjs';

const python=process.env.WORKSPACE_TEST_PYTHON,profile=process.env.JFW_TEST_FONT_PROFILE;
for(const operation of ['vector-reletter','raster-reletter','chart-redraw'])test(`${operation} admits genuine common-tool evidence and rejects another required operation`,{skip:!python||!profile},t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'processing-adapter-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const {task,outputs,evidence}=renderedFixture(root,operation);
 assert.equal(verifyProcessingEvidence(task,outputs,evidence,{python})[0].operation,operation);
 task.productionRoute.processing.operation='rebuild';
 assert.throws(()=>verifyProcessingEvidence(task,outputs,evidence,{python}));
});
test('lettering proof cannot omit a required target or be reused for another output source',{skip:!python||!profile},t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'processing-target-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const {task,outputs,evidence}=renderedFixture(root,'raster-reletter');
 task.productionRoute.processing.targetTextIds.push('missing-label');
 assert.throws(()=>verifyProcessingEvidence(task,outputs,evidence,{python}),/换字/);
 task.productionRoute.processing.targetTextIds=['label'];
 const other=structuredClone(task.productionRoute);other.sourceReview.selected=other.sourceReview.archive;
 task.outputRoutes=[{number:'1',productionRoute:other}];
 assert.throws(()=>verifyProcessingEvidence(task,outputs,evidence,{python}),/来源/);
});
