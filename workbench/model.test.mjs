import test from 'node:test';
import assert from 'node:assert/strict';
import {classify,loadModel} from './model.mjs';
import fs from 'node:fs';
import {recordRoot} from './paths.mjs';
test('六类状态保留终检与内部复核区别',()=>{assert.equal(classify('内部复核通过'),'待终检');assert.equal(classify('用户最终验收通过'),'终检通过');assert.equal(classify('已修改待复核'),'异常');assert.equal(classify('暂留待确认'),'暂缓');assert.equal(classify('rendering'),'生产中');assert.equal(classify('生产已暂停'),'生产中');assert.equal(classify('待配对图源'),'待制作');});
test('真实主图和分图映射不重复计数',()=>{const {data,files}=loadModel();assert.equal(new Set(data.rows.map(r=>r.id)).size,data.rows.length);const z=data.rows.find(r=>r.author==='张琛'&&r.number==='2');const authority=JSON.parse(fs.readFileSync(recordRoot+'/production-results.json','utf8'));assert.equal(z.status,classify(authority.figures[z.id].status));assert.equal(z.outputs.length,4);assert.ok(z.outputs.every(o=>o.file));assert.ok(z.summary&&z.ai&&z.folder&&z.source);assert.equal(data.rows.find(r=>r.author==='叶林俊'&&r.number==='5').status,'终检通过');assert.equal(data.rows.find(r=>r.author==='李琪琪'&&r.number==='3').status,'待终检');assert.ok(files.size>100);});

