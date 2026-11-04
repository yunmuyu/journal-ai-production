import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {prepareClassificationEvidence,assertConfirmedRoute,productionTaskGroup} from './production-admission.mjs';

function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'bound-classification-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const ref=key=>{const p=path.join(root,key);fs.writeFileSync(p,key);return {path:p,sha256:createHash('sha256').update(key).digest('hex')};};
 const figure={id:'F1',reviewVersion:'v1',type:'统计曲线图'};
 const plan={baseVersion:'v1',outputRoutes:[{number:'1',productionRoute:{method:'editable-pdf',processing:{operation:'rebuild'},sourceReview:Object.fromEntries(['archive','word','selected'].map(k=>[k,ref(k)]))}}]};
 return {root,figure,plan};
}

test('source-bound semantic classification corrects an old chart heuristic without disabling its guard',t=>{
 const {root,figure,plan}=fixture(t);
 assert.throws(()=>assertConfirmedRoute(figure,plan),/chart_processing_conflict/);
 plan.classificationEvidence=prepareClassificationEvidence(figure,plan,{kind:'diagram',basis:'Source contains process nodes and directed links; Word caption identifies a retrieval pipeline.'},path.join(root,'classification.json'));
 assert.doesNotThrow(()=>assertConfirmedRoute(figure,plan));
 assert.equal(productionTaskGroup(figure,plan),'流程与结构图 / 保留语义重排');
 assert.throws(()=>assertConfirmedRoute({...figure,reviewVersion:'v2'},plan),/classification_evidence_invalid/);
 fs.appendFileSync(plan.outputRoutes[0].productionRoute.sourceReview.selected.path,'changed');
 assert.throws(()=>assertConfirmedRoute(figure,plan),/classification_source_changed/);
});

test('chart correction still requires chart processing and cannot authorize raster preservation',t=>{
 const {root,figure,plan}=fixture(t);figure.type='流程与结构图';
 plan.classificationEvidence=prepareClassificationEvidence(figure,plan,{kind:'chart',basis:'Source contains axes, measured curve series and numeric ticks.'},path.join(root,'classification.json'));
 assert.equal(productionTaskGroup(figure,plan),'统计曲线图 / 保留图形换字');
 assert.throws(()=>assertConfirmedRoute(figure,plan),/chart_processing_conflict/);
 plan.outputRoutes[0].productionRoute.processing.operation='chart-redraw';
 assert.doesNotThrow(()=>assertConfirmedRoute(figure,plan));
 plan.outputRoutes[0].productionRoute.processing.operation='preserve';
 assert.throws(()=>assertConfirmedRoute(figure,plan),/chart_preserve_conflict/);
});

test('agent semantic correction cannot override a confirmed user classification',t=>{
 const {root,figure,plan}=fixture(t);
 figure.decision={attributes:{kind:{state:'confirmed',value:'统计图表'}}};
 assert.throws(()=>prepareClassificationEvidence(figure,plan,{kind:'diagram',basis:'different classification'},path.join(root,'classification.json')),/classification_confirmed_conflict/);
 assert.equal(fs.existsSync(path.join(root,'classification.json')),false);
});
