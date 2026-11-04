import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createWorkBuddyHandler} from './workbuddy-http.mjs';

test('restart restores the same published candidate after acceptance was withdrawn, without accepting it',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'restore-withdrawn-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const output=path.join(root,'figure.pdf');fs.writeFileSync(output,'%PDF-fixture');
 const sha256=createHash('sha256').update(fs.readFileSync(output)).digest('hex');
 const version=createHash('sha256').update(JSON.stringify([[['1',output,sha256]],0])).digest('hex');
 const result={outputs:[{number:'1',path:output,sha256}]},job={id:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',state:'ready',kind:'production',executionMode:'imported-pdf',publicationState:'published',returnMode:'automatic-candidate',outputNumbers:['1'],result,qualityVerification:{kind:'automatic-candidate',status:'candidate',manualStatus:'pending'}};
 fs.mkdirSync(path.join(root,job.id));fs.writeFileSync(path.join(root,job.id,'job.json'),JSON.stringify(job));
 const snapshot={status:'待制作',outputs:[],accepted:false,feedbackRevision:0,userAcceptance:{accepted:false,version}};let restored=0;
 const options={root,origin:'http://127.0.0.1',config:{},getDirectPublicationState:()=>snapshot,restore:()=>restored++};
 createWorkBuddyHandler(options);assert.equal(restored,1);assert.equal(snapshot.userAcceptance.accepted,false);
 snapshot.userAcceptance.version='changed';createWorkBuddyHandler(options);assert.equal(restored,1,'a different reviewed version cannot be overwritten');
});
