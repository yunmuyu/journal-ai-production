import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {assertDispatchAllowed,buildProductionQueue,bindAuthoritativeSources} from './production-admission.mjs';

test('confirmed source defect blocks every matching figure before tools; unrelated and repaired versions continue',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'admission-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const evidence=path.join(root,'failure.txt');fs.writeFileSync(evidence,'confirmed hidden Form font failure');
 const registry=path.join(root,'faults.json'),proof={path:evidence,sha256:createHash('sha256').update(fs.readFileSync(evidence)).digest('hex')};
 fs.writeFileSync(registry,JSON.stringify({version:1,faults:[{id:'form-font',status:'open',engineSignature:'frozen',scope:{sourceHashes:['bad-source']},evidence:proof,reason:'Form font cleanup unsupported'}]}));
 const config={knownFaultsFile:registry,runtimeLock:{engineSignature:'frozen'}};
 const plan=figureId=>({figureId,outputRoutes:[{number:'1',productionRoute:{sourceReview:{selected:{sha256:'bad-source'}}}}]});
 for(const id of ['author-A','author-B'])assert.throws(()=>assertDispatchAllowed(config,plan(id)),e=>e.code==='known_fault'&&e.faultIds[0]==='form-font');
 assert.doesNotThrow(()=>assertDispatchAllowed({...config,runtimeLock:{engineSignature:'repaired'}},plan('A')));
 assert.doesNotThrow(()=>assertDispatchAllowed(config,{figureId:'C',outputRoutes:[]}));
 const r=JSON.parse(fs.readFileSync(registry));r.faults[0].status='resolved';fs.writeFileSync(registry,JSON.stringify(r));
 assert.doesNotThrow(()=>assertDispatchAllowed(config,plan('A')));
 r.faults[0].status='open';fs.writeFileSync(registry,JSON.stringify(r));fs.writeFileSync(evidence,'changed');
 assert.throws(()=>assertDispatchAllowed(config,plan('A')),/fault_evidence_changed/);
 fs.writeFileSync(evidence,'confirmed hidden Form font failure');r.faults[0].scope={specHashes:['failed-layout']};fs.writeFileSync(registry,JSON.stringify(r));
 assert.throws(()=>assertDispatchAllowed(config,{...plan('A'),render:[{spec:{sha256:'failed-layout'}}]}),e=>e.failureAction==='correct_plan');
 assert.doesNotThrow(()=>assertDispatchAllowed(config,{...plan('A'),render:[{spec:{sha256:'corrected-layout'}}]}));
});

test('queue preserves reviewed candidates and reports missing plans instead of inventing ready work',()=>{
 const rows=[{id:'accepted',status:'终检通过',outputs:[{}]},{id:'candidate',status:'待终检',outputs:[{}]},{id:'missing',status:'待制作',outputs:[]}];
 const queue=buildProductionQueue({},[],rows);
 assert.equal(queue.ready.length,0);assert.equal(queue.reused.length,2);
 assert.deepEqual(queue.held.map(x=>[x.figureId,x.reason]),[['missing','plan_not_prepared']]);
 const chart=buildProductionQueue({},[],[{id:'chart',type:'统计曲线图',status:'待制作',outputs:[]}]);
 assert.equal(chart.held[0].reason,'chart_route_discovery_required');
 assert.throws(()=>buildProductionQueue({},[{figureId:'missing'},{figureId:'missing'}],rows),/duplicate_plan/);
 assert.throws(()=>assertDispatchAllowed({},{figureId:'missing',state:'held',holdReason:'source requires repair'}),/plan_on_hold/);
 assert.throws(()=>assertDispatchAllowed({},{figureId:'missing',doNotRunUntilBlockerResolved:true}),/plan_on_hold/);
 assert.throws(()=>assertDispatchAllowed({},{figureId:'missing',qualityRoute:'source-preserving-circuit'}),/unsupported_quality_route/);
});

test('source aliases are bound to server catalog spelling without accepting a different file',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'catalog-path-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const file=path.join(root,'source.docx');fs.writeFileSync(file,'source');const source={path:file,sha256:createHash('sha256').update(fs.readFileSync(file)).digest('hex')};
 const config={catalog:{batchHash:source.sha256,archive:source,articles:[{id:'A',word:source}]}};
 const routes=[{productionRoute:{sourceReview:{archive:{...source,path:path.join(root,'.','source.docx').replaceAll('\\','/')},word:{...source,path:path.join(root,'unused','..','source.docx')}}}}];
 bindAuthoritativeSources(config,'A',routes);assert.equal(routes[0].productionRoute.sourceReview.archive.path,source.path);assert.equal(routes[0].productionRoute.sourceReview.word.path,source.path);
 const copy=path.join(root,'copy.docx');fs.copyFileSync(file,copy);routes[0].productionRoute.sourceReview.word.path=copy;
 assert.throws(()=>bindAuthoritativeSources(config,'A',routes),/authoritative_source_mismatch/);
});
