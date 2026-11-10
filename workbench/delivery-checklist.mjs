// Summarize the existing public renderer evidence; never create user acceptance.
const sha=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const check=(passed,measurement,scope)=>({status:passed===true?'checked':passed===false?'failed':'pending',measurement,scope});

export function deliveryChecklist(report,{outputSha256,widthMm}={}){
 if(!sha(outputSha256)||report?.pdf_sha256!==outputSha256)throw Error('delivery_checklist_output_mismatch');
 const audit=report.pdf_audit??{},layout=report.layout?.layout_evidence??{},font=report.font??{};
 const production=report.status==='candidate-rendered'&&report.mechanical_checks_passed===true&&report.backend==='direct-pdf';
 const sizes=(report.layout?.texts??[]).map(t=>t.font_size_pt).filter(finite);
 const checks={
  publicRenderer:check(production,{status:report.status,engineSignature:report.engine_signature},'当前产物哈希绑定的公共制作报告；不表示正式发布'),
  fonts:check(font.purpose==='production'&&sha(font.fingerprint)&&audit.all_fonts_embedded===true&&audit.editable_text_font_styles_exact===true,
   {profileId:font.profile_id,fingerprint:font.fingerprint,faces:Object.fromEntries(Object.entries(font.faces??{}).map(([name,face])=>[name,{sha256:face.sha256,faceSha256:face.face_sha256}]))},'实际可编辑文字字体、字号及嵌入检查；字体等效与InDesign置入仍待终检'),
  grayscale:check(audit.neutral_rgb_300dpi,{nonneutralPixels:audit.nonneutral_pixels},'实际PDF 300dpi灰度检查；灰度语义仍须人工核对'),
  dimensions:check(finite(audit.width_mm)&&finite(audit.height_mm)&&audit.width_mm>0&&audit.height_mm>0&&finite(widthMm)&&widthMm>0&&widthMm<=160&&audit.width_mm<=widthMm+.01,
   {widthMm:audit.width_mm,heightMm:audit.height_mm,requestedWidthMm:widthMm},'绑定本图计划的实际PDF尺寸，不按文件名推断栏宽'),
  fontSize:check(finite(layout.final_font_size_pt)&&layout.final_font_size_pt>=6-1e-6&&layout.final_font_size_pt<=8+1e-6&&audit.editable_text_font_styles_exact===true,
   {basePt:layout.final_font_size_pt,designPt:layout.initial_design_font_size_pt,sceneSizesPt:[...new Set(sizes)]},'可编辑正文基准6–8pt；角标按语义检查，位图内部不按像素估算字号'),
  strokes:check(audit.effective_path_strokes_05pt,{targetPt:.5,auditedCount:audit.audited_stroke_count,violations:audit.stroke_violations??[]},audit.stroke_scope??'可见PDF描边；位图、填充轮廓不在0.5pt检查范围'),
  editableText:check(audit.text_multiset_exact===true&&audit.editable_text_pure_black===true,
   {expectedCharacters:audit.expected_text_characters,actualCharacters:audit.actual_text_characters},'已登记可编辑文字，不等于证明所有位图或轮廓中没有遗漏文字'),
  margins:check(audit.editable_text_margin_passed===true&&finite(audit.minimum_text_margin_pt)&&audit.minimum_text_margin_pt>=1.99,
   {minimumPt:audit.minimum_text_margin_pt},'保存后实际PDF至少2pt留白')
 };
 return {version:1,type:'production-checklist',outputSha256,engineSignature:report.engine_signature,ruleset:report.editorial_ruleset,
  sourceBindings:(report.source_bindings??[]).map(({path,sha256,role})=>({path,sha256,role:role??'source'})),checks,
  mechanicalStatus:Object.values(checks).every(c=>c.status==='checked')?'checked':'blocked',
  reviewPending:[...new Set([...(report.needs_review??[]),'actual-size-visual-review','source-content-and-topology','InDesign-placement','user-acceptance'])],
  userAccepted:false,workbenchReturned:false,stage:'offline-candidate'};
}

export function assertDeliveryChecklist(report,options){
 const result=deliveryChecklist(report,options),missing=Object.entries(result.checks).filter(([,c])=>c.status!=='checked').map(([name])=>name);
 if(missing.length)throw Error('delivery_checklist_failed: '+missing.join(', '));
 return result;
}

// A return receipt and acceptance are different observations. Call only after
// verifyProductionDelivery has independently verified the current workbench.
export function verifiedDeliveryState(figure,receipt){
 if(!figure?.id||receipt?.type!=='production-delivery'||figure.id!==receipt.figureId||figure.articleId!==receipt.articleId||
  !Array.isArray(receipt.outputs)||!receipt.outputs.length||figure.outputs?.length!==receipt.outputs.length||
  !receipt.outputs.every(o=>figure.outputs.some(x=>x.number===o.number&&x.file?.meta?.sha256===o.sha256)))throw Error('delivery_state_binding_mismatch');
 const accepted=figure.status==='终检通过';
 return {stage:accepted?'user-accepted':'workbench-candidate',workbenchReturned:true,userAccepted:accepted,
  workbenchReviewVersion:figure.reviewVersion??null,receiptId:receipt.id,
  note:accepted?'工作台当前版本已终检通过；回传收据本身不授予验收。':'已回工作台待终检；制作检查不等于用户验收。'};
}
