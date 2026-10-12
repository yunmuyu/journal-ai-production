import test from 'node:test';
import assert from 'node:assert/strict';
import {authorState,queueState,routeFor,buildWorkspace,figureType} from './workspace.mjs';
test('返工优先，部分通过及空文章不能封存',()=>{
 const figures=(...states)=>states.map(status=>({status}));
 assert.equal(authorState(figures('终检通过','待制作')),'制作中');
 assert.equal(authorState(figures('待终检','待制作')),'制作中');
 assert.equal(authorState(figures('待终检','暂缓')),'制作中');
 assert.equal(authorState(figures('待终检','终检通过')),'待终检');
 assert.equal(authorState(figures('待终检','待终检')),'待终检');
 assert.equal(authorState(figures('待终检','待修订')),'待修订');
 assert.equal(authorState(figures('待终检','异常')),'制作中');
 assert.equal(authorState(figures('终检通过','暂缓')),'制作中');
 assert.equal(authorState(figures('终检通过','终检通过')),'全部通过');
 assert.equal(authorState([]),'未完成');
});
test('未知源结构不从native-render猜为统计图',()=>{
 assert.equal(routeFor({route:'native-render',sourceAi:'F:/作者/图1.svg'}),null);
 assert.equal(routeFor({route:'native-render',sourceAi:'C:/work/statistics-batch-20261009-01/sources/A/图2.svg'}),'matplotlib');
 assert.equal(queueState({status:'待制作'}),'待预检');
 assert.equal(queueState({status:'待修订'}),'待返工');
});
test('能力视图复用逐图验收，队列保留反馈且不修改输入',()=>{
 const rows=[{id:'A-one-F1',author:'甲',number:'1',status:'待修订',feedback:{text:'对齐',attachments:[{path:'x'}]}},{id:'A-one-F2',author:'甲',number:'2',status:'终检通过'}];
 const production={figures:{'A-one-F1':{route:'image'},'A-one-F2':{route:'image'}}};
 const before=JSON.stringify([rows,production]);
 const workspace=buildWorkspace(rows,production,()=>null);
 assert.equal(workspace.queue.length,1);
 assert.equal(workspace.queue[0].reason,'对齐');
 assert.equal(workspace.queue[0].attachments,1);
 assert.equal(workspace.capabilities.find(c=>c.id==='image').cases.filter(c=>c.status==='终检通过').length,1);
 assert.equal(JSON.stringify([rows,production]),before);
 assert.equal(workspace.experiments.find(e=>e.name==='人工修改自动学习').stage,'暂不开发');
});

test('图类型采用已核对结构，普通文件扩展名不能猜图型',()=>{
 assert.equal(figureType({caption:'结果图'},{route:'native-render'}),'待分类');
 assert.equal(figureType({caption:'结构图'},{},{type:'vector hardware block diagram'}),'流程与框图');
 assert.equal(figureType({caption:'结果图'},{},{type:'circuit diagram'}),'电路图');
 assert.equal(figureType({caption:'散点图'}),'统计图');
 assert.equal(figureType({caption:'实验图'},{},{type:'photograph'}),'照片与截图');
});
