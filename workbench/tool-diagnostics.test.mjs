import test from 'node:test';
import assert from 'node:assert/strict';
import {extractToolDiagnostic} from './tool-diagnostics.mjs';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

test('retains every issue and expected values behind multiline stderr warnings',()=>{
 const issues=[{code:'arrow_terminal_length',actual_pt:2,required_pt:8.5},
  {code:'primitive_box_measurement_mismatch',actual_wh:[20,10],expected_wh:[25,13]}];
 const error={stderr:'font warning\n'+JSON.stringify({status:'blocked',error:{code:'no_feasible_layout',attempts:[{issues}]}},null,2)};
 const diagnostic=extractToolDiagnostic(error);
 assert.equal(diagnostic.code,'no_feasible_layout');
 assert.deepEqual(diagnostic.issues,issues);
});

test('non JSON process failures keep their original message without invented issues',()=>{
 assert.equal(extractToolDiagnostic({stderr:'Traceback: bad source'}),null);
});

test('exposes source-bound measured capacity as a readable summary without changing the decision',()=>{
 const capacity={version:1,figure_id:'synthetic-current',spec_hash:'a'.repeat(64),source_bindings:{'source.pdf':'b'.repeat(64)},
  requested_column:'single',column_mm:80,proposed_font_size_pt:5.75,status:'blocked-font',
  summary:'当前布局在单栏80 mm内整图缩放后正文为5.75 pt，低于6 pt，须重新布局。'};
 const report={status:'blocked',error:{code:'layout_reflow_required',message:'须重新布局',capacity}};
 const original=structuredClone(report);
 const diagnostic=extractToolDiagnostic({stderr:'font warning\n'+JSON.stringify(report)});
 assert.equal(diagnostic.summary,capacity.summary);
 assert.deepEqual(diagnostic.capacity,capacity);
 assert.deepEqual(diagnostic.issues,[]);
 assert.deepEqual(report,original);
});

test('capacity geometry evidence does not duplicate original issues or invent raster measurements',()=>{
 const issue={code:'arrow_terminal_length',actual_pt:4,required_pt:8.5};
 const capacity={version:1,figure_id:'synthetic-current',spec_hash:'a'.repeat(64),column_mm:80,proposed_font_size_pt:8,
  summary:'当前布局实际箭头未通过',geometry_issues:[issue]};
 const diagnostic=extractToolDiagnostic({stderr:JSON.stringify({status:'blocked',error:{code:'no_feasible_layout',attempts:[{issues:[issue]}],capacity}})});
 assert.deepEqual(diagnostic.issues,[issue]);
 assert.equal(diagnostic.summary,capacity.summary);
 const unmeasured=extractToolDiagnostic({stderr:JSON.stringify({status:'blocked',error:{code:'layout_reflow_required',capacity:{width_px:800,summary:'do not infer font size'}}})});
 assert.equal(unmeasured.summary,undefined);
 assert.equal(unmeasured.capacity,undefined);
});

test('real public CLI exposes all geometry failures through the shared diagnostic adapter',
 {skip:!process.env.WORKSPACE_TEST_PYTHON||!process.env.JFW_TEST_FONT_PROFILE},t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'tool-diagnostic-cli-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const source=path.join(root,'source');fs.mkdirSync(source);
 const spec={version:1,id:'bad-ports',author:'Synthetic',kind:'scene',synthetic:true,width_pt:130,height_pt:70,
  nodes:[{id:'a',rect:[10,10,40,40],container:true},{id:'b',rect:[70,10,100,40],container:true}],
  paths:[{id:'bad',points:[[42,25],[45,25],[69,25]],arrow:true,exact_terminal:true,
   endpoint_nodes:[{node:'a',side:'right',fraction:.5},'b']}],policy:{column:'single'}};
 const input=path.join(root,'spec.json');fs.writeFileSync(input,JSON.stringify(spec));
 const entry=fileURLToPath(new URL('./run-public-pdf.mjs',import.meta.url));
 const result=spawnSync(process.execPath,[entry,process.env.WORKSPACE_TEST_PYTHON,'render',input,
  '--profile',process.env.JFW_TEST_FONT_PROFILE,'--source-root',source,'--cache',path.join(root,'cache'),
  '--output',path.join(root,'output')],{encoding:'utf8',windowsHide:true});
 assert.notEqual(result.status,0);
 const diagnostic=extractToolDiagnostic(result);
 assert.equal(diagnostic.code,'no_feasible_layout');
 assert.ok(diagnostic.issues.length>=3,JSON.stringify(diagnostic));
 assert.ok(diagnostic.issues.some(i=>i.expected_point?.[0]===40));
 assert.ok(diagnostic.issues.some(i=>i.code==='arrow_terminal_not_exact'&&i.required_pt>8));
});

test('public capacity bridge accepts caller-relative inputs and does not produce a PDF',
 {skip:!process.env.WORKSPACE_TEST_PYTHON||!process.env.JFW_TEST_FONT_PROFILE},t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'capacity-bridge-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.mkdirSync(path.join(root,'source'));
 const spec={version:1,id:'current-capacity',author:'Synthetic',kind:'scene',synthetic:true,width_pt:309,height_pt:50,
  texts:[{id:'a',text:'A',x:20,y:25}],policy:{column:'single',design_font_size_pt:8}};
 const entry=fileURLToPath(new URL('./run-public-pdf.mjs',import.meta.url));
 const invoke=()=>spawnSync(process.execPath,[entry,process.env.WORKSPACE_TEST_PYTHON,'capacity','spec.json',
  '--profile',process.env.JFW_TEST_FONT_PROFILE,'--source-root','source','--cache',path.join(root,'cache')],
  {encoding:'utf8',windowsHide:true,cwd:root});
 fs.writeFileSync(path.join(root,'spec.json'),JSON.stringify(spec));
 const blocked=invoke(),diagnostic=extractToolDiagnostic(blocked);
 assert.equal(blocked.status,2,blocked.stderr);
 assert.equal(diagnostic.capacity.column_mm,80);
 assert.match(diagnostic.summary,/5\.85 pt/);
 assert.equal(diagnostic.capacity.export_padding_pt,.25);
 spec.policy.column='double';fs.writeFileSync(path.join(root,'spec.json'),JSON.stringify(spec));
 const fitted=invoke();assert.equal(fitted.status,0,fitted.stderr);
 const report=JSON.parse(fitted.stdout);
 assert.equal(report.capacity.column_mm,160);
 assert.notEqual(report.capacity.spec_hash,diagnostic.capacity.spec_hash);
 assert.equal(report.pdf_produced,false);
 assert.equal(fs.readFileSync(path.join(root,'spec.json'),'utf8'),JSON.stringify(spec));
 assert.deepEqual(fs.readdirSync(path.join(root,'source')),[]);
 assert.ok(!fs.existsSync(path.join(root,'output')));
});
