import test from 'node:test';
import assert from 'node:assert/strict';
import {rankCases,projectCaseOutcome,shouldBlockIdenticalAttempt} from './figure-case-index.mjs';

test('semantic similarity recommends methods without copying bindings and exact error is prioritised',()=>{
 const cases=[{id:'success',features:{kind:'chart',format:'pdf',nativeText:true,vector:true,panels:1},outcome:'candidate',entry:'source-vector-reletter'},
  {id:'error',features:{kind:'chart',format:'pdf',nativeText:true,vector:true},outcome:'failure',errorCode:'source_icon_pixels_changed'}];
 const result=rankCases(cases,{kind:'chart',format:'pdf',nativeText:true,vector:true,panels:1,errorCode:'source_icon_pixels_changed'});
 assert.equal(result[0].id,'error');assert.equal(result[0].match.exactError,true);
 assert.ok(result.every(x=>!('bindings' in x)));assert.equal(result.find(x=>x.id==='success').outcome,'candidate');
});

test('only current matching output may inherit authoritative acceptance or rejection',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'case-status-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const p=path.join(root,'out.pdf');fs.writeFileSync(p,'content');const sha=crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
 const item={outcome:'candidate',figureId:'F',outputSha256:sha},file={path:p,meta:{sha256:sha}};
 assert.equal(projectCaseOutcome(item,{status:'终检通过',outputs:[{file}]}),'approved');
 assert.equal(projectCaseOutcome(item,{status:'异常',feedback:{needsRevision:true},outputs:[{file}]}),'rejected');
 assert.equal(projectCaseOutcome(item,{status:'终检通过',outputs:[{file:{meta:{sha256:'other'}}}]}),'superseded');
 fs.writeFileSync(p,'changed');assert.equal(projectCaseOutcome(item,{status:'终检通过',outputs:[{file}]}),'historical_unverified');
});

test('failure blocks only identical engine, source, method and binding fingerprint',()=>{
 const prior={outcome:'failure',guard:{sourceSha256:'a',engineSignature:'v',operation:'vector-reletter',bindingSha256:'b'}};
 assert.equal(shouldBlockIdenticalAttempt(prior,{sourceSha256:'a',engineSignature:'v',operation:'vector-reletter',bindingSha256:'b'}),true);
 assert.equal(shouldBlockIdenticalAttempt(prior,{sourceSha256:'a',engineSignature:'v',operation:'vector-reletter',bindingSha256:'different'}),false);
 assert.equal(shouldBlockIdenticalAttempt(prior,{sourceSha256:'a',engineSignature:'v2',operation:'vector-reletter',bindingSha256:'b'}),false);
});

test('workbench case quality changes only for matching current figure and bytes',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const {casesFromWorkbench}=await import('./figure-case-index.mjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'case-live-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const p=path.join(root,'out.pdf');fs.writeFileSync(p,'candidate');const sha=crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
 const row={id:'F',number:'2',type:'统计曲线图',status:'待终检',outputs:[{number:'2',file:{path:p,meta:{sha256:sha}}}],productionRoute:{processing:{operation:'chart-redraw',basis:'source-bound'},sourceReview:{selected:{path:'input.svg'}}}};
 assert.equal(casesFromWorkbench([row])[0].outcome,'candidate');
 row.status='终检通过';assert.equal(casesFromWorkbench([row])[0].outcome,'approved');
 row.status='异常';row.feedback={needsRevision:true};assert.equal(casesFromWorkbench([row])[0].outcome,'rejected');
 fs.writeFileSync(p,'changed');assert.equal(casesFromWorkbench([row]).length,0);
});

test('structured failures and delivered candidates create evidence-bound reusable case events',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const {recordFailureCase,recordDeliveryCases,loadCaseEvents}=await import('./figure-case-index.mjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'case-events-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const ref=(name,body)=>{let p=path.join(root,name);fs.writeFileSync(p,body);return {path:p,sha256:crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')}};
 const source=ref('source.pdf','source'),out=ref('output.pdf','output'),spec=ref('spec.json',JSON.stringify({assets:[{source_vector_body:true,path:source.path,clip:[0,0,1,1],text_replacements:[{source_text:'a',source_bbox:[0,0,1,1]}]}]}));
 const plan={qualityRoute:'source-preserving-chart',render:[{spec,sourceRoot:root}],outputRoutes:[{number:'2',productionRoute:{processing:{operation:'chart-redraw',basis:'checked'},requirements:{widthMm:80},sourceReview:{selected:source,word:{sha256:'word'},archive:{sha256:'batch'}}}}]};
 const dir=path.join(root,'events'),error={stdout:JSON.stringify({status:'blocked',error:{code:'source_icon_pixels_changed',message:'changed'}})};
 const a=recordFailureCase(dir,{figureId:'F',plan,error,stage:'render',engineSignature:'v'});
 assert.equal(recordFailureCase(dir,{figureId:'F',plan,error,stage:'render',engineSignature:'v'}),a);
 assert.equal(recordFailureCase(dir,{figureId:'F',plan,error:{message:'network'},stage:'publish',engineSignature:'v'}),null);
 recordDeliveryCases(dir,{figure:{id:'F',articleId:'A'},plan,outputs:[{number:'2',...out}]});
 const row={id:'F',status:'终检通过',outputs:[{number:'2',file:{path:out.path,meta:{sha256:out.sha256}}}]};
 const cases=loadCaseEvents(dir,[row]).cases;
 assert.ok(cases.some(c=>c.outcome==='approved'));assert.ok(cases.some(c=>c.outcome==='failure'&&c.guard?.sourceSha256===source.sha256));
});
test('a resolved failure is active again if its resolution evidence changes',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const {recommendCases}=await import('./figure-case-index.mjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'case-resolution-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const proof=path.join(dir,'proof.txt'),old=path.join(dir,'old.txt'),index=path.join(dir,'index.json');fs.writeFileSync(proof,'fixed');fs.writeFileSync(old,'failed');
 const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
 fs.writeFileSync(index,JSON.stringify({version:1,cases:[{id:'x',outcome:'failure',resolved:true,errorCode:'E',features:{format:'pdf'},entry:'gray',evidence:{path:old,sha256:sha(old)},resolutionEvidence:{path:proof,sha256:sha(proof)}}]}));
 const check=()=>recommendCases({registryPath:index,features:{format:'pdf',errorCode:'E'}}).byOutcome;
 assert.equal(check().resolvedFailure.length,1);assert.equal(check().failure.length,0);
 fs.writeFileSync(proof,'changed');assert.equal(check().resolvedFailure.length,0);assert.equal(check().failure.length,1);
});
test('a structured tool failure automatically searches known methods by exact error',async t=>{
 const fs=await import('node:fs'),os=await import('node:os'),path=await import('node:path'),crypto=await import('node:crypto');
 const {searchFailureAlternatives}=await import('./figure-case-index.mjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'failure-search-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const proof=path.join(dir,'evidence'),registry=path.join(dir,'cases.json');fs.writeFileSync(proof,'evidence');
 const sha=crypto.createHash('sha256').update(fs.readFileSync(proof)).digest('hex');
 fs.writeFileSync(registry,JSON.stringify({version:1,cases:[{id:'method',outcome:'intermediate',features:{format:'pdf'},errorCode:'source_icon_pixels_changed',entry:'existing tool',evidence:{path:proof,sha256:sha}}]}));
 const result=searchFailureAlternatives({registryPath:registry,error:{stdout:JSON.stringify({error:{code:'source_icon_pixels_changed'}})},plan:{outputRoutes:[{productionRoute:{sourceReview:{selected:{path:'a.pdf'}}}}]}});
 assert.equal(result.status,'searched');assert.equal(result.recommendations.cases[0].id,'method');assert.equal(result.recommendations.cases[0].match.exactError,true);
});
