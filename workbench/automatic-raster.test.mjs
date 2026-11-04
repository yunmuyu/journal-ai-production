import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {verifyAutomaticCandidate,verifyProductionResult} from './production-route.mjs';

test('actual Python candidate replay returns pending while strict review still rejects absent receipt',t=>{
 const python=process.env.JFW_TEST_PYTHON||(process.platform==='win32'?'python':'python3');
 try{execFileSync(python,['-c','import PIL,fitz'],{stdio:'ignore'});}catch{return t.skip('Set JFW_TEST_PYTHON with Pillow/PyMuPDF');}
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'auto-raster-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const script="import sys,json;from pathlib import Path;sys.path[:0]=['portable-production','portable-production/tests-task'];from test_automatic_raster import fixture;from task_quality.storage import ref;c,p,n=fixture(Path(sys.argv[1]));q=Path(sys.argv[1])/'contract.json';q.write_text(json.dumps(c));print(json.dumps(dict(contract=ref(q),rasterPlan=ref(p),selfCheck=ref(n),raw=c)))";
 const prepared=JSON.parse(execFileSync(python,['-c',script,root],{encoding:'utf8'}));
 const source=prepared.raw.source,output=path.join(prepared.raw.workspace,'fig1.jpg');
 const route={version:1,method:'raster-preserve',sourceReview:{archive:source,word:source,inventory:source,selected:source,candidates:[{...source,kind:'raster',decision:'selected',reason:'Synthetic test screenshot'}],basis:'Synthetic fixture binding',rasterReason:'Retain synthetic raster'},requirements:{format:'jpg',fontCheck:'none',widthMm:25.4}};
 route.processing={operation:'preserve',basis:'Synthetic source preserved without lettering'};
 const job={id:'task-1',attemptDir:root,productionRoute:route,outputNumbers:['1']};
 const result={quality:{contract:prepared.contract,rasterPlan:prepared.rasterPlan},selfCheck:prepared.selfCheck,outputs:[{number:'1',path:output,sha256:createHash('sha256').update(fs.readFileSync(output)).digest('hex'),fontLabel:''}]};
 const checked=verifyAutomaticCandidate(job,result,{python});
 assert.equal(checked.manual_status,'pending');assert.equal(checked.kind,'automatic-candidate');
 assert.match(result.outputs[0].preview,/fig1\.preview\.png$/);
 assert.throws(()=>verifyProductionResult(job,result,{python}),/核验未通过/);
});
