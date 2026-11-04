import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {verifyProcessingEvidence,assertRebuildLayout,verifyOperation} from './processing-evidence.mjs';
import {routeFixture,testRef} from './route-test-fixture.mjs';
import {verifyProductionResult} from './production-route.mjs';
import {verifyImportedPdfCandidate} from './imported-pdf.mjs';

function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'processing-gate-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const sourceRoot=path.join(root,'source');fs.mkdirSync(sourceRoot);
 const route=routeFixture(sourceRoot),pdf=path.join(root,'unchanged.pdf');fs.writeFileSync(pdf,'%PDF-1.7 old editable source');
 return {task:{id:'fixture',attemptDir:root,productionRoute:route,outputNumbers:['7']},outputs:[{number:'7',...testRef(pdf)}]};
}

test('vector legend groups bind every text fragment without weakening coverage',()=>{
 const sha='a'.repeat(64),ids=['tick','title','legend','suffix'];
 const entry={text_id:'legend',text_ids:['legend','suffix'],series_path_index:1,series_marker_index:2,swatch_path_index:3,swatch_marker_index:4};
 const spec={kind:'scene',legend_review:{present:true,source_sha256:sha,reason:'native split label',entries:[entry]}};
 const texts=ids.map((id,i)=>({id,text:id,role:['axis-tick','axis-title','legend-label','legend-label'][i]}));
 const report={layout:{texts,layout_evidence:{chart_vector_layout:{source_geometry_verified:true,source_sha256:sha,legend_bindings:[structuredClone(entry)]}}},pdf_audit:{chart_vector_layout:{passed:true,source_sha256:sha,curve_data_reconstructed:false,legend_bindings_verified:1}},assets:[{source_hash:sha,preparation_mode:'source-vector-reletter',source_path_multiset_preserved:true,text_replacements:ids.map(id=>({target_text_id:id,source_text:id}))}]};
 const requirement={operation:'chart-redraw',targetTextIds:ids};
 assert.doesNotThrow(()=>verifyOperation(requirement,spec,report,sha));
 for(const alter of [r=>r.layout.texts.pop(),r=>r.layout.layout_evidence.chart_vector_layout.legend_bindings[0].text_ids.reverse(),r=>r.pdf_audit.chart_vector_layout.legend_bindings_verified=0]){
  const bad=structuredClone(report);alter(bad);assert.throws(()=>verifyOperation(requirement,spec,bad,sha),/图例/);
 }
});
test('real grouping containers may hold child frames or source assets',()=>{
 const layout={nodes:[{id:'group',container:true,rect:[0,0,100,80]}],texts:[{id:'group:text',owner:'group'}]};
 assert.throws(()=>assertRebuildLayout({layout}),/ordinary_box_container/);
 assert.doesNotThrow(()=>assertRebuildLayout({layout:{...layout,nodes:[...layout.nodes,{id:'child',rect:[10,20,90,70]}]}}));
 assert.doesNotThrow(()=>assertRebuildLayout({layout:{...layout,assets:[{rect:[10,20,90,70]}]}}));
});
test('ordinary PDF return cannot use file format as proof of editorial processing',t=>{
 const {task,outputs}=fixture(t);
 assert.throws(()=>verifyProductionResult(task,{outputs}),/加工要求/);
});
test('imported PDF return cannot omit the required editorial operation',t=>{
 const {task}=fixture(t);
 assert.throws(()=>verifyImportedPdfCandidate(task,{},{}),/加工要求/);
});
test('declaring rebuild without public generator evidence cannot import an old PDF',t=>{
 const {task}=fixture(t);task.productionRoute.processing={operation:'rebuild',basis:'User requires the shared flowchart generator'};
 assert.throws(()=>verifyImportedPdfCandidate(task,{},{}),/加工证据/);
});
test('JPG preservation cannot omit a processing decision or bypass a lettering requirement',t=>{
 const {task,outputs}=fixture(t);task.productionRoute=routeFixture(path.join(task.attemptDir,'source'),{raster:true});
 assert.throws(()=>verifyProductionResult(task,{outputs}),/加工要求/);
 task.productionRoute.processing={operation:'raster-reletter',basis:'Replace labels'};
 assert.throws(()=>verifyProductionResult(task,{outputs}),/换字/);
});

test('real ordinary text box cannot evade measured padding by declaring itself a container',{skip:!process.env.WORKSPACE_TEST_PYTHON||!process.env.JFW_TEST_FONT_PROFILE},t=>{
 const {task}=fixture(t),root=task.attemptDir,python=process.env.WORKSPACE_TEST_PYTHON;
 task.productionRoute.processing={operation:'rebuild',basis:'Compact ordinary block diagram required'};
 const spec={version:1,id:'bad-container',author:'fixture',kind:'scene',width_pt:110,height_pt:60,nodes:[{id:'box',text:'Input',rect:[5,5,105,55],container:true}],sources:[task.productionRoute.sourceReview.selected],policy:{column:'single',design_font_size_pt:8}};
 const input=path.join(root,'spec.json');fs.writeFileSync(input,JSON.stringify(spec));
 const engineRoot=fileURLToPath(new URL('../portable-production/direct-pdf/',import.meta.url));
 execFileSync(python,['-m','journal_pdf','render',input,'--source-root',path.join(root,'source'),'--profile',process.env.JFW_TEST_FONT_PROFILE,'--output',path.join(root,'output')],{cwd:engineRoot,env:{...process.env,PYTHONPATH:engineRoot,PYTHONUTF8:'1'},encoding:'utf8',windowsHide:true});
 const folder=path.join(root,'output','fixture','bad-container'),outputs=[{number:'7',...testRef(path.join(folder,'bad-container.pdf'))}],evidence=[{number:'7',report:testRef(path.join(folder,'report.json')),spec:testRef(path.join(folder,'figure.spec.json'))}];
 assert.throws(()=>verifyProcessingEvidence(task,outputs,evidence,{python}),/ordinary_box_container/);
});

test('real shared generator evidence passes, but another PDF and changed requirements do not',{skip:!process.env.WORKSPACE_TEST_PYTHON||!process.env.JFW_TEST_FONT_PROFILE},t=>{
 const {task,outputs:oldOutputs}=fixture(t),root=task.attemptDir;
 task.productionRoute.processing={operation:'rebuild',basis:'Synthetic regression requires shared diagram layout'};
 const spec={version:1,id:'proof',author:'fixture',kind:'tree',root:'输入',branches:[{text:'输出',children:['检查']}],sources:[task.productionRoute.sourceReview.selected],policy:{column:'single',design_font_size_pt:8,export_crop_padding_pt:4}};
 const input=path.join(root,'spec.json');fs.writeFileSync(input,JSON.stringify(spec));
 const engineRoot=fileURLToPath(new URL('../portable-production/direct-pdf/',import.meta.url)),python=process.env.WORKSPACE_TEST_PYTHON;
 execFileSync(python,['-m','journal_pdf','render',input,'--source-root',path.join(root,'source'),'--profile',process.env.JFW_TEST_FONT_PROFILE,'--output',path.join(root,'output')],{cwd:engineRoot,env:{...process.env,PYTHONPATH:engineRoot,PYTHONUTF8:'1'},encoding:'utf8',windowsHide:true});
 const folder=path.join(root,'output','fixture','proof'),outputs=[{number:'7',...testRef(path.join(folder,'proof.pdf'))}];
 const evidence=[{number:'7',report:testRef(path.join(folder,'report.json')),spec:testRef(path.join(folder,'figure.spec.json'))}];
 assert.equal(verifyProcessingEvidence(task,outputs,evidence,{python})[0].operation,'rebuild');
 assert.throws(()=>verifyProcessingEvidence(task,oldOutputs,evidence,{python}),/加工报告/);
 task.productionRoute.processing.operation='vector-reletter';
 assert.throws(()=>verifyProcessingEvidence(task,outputs,evidence,{python}),/换字/);
 task.productionRoute.processing.operation='rebuild';
 fs.appendFileSync(evidence[0].spec.path,' ');
 assert.throws(()=>verifyProcessingEvidence(task,outputs,evidence,{python}),/哈希/);
});
test('mixed vector reletter requires image and vector preservation in final PDF',()=>{
 const sha='a'.repeat(64),requirements={operation:'vector-reletter',targetTextIds:['a']},spec={kind:'scene'};
 const body={id:'body',mode:'source-mixed-body',source_hash:sha,noncolor_geometry_and_style_exact:true,original_image_placements_preserved:true,original_smask_preserved:true,font_count:0,source_text_character_count:0,image_instance_count:1,text_replacements:[{source_text:'A',target_text_id:'a'}]};
 const report={assets:[body],layout:{texts:[{id:'a',text:'A'}]},pdf_audit:{neutral_rgb_300dpi:true,text_multiset_exact:true,source_path_ownership:{source_geometry_and_style_exact:true,bindings:[{id:'body',mode:'source-mixed-body',source_sha256:sha}]},source_image_ownership:{bidirectional_instance_multiset_exact:true,original_smask_exact:true,derived_grayscale_pixels_exact:true,matched_instance_count:1,expected_instance_count:1}}};
 assert.doesNotThrow(()=>verifyOperation(requirements,spec,report,sha));
 for(const change of [r=>r.pdf_audit.source_image_ownership.matched_instance_count=0,r=>r.assets[0].noncolor_geometry_and_style_exact=false,r=>r.pdf_audit.neutral_rgb_300dpi=false,r=>r.pdf_audit.source_path_ownership.bindings[0].source_sha256='b'.repeat(64)]){const invalid=structuredClone(report);change(invalid);assert.throws(()=>verifyOperation(requirements,spec,invalid,sha),/保留源图形/);}
});
