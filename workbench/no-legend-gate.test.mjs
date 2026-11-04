import test from 'node:test';import assert from 'node:assert/strict';import {verifyOperation} from './processing-evidence.mjs';
const sha='a'.repeat(64);
function scene(){return {spec:{kind:'scene',legend_review:{present:false,source_sha256:sha,reason:'reviewed no legend'}},report:{pdf_audit:{chart_vector_layout:{passed:true,source_sha256:sha,curve_data_reconstructed:false}},layout:{layout_evidence:{chart_vector_layout:{source_geometry_verified:true,source_sha256:sha}},texts:[{id:'x',role:'axis-tick',text:'1'},{id:'title',role:'axis-title',text:'Hz'}]},assets:[{source_hash:sha,preparation_mode:'source-vector-reletter',source_path_multiset_preserved:true,text_replacements:[{target_text_id:'x',source_text:'1'},{target_text_id:'title',source_text:'Hz'}]}]},route:{operation:'chart-redraw',targetTextIds:['x','title']}};}
test('source-bound no-legend vector chart preserves paths and complete text',()=>{const {spec,report,route}=scene();assert.doesNotThrow(()=>verifyOperation(route,spec,report,sha));});
test('unreviewed, wrong source, missing text and changed curves cannot pass',()=>{for(const defect of ['missing','source','curve','text','legend']){const {spec,report,route}=scene();if(defect==='missing')delete spec.legend_review;if(defect==='source')spec.legend_review.source_sha256='b'.repeat(64);if(defect==='curve')report.assets[0].source_path_multiset_preserved=false;if(defect==='text')report.layout.texts.pop();if(defect==='legend')report.layout.texts.push({id:'legend:x',role:'legend-label',text:'other'});assert.throws(()=>verifyOperation(route,spec,report,sha));}});
test('no-legend raster chart needs preserved viewport and source-bound review',()=>{const spec={kind:'chart',series:[],masks:[],legend_review:{present:false,source_sha256:sha,reason:'no legend'}},report={layout:{texts:[{id:'x',role:'axis-tick',text:'1'}]},assets:[{id:'plot',source_hash:sha,mode:'raster-protected-viewport',protected_pixels_unchanged_before_color_conversion:true}]};assert.doesNotThrow(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));spec.masks=[[0,0,1,1]];assert.throws(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));});
test('legend chart still requires each declared legend label',()=>{const spec={kind:'chart',series:[{id:'a',label:'A'}]},report={layout:{texts:[{role:'axis-tick',text:'1'}]},assets:[{id:'plot',source_hash:sha,mode:'raster-protected-viewport',protected_pixels_unchanged_before_color_conversion:true}]};assert.throws(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));report.layout.texts.push({id:'legend:a',role:'legend-label',text:'A'});assert.doesNotThrow(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));});

test('no-legend SVG chart preserves real geometry digest',()=>{const spec={kind:'chart',series:[],legend_review:{present:false,source_sha256:sha,reason:'no legend'}},report={layout:{texts:[{role:'axis-tick',text:'1'}]},assets:[{id:'plot',source_hash:sha,mode:'svg-vector-preserve',geometry_before:'c'.repeat(64),geometry_after:'c'.repeat(64)}]};assert.doesNotThrow(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));report.assets[0].geometry_after='d'.repeat(64);assert.throws(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));});

test('scene charts without generation and actual-PDF audit are rejected',()=>{const {spec,report,route}=scene();delete report.pdf_audit.chart_vector_layout;assert.throws(()=>verifyOperation(route,spec,report,sha),/最终PDF刻度间距/);});
test('chart axis lettering cannot bypass chart route as vector reletter',()=>{const {spec,report,route}=scene();route.operation='vector-reletter';assert.throws(()=>verifyOperation(route,spec,report,sha),/图表加工路线/);});
test('vector legend requires exact source bindings and a final legend audit',()=>{
 const {spec,report,route}=scene();
 const entry={text_id:'l',series_path_index:7,series_marker_index:8,swatch_path_index:9,swatch_marker_index:10};
 spec.legend_review={present:true,source_sha256:sha,reason:'source',entries:[entry]};
 report.layout.texts.push({id:'l',role:'legend-label',text:'A'});report.assets[0].text_replacements.push({target_text_id:'l',source_text:'A'});route.targetTextIds.push('l');
 report.layout.layout_evidence.chart_vector_layout.legend_bindings=[{...entry,source_swatch_center:[10,10],source_swatch_end:[12,10]}];
 report.pdf_audit.chart_vector_layout.legend_bindings_verified=1;
 assert.doesNotThrow(()=>verifyOperation(route,spec,report,sha));
 report.pdf_audit.chart_vector_layout.legend_bindings_verified=0;assert.throws(()=>verifyOperation(route,spec,report,sha));
});

test('bar chart delivery requires every source-bound bar value and section label',()=>{
 const labels=[{id:'b1',text_group:'text_1',bar_group:'p1'}],sections=[{id:'s1',text_group:'text_2'}];
 const spec={kind:'chart',series:[{id:'series',label:'S'}],bar_labels:labels,section_labels:sections};
 const report={pdf_audit:{numeric_grouping_in_actual_pdf:true},assets:[{id:'plot',source_hash:sha,mode:'svg-vector-preserve',geometry_before:'c'.repeat(64),geometry_after:'c'.repeat(64)}],
  layout:{texts:[{id:'x',role:'axis-tick',text:'1'},{id:'legend:series',role:'legend-label',text:'S'},{id:'b1',role:'numeric-value',text:'64'},{id:'s1',role:'label',text:'Section'}],layout_evidence:{source_bar_labels:{count:1,bindings:[{...labels[0],source_text:'64'}],section_bindings:[{...sections[0],source_text:'Section'}]}}}};
 assert.doesNotThrow(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));
 report.layout.texts.find(t=>t.id==='b1').text='65';assert.throws(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));
});
