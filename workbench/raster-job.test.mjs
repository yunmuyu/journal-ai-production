import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const cli=fileURLToPath(new URL('./raster-job.mjs',import.meta.url));
function fixture(t,checked=true){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'raster-job-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const write=(name,data)=>{const p=path.join(root,name);fs.writeFileSync(p,data);return {path:p,sha256:createHash('sha256').update(data).digest('hex')};};
 const source=write('source.png',Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=','base64'));
 const route={version:1,method:'raster-preserve',sourceReview:{archive:write('archive','fixture'),word:write('word','fixture'),inventory:write('inventory','fixture'),selected:source,candidates:[{...source,kind:'raster',decision:'selected',reason:'synthetic photo'}],basis:'synthetic matched input',rasterReason:'photo'},requirements:{format:'jpg',fontCheck:'none',widthMm:80}};
 const task=write('task.json',JSON.stringify({id:'test-job',attemptDir:root,outputNumbers:['2'],productionRoute:route}));
 const output=path.join(root,'candidate','figure.jpg');
 const plan=write('plan.json',JSON.stringify({version:1,inputs:[{...source,crop:null}],layout:{mode:'single',gap_px:0},output,width_mm:80,target_dpi:null,quality:95}));
 const evidence=write('evidence.json',JSON.stringify({producer:'synthetic-executor',history:{evidence:write('history.json',JSON.stringify({checked,conclusion:'new',reusable:false,observation:'Synthetic test has no historical output'})),conclusion:'new',reusable:false,revision_authorization:''},frozen_manifest:write('frozen.json','[]'),author_roots:[path.join(root,'delivery')],delivery_target:path.join(root,'delivery','figure.jpg'),runtime:{python:process.env.WORKSPACE_TEST_PYTHON,font_profile:write('font.json','{}')},allowed_changes:['grayscale'],immutable_content:['content'],failure_policy:{max_attempts:2,repair:'local-only',time_budget_seconds:null,cost_budget:null}}));
 return {root,task,plan,evidence,output};
}
test('single CLI call creates real JPG and pending postcheck without publication',{skip:!process.env.WORKSPACE_TEST_PYTHON},t=>{
 const f=fixture(t);assert.ok(fs.existsSync(cli),'public raster job entry must exist');
 const run=spawnSync(process.execPath,[cli,f.task.path,f.plan.path,f.evidence.path],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);const out=JSON.parse(run.stdout);
 assert.equal(out.status,'awaiting_visual_review');assert.deepEqual([...fs.readFileSync(f.output).subarray(0,2)],[255,216]);
 const candidate=JSON.parse(fs.readFileSync(path.join(f.root,'candidate','.task-quality','candidate.json'),'utf8'));
 assert.equal(candidate.manual_status,'pending');assert.ok(candidate.coverage_pending.includes('source_geometry'));
 assert.equal(fs.existsSync(path.join(f.root,'delivery','figure.jpg')),false);
 assert.ok(out.timings.every(s=>s.elapsed_ms>=0));assert.ok(fs.existsSync(out.result.path));
});
test('failed precheck stops before render and records failure',{skip:!process.env.WORKSPACE_TEST_PYTHON},t=>{
 const f=fixture(t,false);
 const run=spawnSync(process.execPath,[cli,f.task.path,f.plan.path,f.evidence.path],{encoding:'utf8'});
 assert.equal(run.status,1);assert.equal(fs.existsSync(f.output),false);
 const record=JSON.parse(fs.readFileSync(path.join(f.root,'raster-job','failure.json'),'utf8'));
 assert.equal(record.stage,'precheck');assert.ok(record.timings.every(s=>s.stage!=='render'));
});
test('failed render cannot create submission or result',{skip:!process.env.WORKSPACE_TEST_PYTHON},t=>{
 const f=fixture(t),plan=JSON.parse(fs.readFileSync(f.plan.path,'utf8'));plan.quality=500;
 fs.writeFileSync(f.plan.path,JSON.stringify(plan));
 const run=spawnSync(process.execPath,[cli,f.task.path,f.plan.path,f.evidence.path],{encoding:'utf8'});
 assert.equal(run.status,1);assert.equal(fs.existsSync(path.join(f.root,'raster-job','result.json')),false);
 assert.equal(fs.existsSync(path.join(f.root,'raster-job','submission.json')),false);
 const record=JSON.parse(fs.readFileSync(path.join(f.root,'raster-job','failure.json'),'utf8'));
 assert.equal(record.stage,'render');assert.ok(record.timings.every(s=>s.stage!=='postcheck'));
});
