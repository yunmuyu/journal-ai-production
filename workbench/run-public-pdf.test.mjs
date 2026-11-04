import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {renderedFixture} from './processing-test-fixture.mjs';

test('public render resolves relative spec, source, profile and output against caller cwd',{skip:!process.env.WORKSPACE_TEST_PYTHON||!process.env.JFW_TEST_FONT_PROFILE},t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'relative-pdf-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const fixture=renderedFixture(root,'raster-reletter');
 const result=spawnSync(process.execPath,[fileURLToPath(new URL('./run-public-pdf.mjs',import.meta.url)),process.env.WORKSPACE_TEST_PYTHON,'render',path.relative(root,fixture.evidence[0].spec.path),'--source-root','source','--profile',process.env.JFW_TEST_FONT_PROFILE,'--output','relative-output'],{cwd:root,encoding:'utf8',windowsHide:true});
 assert.equal(result.status,0,result.stderr);assert.ok(fs.existsSync(path.join(root,'relative-output','fixture','proof','proof.pdf')));
});
test('public runner ignores stale installed engine on inherited PYTHONPATH',{skip:!process.env.WORKSPACE_TEST_PYTHON},t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'old-pdf-engine-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const old=path.join(root,'journal_pdf');fs.mkdirSync(old);fs.writeFileSync(path.join(old,'__init__.py'),'raise RuntimeError("STALE_ENGINE_IMPORTED")');
 const result=spawnSync(process.execPath,[fileURLToPath(new URL('./run-public-pdf.mjs',import.meta.url)),process.env.WORKSPACE_TEST_PYTHON,'--help'],{env:{...process.env,PYTHONPATH:root},encoding:'utf8',windowsHide:true});
 assert.equal(result.status,0,result.stderr);assert.match(result.stderr,/journal_pdf_module=.*portable-production/);assert.doesNotMatch(result.stderr,/STALE_ENGINE_IMPORTED/);
});
