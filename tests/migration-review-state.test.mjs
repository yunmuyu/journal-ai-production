import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {exportPrivate,verifyPrivate} from '../scripts/private-migration.mjs';

test('migration includes the review registry that makes a newer candidate current',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'journal-review-move-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const state=path.join(root,'state');fs.mkdirSync(path.join(state,'review-triage'),{recursive:true});
 for(const name of ['feedback.json','acceptance.json'])fs.writeFileSync(path.join(state,name),'{}');
 const candidate=path.join(root,'current.pdf');fs.writeFileSync(candidate,'%PDF-current');
 const registry=path.join(state,'review-triage','reviews.json');
 fs.writeFileSync(registry,JSON.stringify([{figureId:'figure',state:'ready',result:{outputs:[{path:candidate}]}}]));
 const receipt=path.join(state,'review-triage','published.json');fs.writeFileSync(receipt,JSON.stringify({output:candidate}));
 const output=path.join(root,'migration');exportPrivate({seeds:[path.join(state,'acceptance.json')]},output);
 const manifest=verifyPrivate(output);
 assert.ok(manifest.files.some(row=>row.originalPath===registry));
 assert.ok(manifest.files.some(row=>row.originalPath===candidate));
 assert.ok(manifest.files.some(row=>row.originalPath===receipt));
});
