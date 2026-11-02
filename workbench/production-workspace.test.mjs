import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const modulePath=fileURLToPath(new URL('./production-workspace.mjs',import.meta.url));
function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'workspace-test-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const write=(name,data)=>{const p=path.join(root,name);fs.writeFileSync(p,data);return {path:p,sha256:createHash('sha256').update(data).digest('hex')};};
 const selected=write('source.png',Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=','base64'));
 const route={version:1,method:'raster-preserve',sourceReview:{archive:write('archive','archive'),word:write('word','word'),inventory:write('inventory','inventory'),selected,candidates:[{...selected,kind:'raster',decision:'selected',reason:'photograph'}],basis:'source matches Word',rasterReason:'photograph'},requirements:{format:'jpg',fontCheck:'none',widthMm:57}};
 const task=write('task.json',JSON.stringify({id:'job',attemptDir:root,outputNumbers:['3'],productionRoute:route}));
 const plan={version:1,inputs:[{...selected,crop:null}],layout:{mode:'single',gap_px:0},output:path.join(root,'candidate','image.jpg'),width_mm:57,target_dpi:null,quality:95};
 const planRef=write('plan.json',JSON.stringify(plan));return {root,write,task,plan,planRef};
}
test('missing semantic evidence is explicit and writes no contract',async t=>{
 const f=fixture(t); // Given a real route, but no producer evidence.
 assert.ok(fs.existsSync(modulePath),'public preparation helper must exist');
 const {prepareProductionWorkspace}=await import('./production-workspace.mjs');
 const result=prepareProductionWorkspace(f.task.path,f.planRef.path,{}); // When preparing.
 assert.equal(result.status,'needs_evidence');assert.ok(result.missing.includes('history')); // Then no invented check.
 assert.equal(fs.existsSync(path.join(f.root,'quality-contract.json')),false);
});
test('conflicting width is rejected',async t=>{
 const f=fixture(t);const {prepareProductionWorkspace}=await import('./production-workspace.mjs');
 f.plan.width_mm=80;fs.writeFileSync(f.planRef.path,JSON.stringify(f.plan));
 assert.throws(()=>prepareProductionWorkspace(f.task.path,f.planRef.path,{}),/尺寸|布局|输出/);
});
test('output escaping the attempt is rejected',async t=>{
 const f=fixture(t);f.plan.output=path.join(f.root,'..','escaped.jpg');fs.writeFileSync(f.planRef.path,JSON.stringify(f.plan));
 const {prepareProductionWorkspace}=await import('./production-workspace.mjs');
 assert.throws(()=>prepareProductionWorkspace(f.task.path,f.planRef.path,{}),/attempt内部/);
});
test('CLI reports missing evidence without production',t=>{
 const f=fixture(t);
 const run=spawnSync(process.execPath,[modulePath,f.task.path,f.planRef.path],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);assert.equal(JSON.parse(run.stdout).status,'needs_evidence');
 assert.equal(fs.existsSync(f.plan.output),false);
});
test('actual public raster dimensions and quality schema assemble a candidate-only contract', {skip:!process.env.WORKSPACE_TEST_PYTHON},async t=>{
 const f=fixture(t),python=process.env.WORKSPACE_TEST_PYTHON; // Given synthetic sources and explicit executor evidence.
 const evidence={producer:'fixture-executor',history:{evidence:f.write('history.json',JSON.stringify({checked:true,conclusion:'new',reusable:false})),conclusion:'new',reusable:false,revision_authorization:''},
  frozen_manifest:f.write('frozen.json','[]'),author_roots:[path.join(f.root,'delivery')],delivery_target:path.join(f.root,'delivery','fig3.jpg'),
  runtime:{python,font_profile:f.write('fonts.json','{}')},allowed_changes:['grayscale'],immutable_content:['all content'],
  failure_policy:{max_attempts:2,repair:'local-only',time_budget_seconds:null,cost_budget:null}};
 const {prepareProductionWorkspace}=await import('./production-workspace.mjs');
 const target=path.join(f.root,'quality-contract.json');
 const result=prepareProductionWorkspace(f.task.path,f.planRef.path,evidence,target); // When using real public primitives.
 const contract=JSON.parse(fs.readFileSync(target,'utf8')); // Then no produced or approved image exists.
 assert.equal(result.status,'prepared');assert.equal(contract.producer,'fixture-executor');
 assert.deepEqual(contract.outputs[0].pixels,[1,1]);assert.equal(contract.outputs[0].width_mm,57);
 assert.equal(contract.source_inputs.length,6);assert.equal(fs.existsSync(f.plan.output),false);
 assert.equal(fs.existsSync(path.join(f.root,'candidate','.task-quality')),false);
 assert.throws(()=>prepareProductionWorkspace(f.task.path,f.planRef.path,evidence,target),/EEXIST/);
});
test('changed source references are rejected before assembly',async t=>{
 const f=fixture(t);fs.appendFileSync(f.plan.inputs[0].path,'changed');
 const {prepareProductionWorkspace}=await import('./production-workspace.mjs');
 assert.throws(()=>prepareProductionWorkspace(f.task.path,f.planRef.path,{}),/哈希/);
});
