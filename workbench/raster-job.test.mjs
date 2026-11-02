import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {verifyAutomaticCandidate} from './production-route.mjs';
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
 // Repeating the normal command returns the sealed result without rerendering.
 const repeated=spawnSync(process.execPath,[cli,f.task.path,f.plan.path,f.evidence.path],{encoding:'utf8'});
 assert.equal(repeated.status,0,repeated.stderr);assert.equal(JSON.parse(repeated.stdout).reused,true);
 const auditPath=path.join(f.root,'candidate','raster-job-audit.json'),auditBytes=fs.readFileSync(auditPath);
 const sealedHistory=path.join(f.root,'raster-job','snapshots','history.json'),historyBytes=fs.readFileSync(sealedHistory);
 fs.writeFileSync(path.join(f.root,'history.json'),'original working note changed');
 assert.deepEqual(fs.readFileSync(sealedHistory),historyBytes);
 const observations=path.join(f.root,'observations.json');fs.writeFileSync(observations,JSON.stringify({observations:{source_content:'Synthetic pixel preserved',readability:'No letters in fixture',grayscale_semantics:'One grayscale pixel, no categories'}}));
 const note=spawnSync(process.execPath,[cli,'self-check',f.task.path,observations],{encoding:'utf8'});
 assert.equal(note.status,0,note.stderr);const added=JSON.parse(note.stdout);
 const result=JSON.parse(fs.readFileSync(added.result.path,'utf8'));assert.ok(result.selfCheck);
 const returned=verifyAutomaticCandidate(JSON.parse(fs.readFileSync(f.task.path,'utf8')),result,{python:process.env.WORKSPACE_TEST_PYTHON});
 assert.equal(returned.kind,'automatic-candidate');assert.equal(returned.manual_status,'pending');
 const selfCheck=JSON.parse(fs.readFileSync(result.selfCheck.path,'utf8'));
 assert.equal(selfCheck.producer,'synthetic-executor');assert.equal(selfCheck.candidate_sha256,createHash('sha256').update(fs.readFileSync(path.join(f.root,'candidate','.task-quality','candidate.json'))).digest('hex'));
 assert.deepEqual(fs.readFileSync(auditPath),auditBytes);
 const afterNote=spawnSync(process.execPath,[cli,f.task.path,f.plan.path,f.evidence.path],{encoding:'utf8'});
 assert.equal(afterNote.status,0,afterNote.stderr);
 // A same-user chmod can bypass read-only; the hash seal still rejects the edit.
 fs.chmodSync(auditPath,0o666);fs.appendFileSync(auditPath,' ');
 const changed=spawnSync(process.execPath,[cli,f.task.path,f.plan.path,f.evidence.path],{encoding:'utf8'});
 assert.equal(changed.status,1);assert.match(changed.stderr,/封存证据已变化.*新attempt/);
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
test('incomplete attempt cannot be overwritten and a fresh attempt can run',{skip:!process.env.WORKSPACE_TEST_PYTHON},t=>{
 const old=fixture(t,false);
 const args=[cli,old.task.path,old.plan.path,old.evidence.path];
 assert.equal(spawnSync(process.execPath,args,{encoding:'utf8'}).status,1);
 const failurePath=path.join(old.root,'raster-job','failure.json'),before=fs.readFileSync(failurePath);
 const repeated=spawnSync(process.execPath,args,{encoding:'utf8'});assert.equal(repeated.status,1);assert.match(repeated.stderr,/需要新attempt/);
 const fresh=fixture(t,true),run=spawnSync(process.execPath,[cli,fresh.task.path,fresh.plan.path,fresh.evidence.path],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);assert.ok(fs.existsSync(fresh.output));assert.deepEqual(fs.readFileSync(failurePath),before);
});
