import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {classifyProductionFailure,verifyProductionDelivery,productionReport} from './production-observability.mjs';

test('failure categories preserve unknown failures and never authorize automatic retries',()=>{
 assert.equal(classifyProductionFailure(Error('Plan baseline is stale'),'preflight').code,'stale_version');
 assert.equal(classifyProductionFailure(Error('Source or evidence changed: example'),'render').code,'source_changed');
 assert.equal(classifyProductionFailure(Error('series_binding_confirmation_required'),'preflight').code,'needs_bindings');
 assert.equal(classifyProductionFailure(Error('series_binding_source_changed'),'preflight').code,'source_changed');
 assert.equal(classifyProductionFailure(Error('Workbench preview unavailable'),'verify').code,'visibility_unavailable');
 assert.equal(classifyProductionFailure(Error('novel failure'),'render').code,'render_failed');
 const unknown=classifyProductionFailure(Error('novel failure'),'unknown');
 assert.equal(unknown.code,'unknown');assert.equal(unknown.automaticRetry,false);assert.equal(unknown.message,'novel failure');
});

async function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'production-receipts-'));
 const bytes=Buffer.from('synthetic output'),sha=createHash('sha256').update(bytes).digest('hex');
 const outputs=[{number:'1a',sha256:sha},{number:'1b',sha256:sha}];
 const figure={id:'F1',articleId:'A',number:'1',author:'fixture',editor:'batch-editor',status:'待终检',outputs:outputs.map(o=>({number:o.number,file:{token:o.number,meta:{sha256:o.sha256}}}))};
 let previewFailure=false,changeDuringPreview=false;
 const server=http.createServer((req,res)=>{
  if(req.url==='/data')return res.end(JSON.stringify({rows:[figure]}));
  if(req.url.startsWith('/file/'))return res.end(bytes);
  if(req.url.startsWith('/preview/')){if(changeDuringPreview)figure.reviewVersion='changed';return previewFailure?res.writeHead(503).end():res.end('preview fixture');}
  res.writeHead(404).end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 t.after(async()=>{await new Promise(resolve=>server.close(resolve));fs.rmSync(root,{recursive:true,force:true});});
 return {root,outputs,figure,config:{origin:'http://127.0.0.1:'+server.address().port,receiptRoot:root},fail:v=>{previewFailure=v;},changeDuringPreview:()=>{changeDuringPreview=true;}};
}

test('receipt requires readable workbench output and repeat verification preserves original delivery time',async t=>{
 const x=await fixture(t),request={figureId:'F1',outputs:x.outputs,batchHash:'batch',kind:'ordinary'};
 x.fail(true);await assert.rejects(verifyProductionDelivery(x.config,request),/preview unavailable/);assert.equal(fs.readdirSync(x.root).length,0);
 x.fail(false);const first=await verifyProductionDelivery(x.config,request),again=await verifyProductionDelivery(x.config,request);
 assert.equal(first.receipt.outputs.length,2);assert.equal(first.receipt.author,'fixture');
 assert.equal(first.receipt.id,again.receipt.id);assert.equal(first.receipt.returnedAt,again.receipt.returnedAt);
 assert.equal(first.newReceipt,true);assert.equal(again.newReceipt,false);assert.equal(fs.readdirSync(x.root).length,1);
 const report=productionReport({receiptRoots:[x.root,x.root],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'});
 assert.equal(report.deliveredFigures,1);assert.equal(report.deliveredOutputs,2);
 x.figure.outputs[0].file.meta.sha256='0'.repeat(64);
 await assert.rejects(verifyProductionDelivery(x.config,request),/hash mismatch/);
});

test('time windows use receipt timestamps, deduplicate copies, and separate revisions from figures',async t=>{
 const x=await fixture(t),a=(await verifyProductionDelivery(x.config,{figureId:'F1',outputs:x.outputs,batchHash:'batch',kind:'ordinary'})).receipt;
 // Historical timestamps are synthetic fixtures; real receipts are always stamped by the verifier.
 a.returnedAt='2026-11-03T00:00:00Z';fs.writeFileSync(path.join(x.root,a.id+'.json'),JSON.stringify(a));
 x.figure.id='F2';x.figure.number='2';
 const b=(await verifyProductionDelivery(x.config,{figureId:'F2',outputs:x.outputs,batchHash:'batch',kind:'revision'})).receipt;
 b.returnedAt='2026-11-03T01:00:00Z';fs.writeFileSync(path.join(x.root,b.id+'.json'),JSON.stringify(b));
 const report=productionReport({receiptRoots:[x.root],from:'2026-11-03T00:00:00Z',to:'2026-11-03T01:00:00Z'});
 assert.equal(report.deliveredFigures,1);assert.equal(report.deliveredOutputs,2);assert.equal(report.figuresPerHour,1);assert.equal(report.revisionDeliveries,0);
 const all=productionReport({receiptRoots:[x.root],from:'2026-11-03T00:00:00Z',to:'2026-11-03T02:00:00Z'});
 assert.equal(all.deliveredFigures,2);assert.equal(all.revisionDeliveries,1);
});

test('missing or corrupt receipt roots and invalid windows cannot silently produce zero throughput',async t=>{
 const x=await fixture(t);
 assert.throws(()=>productionReport({receiptRoots:[x.root],from:'bad',to:'bad'}),/window/);
 assert.throws(()=>productionReport({receiptRoots:[path.join(x.root,'missing')],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'}));
 fs.writeFileSync(path.join(x.root,'bad.json'),'{');
 assert.throws(()=>productionReport({receiptRoots:[x.root],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'}));
});

test('concurrent verification and partial-output revisions do not double-count identical outputs',async t=>{
 const x=await fixture(t),request={figureId:'F1',outputs:x.outputs,batchHash:'batch'};
 const results=await Promise.all([verifyProductionDelivery(x.config,request),verifyProductionDelivery(x.config,request)]);
 assert.equal(results.filter(r=>r.newReceipt).length,1);
 x.figure.outputs=x.figure.outputs.slice(0,1);
 await verifyProductionDelivery(x.config,{...request,outputs:x.outputs.slice(0,1),kind:'revision'});
 const report=productionReport({receiptRoots:[x.root],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'});
 assert.equal(report.deliveredFigures,1);assert.equal(report.deliveredOutputs,2);assert.equal(report.deliveryEvents,2);assert.equal(report.revisionDeliveries,1);
});

test('historical candidates can be verified without being counted as new throughput',async t=>{
 const x=await fixture(t);await verifyProductionDelivery(x.config,{figureId:'F1',outputs:x.outputs,batchHash:'batch',historical:true});
 const report=productionReport({receiptRoots:[x.root],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'});
 assert.equal(report.deliveredFigures,0);assert.equal(report.historicalReceipts,1);
});

test('workbench version changing during verification creates no receipt',async t=>{
 const x=await fixture(t);x.changeDuringPreview();
 await assert.rejects(verifyProductionDelivery(x.config,{figureId:'F1',outputs:x.outputs,batchHash:'batch'}),/output set not visible/);
 assert.equal(fs.readdirSync(x.root).length,0);
});

test('report CLI reads persisted receipts using the supplied reporting window',async t=>{
 const x=await fixture(t);await verifyProductionDelivery(x.config,{figureId:'F1',outputs:x.outputs,batchHash:'batch'});
 const input=path.join(x.root,'window.input');fs.writeFileSync(input,JSON.stringify({receiptRoots:[x.root],from:'2000-01-01T00:00:00Z',to:'2100-01-01T00:00:00Z'}));
 const result=await promisify(execFile)(process.execPath,[fileURLToPath(new URL('./production-observability.mjs',import.meta.url)),input],{windowsHide:true,encoding:'utf8'});
 assert.equal(JSON.parse(result.stdout).deliveredOutputs,2);
});
