import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createDecisionStore} from './decision-store.mjs';
import {ATTRIBUTE_OPTIONS,normalizeAttribute} from './decision-attributes.mjs';

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
 assert.throws(()=>f.store.save('f1',f.input),error=>error.status===422&&error.message.includes('制作方法'));
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
 assert.equal(records(f.recordsPath).figures.f1.productionDecision.semanticReview,'pending');
 assert.equal(records(f.recordsPath).figures.f1.status,'已验收');
});

test('新增未知措辞阻止确认，但制作后核验属于执行说明',t=>{
 const f=fixture(t);
 for(const value of ['待人工决定','待核对','未核实','证据不够'])
  assert.throws(()=>f.store.save('f1',{...f.input,fields:{...f.input.fields,method:value}}),{status:422,fields:['method']});
 assert.equal(f.store.save('f1',{...f.input,fields:{...f.input.fields,preflight:'制作后核验'}}).state,'needs-review');
});

test('可选源文件哈希变更或不可读取时拒绝保存',t=>{
 const f=fixture(t),sourcePath=path.join(path.dirname(f.pilotPath),'source.txt');
 fs.writeFileSync(sourcePath,'original');
 const sha256=createHash('sha256').update(fs.readFileSync(sourcePath)).digest('hex');
 const pilot=records(f.pilotPath);
 pilot.figures[0].sourceFiles=[{path:sourcePath,sha256}];
 fs.writeFileSync(f.pilotPath,JSON.stringify(pilot));
 assert.equal(f.store.save('f1',f.input).state,'confirmed');
 fs.writeFileSync(sourcePath,'changed');
 assert.throws(()=>f.store.save('f1',{...f.input,revision:1}),error=>error.status===409&&error.message.includes('源文件'));
 fs.unlinkSync(sourcePath);
 assert.throws(()=>f.store.save('f1',{...f.input,revision:1}),error=>error.status===409&&error.message.includes('不可读取'));
 assert.equal(records(f.recordsPath).figures.f1.productionDecision.revision,1);
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

test('属性归一化只接受能确定的枚举，含歧义返回待判断',()=>{
 assert.deepEqual(ATTRIBUTE_OPTIONS.columns,['小单栏','单栏','双栏','待判断']);
 assert.equal(normalizeAttribute('columns','图件按小单栏排版'),'小单栏');
 assert.equal(normalizeAttribute('columns','单栏或双栏均可'),'待判断');
 assert.equal(normalizeAttribute('method','建议矢量换字'),'矢量换字');
 assert.equal(normalizeAttribute('split','不拆分，整体交付'),'整体1张');
 assert.equal(normalizeAttribute('split','拆分3张及以上'),'拆3张及以上');
 assert.equal(normalizeAttribute('split','80/160 mm，输出数量待定'),'待判断');
 assert.equal(normalizeAttribute('split','拆分3张，规格80/160 mm'),'拆3张及以上');
});

test('三个属性独立保存且共享revision，六项字段与生产状态保持',t=>{
 const f=fixture(t),before=records(f.recordsPath);
 const first=f.store.save('f1',{revision:0,proposalVersion:'v1',action:'attribute-draft',attribute:'columns',value:'待判断'});
 assert.equal(first.attributes.columns.state,'draft');
 assert.equal(first.attributes.columns.originalAIValue,'待判断');
 const second=f.store.save('f1',{revision:1,proposalVersion:'v1',action:'attribute-confirm',attribute:'method',value:'矢量换字'});
 assert.equal(second.attributes.method.state,'confirmed');
 assert.deepEqual(second.attributes.columns,first.attributes.columns);
 assert.deepEqual(second.fields,f.input.fields);
 assert.deepEqual({...records(f.recordsPath).figures.f1,productionDecision:undefined},{...before.figures.f1,productionDecision:undefined});
 assert.throws(()=>f.store.save('f1',{revision:1,proposalVersion:'v1',action:'attribute-confirm',attribute:'split',value:'整体1张'}),{status:409});
});

test('只拦截当前属性未决，其他AI未知不影响明确分类确认',t=>{
 const f=fixture(t,['columns','method','split']);
 const base={revision:0,proposalVersion:'v1',action:'attribute-confirm',attribute:'method'};
 assert.throws(()=>f.store.save('f1',{...base,value:'待判断'}),{status:422,fields:['method']});
 assert.equal(f.store.save('f1',{...base,value:'PS直出'}).attributes.method.state,'confirmed');
 assert.equal(records(f.recordsPath).figures.f1.productionDecision.aiProposal.fields.columns.certainty,'unknown');
 assert.throws(()=>f.store.save('f1',{...base,revision:1,value:'随便写'}),{status:400});
});

test('加工方式变化无明确容量冲突时不推翻栏宽，只记录待Agent检查',t=>{
 const f=fixture(t);
 const columns=f.store.save('f1',{revision:0,proposalVersion:'v1',action:'attribute-confirm',attribute:'columns',value:'双栏'});
 const next=f.store.save('f1',{revision:1,proposalVersion:'v1',action:'attribute-confirm',attribute:'method',value:'完整重绘'});
 assert.deepEqual(next.attributes.columns,columns.attributes.columns);
 assert.equal(next.attributes.method.capacityCheck,'pending-agent');
 const confirmed=f.store.save('f1',{revision:2,proposalVersion:'v1',action:'attribute-confirm',attribute:'method',value:'完整重绘'});
 assert.equal(confirmed.attributes.method.capacityCheck,'pending-agent');
});

test('明确capacityEvidence冲突时只将已保存栏宽置为需复核',t=>{
 const f=fixture(t),pilot=records(f.pilotPath);
 pilot.figures[0].capacityEvidence={method:'完整重绘',allowedColumns:['小单栏','单栏'],basis:'已核对的版面容量',
  calculation:{columns:'双栏',requiredWidthMm:180,availableWidthMm:160}};
 fs.writeFileSync(f.pilotPath,JSON.stringify(pilot));
 f.store.save('f1',{revision:0,proposalVersion:'v1',action:'attribute-confirm',attribute:'columns',value:'双栏'});
 const result=f.store.save('f1',{revision:1,proposalVersion:'v1',action:'attribute-confirm',attribute:'method',value:'完整重绘'});
 assert.equal(result.attributes.columns.value,'双栏');
 assert.equal(result.attributes.columns.state,'needs-review');
 assert.equal(result.attributes.method.capacityCheck,'conflict');
 assert.equal(result.attributes.columns.history.at(-1).action,'capacity-conflict');
});

test('容量证据缺少计算或用户已明确指定栏宽时仅待Agent检查',t=>{
 const f=fixture(t),pilot=records(f.pilotPath);
 pilot.figures[0].capacityEvidence={method:'半重绘',allowedColumns:['单栏'],basis:'粗略判断'};
 fs.writeFileSync(f.pilotPath,JSON.stringify(pilot));
 f.store.save('f1',{revision:0,proposalVersion:'v1',action:'attribute-confirm',attribute:'columns',value:'双栏'});
 const noCalculation=f.store.save('f1',{revision:1,proposalVersion:'v1',action:'attribute-confirm',attribute:'method',value:'半重绘'});
 assert.equal(noCalculation.attributes.columns.state,'confirmed');
 assert.equal(noCalculation.attributes.method.capacityCheck,'pending-agent');
 pilot.figures[0].capacityEvidence={...pilot.figures[0].capacityEvidence,method:'完整重绘',userSpecifiedColumns:true,
  calculation:{columns:'双栏',requiredWidthMm:180,availableWidthMm:160}};
 fs.writeFileSync(f.pilotPath,JSON.stringify(pilot));
 const explicit=f.store.save('f1',{revision:2,proposalVersion:'v1',action:'attribute-confirm',attribute:'method',value:'完整重绘'});
 assert.equal(explicit.attributes.columns.state,'confirmed');
 assert.equal(explicit.attributes.method.capacityCheck,'pending-agent');
});

test('草稿撤销可回待判断，按operationId保留操作链',t=>{
 const f=fixture(t),base={proposalVersion:'v1',action:'attribute-draft',attribute:'split'};
 const first=f.store.save('f1',{...base,revision:0,value:'拆2张',operationId:'drag-1'});
 const undone=f.store.save('f1',{...base,revision:1,value:'待判断',operationId:'undo:drag-1'});
 const history=undone.attributes.split.history;
 assert.equal(history[0].before,'整体1张');
 assert.equal(history[0].value,'拆2张');
 assert.equal(history[0].operationId,'drag-1');
 assert.equal(history[1].op,'undo:drag-1');
 assert.equal(history[1].before,'拆2张');
 assert.equal(undone.attributes.split.state,'draft');
 assert.deepEqual(first.fields,undone.fields);
 assert.throws(()=>f.store.save('f1',{...base,action:'attribute-confirm',revision:2,value:'待判断'}),{status:422});
 assert.throws(()=>f.store.save('f1',{...base,revision:2,value:'整体1张',operationId:'x'.repeat(101)}),{status:400});
});

test('旧六项操作继续保留已审核属性',t=>{
 const f=fixture(t);
 const first=f.store.save('f1',{revision:0,proposalVersion:'v1',action:'attribute-confirm',attribute:'split',value:'整体1张'});
 const next=f.store.save('f1',{...f.input,revision:1});
 assert.deepEqual(next.attributes,first.attributes);
 assert.equal(next.state,'confirmed');
});

 test('真实旧字段文本可归一化，规格数字不冒充输出数量',()=>{
 assert.equal(normalizeAttribute('method','PS直接处理：保留像素'),'PS直出');
 assert.equal(normalizeAttribute('method','局部重排：保留模块'),'半重绘');
 assert.equal(normalizeAttribute('split','拆分为 2 张；每张80 mm'),'拆2张');
 assert.equal(normalizeAttribute('split','整体 1 张；80 mm'),'整体1张');
 assert.equal(normalizeAttribute('split','80 mm / 160 mm'),'待判断');
 });
