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
  '--profile',process.env.JFW_TEST_FONT_PROFILE,'--source-root',source,'--output',path.join(root,'output')],{encoding:'utf8',windowsHide:true});
 assert.notEqual(result.status,0);
 const diagnostic=extractToolDiagnostic(result);
 assert.equal(diagnostic.code,'no_feasible_layout');
 assert.ok(diagnostic.issues.length>=3,JSON.stringify(diagnostic));
 assert.ok(diagnostic.issues.some(i=>i.expected_point?.[0]===40));
 assert.ok(diagnostic.issues.some(i=>i.code==='arrow_terminal_not_exact'&&i.required_pt>8));
});
