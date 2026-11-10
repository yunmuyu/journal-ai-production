import test from 'node:test';
import assert from 'node:assert/strict';
import {deliveryChecklist,assertDeliveryChecklist,verifiedDeliveryState} from './delivery-checklist.mjs';
const hash='a'.repeat(64);
function fixture(){return {pdf_sha256:hash,backend:'direct-pdf',status:'candidate-rendered',mechanical_checks_passed:true,engine_signature:'engine',
 font:{purpose:'production',fingerprint:hash,faces:{}},layout:{layout_evidence:{final_font_size_pt:8,initial_design_font_size_pt:8},texts:[]},source_bindings:[{path:'source.pdf',sha256:hash}],
 pdf_audit:{all_fonts_embedded:true,editable_text_font_styles_exact:true,neutral_rgb_300dpi:true,nonneutral_pixels:0,width_mm:79,height_mm:40,
 effective_path_strokes_05pt:true,audited_stroke_count:3,stroke_violations:[],text_multiset_exact:true,editable_text_pure_black:true,
 expected_text_characters:5,actual_text_characters:5,editable_text_margin_passed:true,minimum_text_margin_pt:2}};}
const options={outputSha256:hash,widthMm:80};
test('public check receipt has scoped measurements and never claims delivery or acceptance',()=>{
 const report=fixture(),before=JSON.stringify(report),r=assertDeliveryChecklist(report,options);
 assert.equal(r.mechanicalStatus,'checked');assert.equal(r.stage,'offline-candidate');assert.equal(r.workbenchReturned,false);assert.equal(r.userAccepted,false);
 assert.match(r.checks.strokes.scope,/位图/);assert.ok(r.reviewPending.includes('InDesign-placement'));assert.equal(JSON.stringify(report),before);
});
test('missing, false, nonfinite and out of range evidence fails closed',()=>{
 for(const change of [r=>delete r.pdf_audit.effective_path_strokes_05pt,r=>r.pdf_audit.editable_text_font_styles_exact=false,r=>r.font.fingerprint='missing',r=>r.layout.layout_evidence.final_font_size_pt=5.9,r=>r.pdf_audit.width_mm=80.1,r=>r.pdf_audit.width_mm=NaN,r=>r.pdf_audit.minimum_text_margin_pt=1,r=>r.status='diagnostic-rendered']){
  const r=fixture();change(r);assert.throws(()=>assertDeliveryChecklist(r,options),/delivery_checklist_failed/);
 }
 assert.throws(()=>assertDeliveryChecklist(fixture(),{...options,widthMm:180}),/delivery_checklist_failed/);
 assert.throws(()=>deliveryChecklist(fixture(),{...options,outputSha256:'b'.repeat(64)}),/output_mismatch/);
});
test('pending stroke coverage is reported, not upgraded by overall checks flag',()=>{
 const r=fixture();r.overall_checks_passed=true;delete r.pdf_audit.effective_path_strokes_05pt;
 assert.equal(deliveryChecklist(r,options).checks.strokes.status,'pending');
});
test('workbench candidate and user acceptance are separate, hash-bound observations',()=>{
 const figure={id:'f',articleId:'a',reviewVersion:'v',status:'待终检',outputs:[{number:'1',file:{meta:{sha256:hash}}}]};
 const receipt={type:'production-delivery',id:'r',figureId:'f',articleId:'a',outputs:[{number:'1',sha256:hash}]};
 assert.equal(verifiedDeliveryState(figure,receipt).stage,'workbench-candidate');
 figure.status='终检通过';assert.equal(verifiedDeliveryState(figure,receipt).stage,'user-accepted');
 figure.outputs[0].file.meta.sha256='changed';assert.throws(()=>verifiedDeliveryState(figure,receipt),/binding/);
});
