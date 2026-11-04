import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createWorkBuddyHandler} from './workbuddy-http.mjs';
import {testRef} from './route-test-fixture.mjs';

for(const changedOutput of [false,true])test(`restore published base after newer feedback; acceptance belongs to ${changedOutput?'another':'same'} output`,t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'prior-acceptance-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const pdf=path.join(root,'published.pdf');fs.writeFileSync(pdf,'%PDF-fixture');
 const output={number:'10',...testRef(pdf)},id='12345678-1234-1234-1234-123456789abc';
 const acceptedOutputs=[['10',changedOutput?path.join(root,'another.pdf'):pdf,output.sha256]];
 const acceptance={accepted:true,version:createHash('sha256').update(JSON.stringify([acceptedOutputs,2])).digest('hex')};
 const snapshot={outputs:[],status:'待制作',accepted:true,approved:false,userAcceptance:acceptance,feedbackRevision:3,feedback:{revision:3,text:'new correction'}};
 const before=structuredClone(snapshot);
 const job={id,state:'ready',executionMode:'imported-pdf',returnMode:'automatic-candidate',publicationState:'published',createdAt:'2026-01-01',outputNumbers:['10'],qualityVerification:{kind:'automatic-candidate',status:'candidate',manualStatus:'pending'},result:{outputs:[output]}};
 fs.mkdirSync(path.join(root,id));fs.writeFileSync(path.join(root,id,'job.json'),JSON.stringify(job));
 let restored=0;
 createWorkBuddyHandler({root,origin:'http://127.0.0.1',config:{workerToken:'fixture'},getDirectPublicationState:()=>structuredClone(snapshot),publish:()=>assert.fail('must not publish'),restore:()=>restored++});
 assert.equal(restored,changedOutput?0:1);
 assert.deepEqual(snapshot,before);
});
