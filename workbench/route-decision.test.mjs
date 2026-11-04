import test from 'node:test';
import assert from 'node:assert/strict';
import {assertConfirmedRoute,assertStableRouteDecision,buildProductionQueue} from './production-admission.mjs';

const figure=(method,state='confirmed')=>({decision:{attributes:{method:{value:method,state}}}});
const plan=operation=>({outputRoutes:[{number:'1',productionRoute:{method:operation==='preserve'?'raster-preserve':'editable-pdf',processing:{operation}}}]});

test('confirmed full redraw rejects lettering or preservation before dispatch',()=>{
 for(const op of ['vector-reletter','raster-reletter','preserve'])
  assert.throws(()=>assertConfirmedRoute(figure('完整重绘'),plan(op)),/confirmed_route_conflict/);
 assert.doesNotThrow(()=>assertConfirmedRoute(figure('完整重绘'),plan('rebuild')));
});

test('unconfirmed proposals and absent decisions do not become mandatory rules',()=>{
 assert.doesNotThrow(()=>assertConfirmedRoute(figure('完整重绘','draft'),plan('vector-reletter')));
 assert.doesNotThrow(()=>assertConfirmedRoute({},plan('vector-reletter')));
});

test('each output must comply, and stale confirmed decisions cannot dispatch',()=>{
 const mixed=plan('rebuild');mixed.outputRoutes.push(...plan('vector-reletter').outputRoutes);
 assert.throws(()=>assertConfirmedRoute(figure('完整重绘'),mixed),/confirmed_route_conflict/);
 const stale=figure('完整重绘');stale.decision.stale=true;
 assert.throws(()=>assertConfirmedRoute(stale,plan('rebuild')),/confirmed_route_stale/);
});

test('queue holds the conflicting plan and leaves the next figure eligible for its own checks',()=>{
 const rows=[{...figure('完整重绘'),id:'one',reviewVersion:'v1'}, {id:'two',reviewVersion:'v1'}];
 const bad={...plan('vector-reletter'),figureId:'one',baseVersion:'v1'};
 const queue=buildProductionQueue({},[bad],rows);
 assert.equal(queue.held.length,2);
 assert.match(queue.held.find(row=>row.figureId==='one').reason,/confirmed_route_conflict/);
 assert.match(queue.held.find(row=>row.figureId==='two').reason,/plan_not_prepared/);
});

test('confirmed decision changes while rendering invalidate the result',()=>{
 assert.throws(()=>assertStableRouteDecision(figure('完整重绘'),figure('矢量换字')),/route_decision_changed/);
 assert.throws(()=>assertStableRouteDecision({},figure('完整重绘')),/route_decision_changed/);
 assert.doesNotThrow(()=>assertStableRouteDecision(figure('完整重绘'),figure('完整重绘')));
 assert.doesNotThrow(()=>assertStableRouteDecision(figure('完整重绘','draft'),figure('矢量换字','draft')));
});

test('explicit source-preserving chart requires chart processing before tools run',()=>{
 const p={...plan('vector-reletter'),qualityRoute:'source-preserving-chart'};
 assert.throws(()=>assertConfirmedRoute({},p),/chart_route_conflict/);
 p.outputRoutes[0].productionRoute.processing.operation='chart-redraw';
 assert.doesNotThrow(()=>assertConfirmedRoute({},p));
});

test('live chart classification cannot be downgraded by declaring raster quality',()=>{
 for(const type of ['统计曲线图 / 保留图形换字','柱状图','散点图']){
  assert.throws(()=>assertConfirmedRoute({type},{...plan('preserve'),qualityRoute:'raster'}),/chart_preserve_conflict/);
  assert.doesNotThrow(()=>assertConfirmedRoute({type},plan('chart-redraw')));
  assert.throws(()=>assertConfirmedRoute({type},plan('vector-reletter')),/chart_processing_conflict/);
 }
 assert.doesNotThrow(()=>assertConfirmedRoute({type:'截图照片 / 裁切灰度'},plan('preserve')));
 assert.doesNotThrow(()=>assertConfirmedRoute({type:'专业图 / 原图保护处理'},plan('vector-reletter')));
});
