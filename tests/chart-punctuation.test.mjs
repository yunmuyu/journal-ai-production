import test from 'node:test';
import assert from 'node:assert/strict';
import {chartLabels} from '../lib/outlined-chart.mjs';
test('Chinese chart explanations use fullwidth parentheses without changing English or formulas',()=>{
 const labels=chartLabels({pageSizePt:[250,200],plotBoundsPt:[36,14,212,160],sourceScale:1,labels:[{text:'理想线 (y=x)',role:'legend',x:100,y:120},{text:'模型（测试）',role:'legend',x:100,y:130},{text:'Baseline (y=x)',role:'legend',x:100,y:140},{text:'(x+y)/2',role:'annotation',x:100,y:50},{text:'测量值 (°C)',role:'x-title',x:100,y:180}]});
 assert.deepEqual(labels.map(t=>t.text),['理想线（y=x）','模型（测试）','Baseline (y=x)','(x+y)/2','测量值/°C']);
 assert.deepEqual(labels[0].styles.map(s=>s.start),[4,6]);
});
test('retain metric headings but omit explicit subfigure captions',()=>{
 const labels=chartLabels({pageSizePt:[250,200],plotBoundsPt:[36,14,212,160],sourceScale:1,labels:[{text:'train/loss',role:'panel-title',x:90,y:7},{text:'metrics/accuracy_top1',role:'panel-title',x:90,y:7},{text:'（a）训练损失对比',role:'panel-title',x:90,y:7}]});
 assert.deepEqual(labels.map(t=>t.text),['train/loss','metrics/accuracy_top1']);
 assert.ok(labels.every(t=>t.align==='center'&&t.y===7/200));
});