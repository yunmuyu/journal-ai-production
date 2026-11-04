import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {routeFixture,testRef} from './route-test-fixture.mjs';

const python=process.env.WORKSPACE_TEST_PYTHON,profile=process.env.JFW_TEST_FONT_PROFILE;
const engine=fileURLToPath(new URL('../portable-production/direct-pdf/',import.meta.url));
export function renderedFixture(root,operation){
 const rendered=JSON.parse(execFileSync(python,[fileURLToPath(new URL('./processing-test-fixture.py',import.meta.url)),root,operation,profile],{env:{...process.env,PYTHONPATH:engine,PYTHONUTF8:'1'},encoding:'utf8',windowsHide:true}));
 const route=routeFixture(path.join(root,'source'));route.sourceReview.selected=rendered.source;
 route.sourceReview.candidates=[{...rendered.source,kind:operation==='vector-reletter'?'vector':'raster',decision:'selected',reason:'Synthetic source verified'}];
 route.processing={operation,basis:'Synthetic reviewed processing requirement',...(operation!=='chart-redraw'?{targetTextIds:['label']}:{})};
 route.requirements.widthMm=rendered.report.pdf_audit.width_mm;
 const folder=path.join(root,'output','fixture','proof');
 return {task:{id:'proof-task',attemptDir:root,outputNumbers:['1'],productionRoute:route},
  outputs:[{number:'1',...testRef(path.join(folder,'proof.pdf'))}],
  evidence:[{number:'1',report:testRef(path.join(folder,'report.json')),spec:testRef(path.join(folder,'figure.spec.json'))}]};
}

export function qualityFixture(task,rendered,root){
 const dir=task.attemptDir;
 const write=(name,value)=>{const p=path.join(dir,name);fs.writeFileSync(p,JSON.stringify(value));return testRef(p);};
 const input=write('rendered-input.json',{outputs:rendered.outputs,processingEvidence:rendered.evidence});
 const context={producer:'synthetic-public-renderer',qualityRoute:'source-preserving-chart',author_roots:[path.join(root,'delivery')],
  history:{evidence:write('history.json',{checked:true,conclusion:'new',reusable:false,observation:'Synthetic old output has the feedback covered by this regression'}),conclusion:'new',reusable:false,revision_authorization:'Synthetic reviewed revision'},
  frozen_manifest:write('frozen.json',[]),
  runtime:{python:testRef(python),font_profile:testRef(profile)},delivery_targets:{'1':path.join(root,'delivery','figure.pdf')},
  allowed_changes:['lettering'],immutable_content:['data'],failure_policy:{max_attempts:2,repair:'local-only',time_budget_seconds:null,cost_budget:null}};
 const contextRef=write('context.json',context),cli=fileURLToPath(new URL('./pdf-candidate.mjs',import.meta.url));
 const args=[cli,path.join(dir,'task.json'),input.path,contextRef.path];
 const result=JSON.parse(execFileSync(process.execPath,args,{encoding:'utf8',windowsHide:true}));
 const reused=JSON.parse(execFileSync(process.execPath,args,{encoding:'utf8',windowsHide:true}));
 if(!reused.reused||result.candidate.sha256!==reused.candidate.sha256)throw Error('Public PDF staging is not idempotent');
 return JSON.parse(fs.readFileSync(result.candidate.path,'utf8'));
}
