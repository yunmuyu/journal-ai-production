import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createDecisionStore} from './decision-store.mjs';

const names=['sourceMatch','method','columns','split','contentTypes','preflight'];
function fixture(t,unknown=[]){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'decision-store-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const recordsPath=path.join(dir,'production-results.json'),pilotPath=path.join(dir,'pilot.json');
 const fields=Object.fromEntries(names.map(name=>[name,{value:name==='split'?'不拆分':`${name}已核对`,certainty:unknown.includes(name)?'unknown':'verified',basis:'样例资料'}]));
 const figure={id:'f1',author:'作者',number:'图1',aiProposal:{version:'v1',sourceFingerprint:'sha-one',fields}};
 fs.writeFileSync(pilotPath,JSON.stringify({schemaVersion:1,figures:[figure],cases:[]}));
 const production={status:'已验收',output:'existing.pdf',userFeedback:{text:'保留'},userAcceptance:{accepted:true}};
 fs.writeFileSync(recordsPath,JSON.stringify({figures:{f1:production},articles:{keep:true}}));
 return {store:createDecisionStore({recordsPath,pilotPath}),recordsPath,pilotPath,fields,production,
  input:{revision:0,proposalVersion:'v1',action:'confirm',fields:Object.fromEntries(names.map(name=>[name,fields[name].value])),resolutions:{}}};
}
const records=path=>JSON.parse(fs.readFileSync(path,'utf8'));

test('原建议确认后保留生产和反馈字段，历史记录可追溯',t=>{
 const f=fixture(t);
 const result=f.store.save('f1',f.input);
 assert.equal(result.state,'confirmed');
 assert.equal(result.semanticReview,'not-required');
 assert.equal(result.userConfirmed,true);
 assert.equal(result.history[0].sourceFingerprint,'sha-one');
 assert.deepEqual(result.aiProposal.fields,f.fields);
 const saved=records(f.recordsPath);
 assert.deepEqual({...saved.figures.f1,productionDecision:undefined},{...f.production,productionDecision:undefined});
 assert.equal(saved.articles.keep,true);
 assert.deepEqual(f.store.read().figures[0].aiProposal.fields,f.fields);
});

test('修改一项或多项后的确认留待语义复核',t=>{
 const f=fixture(t);
 f.input.fields.method='用户核定的方法';
 const first=f.store.save('f1',f.input);
 assert.equal(first.state,'needs-review');
 assert.equal(first.semanticReview,'pending');
 assert.deepEqual(first.changes,[{field:'method',from:'method已核对',to:'用户核定的方法'}]);
 const second=f.store.save('f1',{...f.input,revision:1,fields:{...f.input.fields,columns:'双栏'}});
 assert.equal(second.changes.length,2);
 assert.equal(second.history.length,2);
});

test('未知建议确认时要求明确修改或消歧说明，草稿可保存',t=>{
 const f=fixture(t,['method']);
 assert.throws(()=>f.store.save('f1',f.input),{status:422,fields:['method']});
 const draft=f.store.save('f1',{...f.input,action:'draft'});
 assert.equal(draft.state,'draft');
 const resolved=f.store.save('f1',{...f.input,revision:1,resolutions:{method:'作者原稿第3页明确写明'}});
 assert.equal(resolved.userConfirmed,true);
 assert.equal(resolved.state,'needs-review');
 assert.equal(resolved.semanticReview,'pending');
 assert.throws(()=>f.store.save('f1',{...f.input,revision:2,fields:{...f.input.fields,method:'待确认'}}),{status:422});
});

test('未知建议改成明确值可确认，明显图源错误和拆分缺规格会被拦截',t=>{
 const f=fixture(t,['method']);
 const changed={...f.input.fields,method:'作者确认使用散点图'};
 assert.equal(f.store.save('f1',{...f.input,fields:changed}).state,'needs-review');
 assert.throws(()=>f.store.save('f1',{...f.input,revision:1,fields:{...changed,sourceMatch:'图源不匹配'}}),{status:422,fields:['sourceMatch']});
 assert.throws(()=>f.store.save('f1',{...f.input,revision:1,fields:{...changed,split:'拆分2张'}}),{status:422,fields:['split']});
});

test('暂缓与重核保留为不同决策，不改变生产状态',t=>{
 const f=fixture(t);
 assert.equal(f.store.save('f1',{...f.input,action:'defer'}).state,'deferred');
 assert.equal(f.store.save('f1',{...f.input,revision:1,action:'recheck'}).state,'needs-review');
 assert.equal(records(f.recordsPath).figures.f1.status,'已验收');
});

test('读取刷新后的建议并将旧决策标为过期',t=>{
 const f=fixture(t);
 f.store.save('f1',f.input);
 const pilot=records(f.pilotPath);
 pilot.figures[0].aiProposal.version='v2';
 fs.writeFileSync(f.pilotPath,JSON.stringify(pilot));
 const figure=f.store.read().figures[0];
 assert.equal(figure.aiProposal.version,'v2');
 assert.equal(figure.decision.state,'stale');
 assert.equal(figure.decision.stale,true);
 assert.throws(()=>f.store.save('f1',{...f.input,revision:1}),{status:409});
 pilot.figures[0].aiProposal.version='v1';
 pilot.figures[0].aiProposal.sourceFingerprint='sha-two';
 fs.writeFileSync(f.pilotPath,JSON.stringify(pilot));
 assert.equal(f.store.read().figures[0].decision.state,'stale');
});

test('旧revision、未知图件与非法字段分别失败',t=>{
 const f=fixture(t);
 assert.throws(()=>f.store.save('absent',f.input),{status:404});
 assert.throws(()=>f.store.save('f1',{...f.input,unexpected:true}),{status:400});
 f.store.save('f1',f.input);
 assert.throws(()=>f.store.save('f1',f.input),{status:409});
});

test('与反馈共用写锁，锁占用时不写生产记录',t=>{
 const f=fixture(t),before=fs.readFileSync(f.recordsPath,'utf8');
 fs.writeFileSync(f.recordsPath+'.feedback.lock','held');
 assert.throws(()=>f.store.save('f1',f.input),{status:409});
 assert.equal(fs.readFileSync(f.recordsPath,'utf8'),before);
 fs.unlinkSync(f.recordsPath+'.feedback.lock');
});

test('新增图件仅写入制作决策',t=>{
 const f=fixture(t),pilot=records(f.pilotPath);
 pilot.figures.push({...pilot.figures[0],id:'f2'});
 fs.writeFileSync(f.pilotPath,JSON.stringify(pilot));
 f.store.save('f2',f.input);
 assert.deepEqual(Object.keys(records(f.recordsPath).figures.f2),['productionDecision']);
});
