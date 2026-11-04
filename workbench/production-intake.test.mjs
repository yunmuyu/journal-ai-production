import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareProductionRequests,subfigureCandidateConflicts} from './production-intake.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';

test('five requests retain receipt time and expose missing bindings without inventing unsupported routes',()=>{
 const requestedAt=new Date().toISOString();
 const rows=Array.from({length:5},(_,i)=>({id:'F'+i,number:String(i+1),author:'fixture',editor:'fixture',reviewVersion:'v1',outputs:[],type:'统计曲线图'}));
 const result=prepareProductionRequests({}, {requestedAt,requests:rows.map(r=>({figureId:r.id})),plans:[]},rows);
 assert.equal(result.held.length,5);
 assert.ok(result.held.every(r=>r.status==='needs_bindings'&&r.requestedAt===requestedAt&&r.routes.includes('chart-panels')));
});

test('a detected subfigure set blocks a plan that would publish the parent as one output',()=>{
 const detected={status:'candidate',candidates:[{outputs:[{number:'3.1'},{number:'3.2'}]}]};
 assert.equal(subfigureCandidateConflicts(detected,{outputRoutes:[{number:'3'}]}),true);
 assert.equal(subfigureCandidateConflicts(detected,{outputRoutes:[{number:'3.1'},{number:'3.2'}]}),false);
 assert.equal(subfigureCandidateConflicts({status:'not_detected'}, {outputRoutes:[{number:'3'}]}),false);
});

test('existing candidate is excluded even when it has old feedback and no source plan',()=>{
 const row={id:'F1',outputs:[{number:'1'}],feedback:{revision:2},status:'异常'};
 const result=prepareProductionRequests({}, {requestedAt:new Date().toISOString(),requests:[{figureId:'F1'}]},[row]);
 assert.equal(result.reused.length,0);assert.equal(result.ready.length,0);assert.equal(result.held[0].reason,'candidate_verification_required');
});

test('reuse requires the current candidate file and matching workbench digest',async t=>{
 const crypto=await import('node:crypto');const root=fs.mkdtempSync(path.join(os.tmpdir(),'candidate-reuse-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const file=path.join(root,'candidate.pdf');fs.writeFileSync(file,'candidate');const sha=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
 const row={id:'F1',status:'待终检',previewCurrent:true,outputs:[{number:'1',file:{path:file,meta:{sha256:sha}}}]};
 const request={requestedAt:new Date().toISOString(),requests:[{figureId:'F1'}]};
 assert.equal(prepareProductionRequests({},request,[row]).reused.length,1);
 fs.writeFileSync(file,'changed');const changed=prepareProductionRequests({},request,[row]);
 assert.equal(changed.reused.length,0);assert.equal(changed.held[0].reason,'candidate_verification_required');assert.equal(changed.ready.length,0);
});

test('expired requests stop at admission and duplicate identities are rejected',()=>{
 const request={requestedAt:new Date(Date.now()-181000).toISOString(),requests:[{figureId:'F1'}]};
 assert.equal(prepareProductionRequests({},request,[{id:'F1',outputs:[]}]).held[0].reason,'three_minute_deadline: intake');
 assert.throws(()=>prepareProductionRequests({}, {...request,requests:[{figureId:'F1'},{figureId:'F1'}]},[]),/duplicate_request/);
});

test('conflicting saved plans cannot be selected by modification date',()=>{
 const request={requestedAt:new Date().toISOString(),requests:[{figureId:'F1'}],plans:[{figureId:'F1',baseVersion:'v1',x:1},{figureId:'F1',baseVersion:'v1',x:2}]};
 assert.equal(prepareProductionRequests({},request,[{id:'F1',reviewVersion:'v1',outputs:[]}]).held[0].reason,'ambiguous_saved_plans');
});

test('real CLI admits five requests from HTTP and emits a complete report without publishing',async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'production-intake-'));
 let writes=0;
 const rows=Array.from({length:5},(_,i)=>({id:'F'+i,number:String(i+1),outputs:[],reviewVersion:'v1',type:'统计曲线图'}));
 const server=http.createServer((req,res)=>{if(req.method!=='GET')writes++;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({rows}));});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 t.after(async()=>{await new Promise(resolve=>server.close(resolve));fs.rmSync(root,{recursive:true,force:true});});
 const config=path.join(root,'config.json'),request=path.join(root,'request.json');
 fs.writeFileSync(config,JSON.stringify({origin:'http://127.0.0.1:'+server.address().port}));
 fs.writeFileSync(request,JSON.stringify({requestedAt:new Date().toISOString(),requests:rows.map(r=>({figureId:r.id}))}));
 let output;
 try{await promisify(execFile)(process.execPath,[fileURLToPath(new URL('./production-runner.mjs',import.meta.url)),config,request],{timeout:10000,windowsHide:true});assert.fail('held requests must return nonzero');}
 catch(error){assert.equal(error.code,1);output=JSON.parse(error.stdout);}
 assert.equal(output.admission.held.length,5);assert.equal(output.returnedOutputs,0);assert.equal(writes,0);
});

test('a new request timestamp does not create a second execution directory for the same plan',async t=>{
 const {runProduction}=await import('./production-runner.mjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'production-request-key-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const credentialsFile=path.join(root,'credentials.json');fs.writeFileSync(credentialsFile,'{}');
 const config={workbenchRoot:root,credentialsFile},plan={figureId:'F1'};
 await runProduction(config,{...plan,requestedAt:new Date(Date.now()-181000).toISOString()});
 await runProduction(config,{...plan,requestedAt:new Date(Date.now()-182000).toISOString()});
 assert.equal(fs.readdirSync(path.join(root,'production-runs','F1')).length,1);
});

test('retry cannot hide an expired original request by supplying a new timestamp',async t=>{
 const {runProduction}=await import('./production-runner.mjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'production-retry-clock-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const credentialsFile=path.join(root,'credentials.json');fs.writeFileSync(credentialsFile,'{}');
 const config={workbenchRoot:root,credentialsFile},requestedAt=new Date(Date.now()-181000).toISOString();
 await runProduction(config,{figureId:'F1',requestedAt});
 const result=await runProduction({...config,retryFailed:true},{figureId:'F1',requestedAt:new Date().toISOString()});
 assert.equal(result.requestStartedAt,requestedAt);
 assert.ok(result.elapsedMs>=181000);
 assert.match(result.error,/three_minute_deadline/);
});

test('intake automatically discovers PDF chart cases when no plan exists and source is known',async()=>{
 const {runProductionRequests}=await import('./production-intake.mjs');
 const prior=globalThis.fetch;globalThis.fetch=async()=>({ok:true,json:async()=>({rows:[{id:'chart',articleId:'a',number:'2',reviewVersion:'v',outputs:[],type:'统计曲线图'}]})});
 let calls=0;
 try{
  const source={path:'test.pdf',sha256:'hash'},requestedAt=new Date().toISOString();
  const result=await runProductionRequests({origin:'http://example.test'}, {requestedAt,requests:[{figureId:'chart',source}]},{executeChartRequest:async(_config,request)=>{calls++;assert.equal(request.requestedAt,requestedAt);return {figureId:'chart',status:'needs_bindings',caseRecommendations:{cases:[{id:'known-case'}]}};}});
  assert.equal(calls,1);assert.equal(result.admission.held[0].caseRecommendations.cases[0].id,'known-case');
 }finally{globalThis.fetch=prior;}
});

test('intake also discovers SVG chart routes without treating unsupported extensions as missing source',async()=>{
 const {runProductionRequests}=await import('./production-intake.mjs');
 const prior=globalThis.fetch;globalThis.fetch=async()=>({ok:true,json:async()=>({rows:[{id:'chart',articleId:'a',number:'7',reviewVersion:'v',outputs:[],type:'统计曲线图'}]})});
 let calls=0;
 try{
  const result=await runProductionRequests({origin:'http://example.test'},{requestedAt:new Date().toISOString(),requests:[{figureId:'chart',source:{path:'test.svg',sha256:'hash'}}]},{executeChartRequest:async()=>{calls++;return {status:'needs_bindings',stage:'route_discovery'};}});
  assert.equal(calls,1);assert.equal(result.admission.held[0].stage,'route_discovery');
 }finally{globalThis.fetch=prior;}
});

test('intake proposes Word subfigures and source objects without treating them as an executable plan',async t=>{
 const {runProductionRequests}=await import('./production-intake.mjs');
 const python=process.env.JFW_TEST_PYTHON||'python';
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'intake-word-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const word=path.join(root,'paper.docx'),pdf=path.join(root,'source.pdf');
 const script=`import sys, zipfile, fitz\nw,p=sys.argv[1:]\nxml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>(a) 左侧 (b) 右侧</w:t></w:r></w:p><w:p><w:r><w:t>图3 架构</w:t></w:r></w:p></w:body></w:document>'\nwith zipfile.ZipFile(w,'w') as z: z.writestr('word/document.xml',xml)\nd=fitz.open(); page=d.new_page(); page.insert_text((20,30),'input'); page.insert_text((20,30),'input'); page.draw_line((10,40),(100,40)); page.draw_rect((21,25,23,29),color=None,fill=(.8,.8,.8)); page.set_cropbox(fitz.Rect(5,5,200,200)); d.save(p)`;
 await promisify(execFile)(python,['-c',script,word,pdf],{env:{...process.env,PYTHONUTF8:'1'},windowsHide:true});
 const {createHash}=await import('node:crypto'),sha256=createHash('sha256').update(fs.readFileSync(pdf)).digest('hex');
 const row={id:'F3',articleId:'a',number:'3',reviewVersion:'v',outputs:[],type:'专业图'};
 const prior=globalThis.fetch;globalThis.fetch=async()=>({ok:true,json:async()=>({rows:[row],articles:[{id:'a',word:{path:word}}]})});
 try{
  const result=await runProductionRequests({origin:'http://fixture',python},{requestedAt:new Date().toISOString(),requests:[{figureId:'F3',source:{path:pdf,sha256}}]});
  const held=result.admission.held[0];
  assert.equal(held.reason,'confirmed_plan_missing');assert.deepEqual(held.subfigureCandidates.candidates[0].outputs.map(x=>x.number),['3.1','3.2']);
  assert.equal(held.sourceObjectCandidates.sourceSha256,sha256);assert.ok(held.sourceObjectCandidates.facts.vectorPaths>0);
  assert.equal(held.nativeTextBindings.sourceSha256,sha256);assert.equal(held.nativeTextBindings.replacements[0].source_text,'input');assert.equal(held.nativeTextBindings.replacements[0].source_occurrences,2);assert.equal(held.nativeTextBindings.validated,true);
  assert.equal(held.nativeTextBindings.textShadowProposal.candidates.length,1);
  assert.equal(held.nativeTextBindings.textShadowProposal.status,'needs-semantic-binding');
  assert.deepEqual(held.nativeTextBindings.sourceCropBox,[5,5,200,200]);
  assert.equal(result.returnedOutputs,0);
 }finally{globalThis.fetch=prior;}
});
