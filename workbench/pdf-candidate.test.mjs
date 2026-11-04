import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {renderedFixture,qualityFixture} from './processing-test-fixture.mjs';
import {testRef} from './route-test-fixture.mjs';
import {verifyImportedPdfCandidate} from './imported-pdf.mjs';

test('ordinary PDF adapter preserves server staging and passes the server verifier', {skip:!process.env.WORKSPACE_TEST_PYTHON||!process.env.JFW_TEST_FONT_PROFILE},t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'pdf-import-adapter-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const rendered=renderedFixture(path.join(root,'render'),'raster-reletter');
 const attemptDir=path.join(root,'attempt'),stage=path.join(attemptDir,'imported-pdf');fs.mkdirSync(stage,{recursive:true});
 const staged=path.join(stage,'candidate-1.pdf');fs.copyFileSync(rendered.outputs[0].path,staged);
 const task={...rendered.task,attempt:1,attemptDir,executionMode:'imported-pdf',existingPdf:{outputs:[{number:'1',staged:testRef(staged)}]}};
 fs.writeFileSync(path.join(attemptDir,'task.json'),JSON.stringify(task));
 const candidate=qualityFixture(task,rendered,root);
 assert.equal(candidate.outputs[0].path,fs.realpathSync(staged));
 const checked=verifyImportedPdfCandidate(task,candidate,{python:process.env.WORKSPACE_TEST_PYTHON});
 assert.equal(checked.qualityVerification.manualStatus,'pending');
 assert.ok(fs.existsSync(checked.result.outputs[0].preview));
 fs.appendFileSync(staged,'tamper');
 assert.throws(()=>verifyImportedPdfCandidate(task,candidate,{python:process.env.WORKSPACE_TEST_PYTHON}),/哈希|候选|证据/);
});
