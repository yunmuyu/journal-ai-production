import test from 'node:test';
import assert from 'node:assert/strict';
import {comparison,timingRow,buildProgress} from './progress.mjs';
test('暖机一轮变快不能冒称稳定提速',()=>{
 const r=comparison([{round:1,mode:'original',durationMs:85384},{round:1,mode:'candidate',durationMs:46363},{round:2,mode:'candidate',durationMs:43646},{round:2,mode:'original',durationMs:42224}]);
 assert.equal(r.consistentImprovement,false);assert.equal(r.rounds.length,2);
});
test('加工耗时不冒充总耗时与首次通过率，保留缓存标记',()=>{
 const r=timingRow({articleId:'A-1',author:'甲',number:'2.1',result:{durationMs:1000,cached:true}});
 assert.equal(r.processingMs,1000);assert.equal(r.totalMs,null);assert.equal(r.reworkCount,null);assert.equal(r.firstPassRate,null);assert.equal(r.cached,true);
 assert.equal(timingRow({result:{}}),null);
});
test('优先顺序来自权威inventory，读视图不改变生产记录',()=>{
 const inventory={articles:[{id:'A-2',author:'乙',productionPriority:{rank:2,nextStep:'第二'}},{id:'A-1',author:'甲',productionPriority:{rank:1,nextStep:'第一'}}]};
 const rows=[{articleId:'A-1',number:'1',status:'终检通过'}],before=JSON.stringify([inventory,rows]);
 const p=buildProgress(rows,inventory,()=>null,{project:'C:/__missing_workbench_test__'});
 assert.deepEqual(p.priorities.map(a=>a.author),['甲','乙']);assert.equal(p.priorities[0].figures[0].status,'终检通过');assert.equal(JSON.stringify([inventory,rows]),before);
});
