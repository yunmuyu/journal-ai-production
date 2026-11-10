import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {assertDeliveryChecklist} from './delivery-checklist.mjs';

const engineRoot=fileURLToPath(new URL('../portable-production/direct-pdf/',import.meta.url));
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const bindingKeys=rows=>JSON.stringify(rows?.map(r=>[r.path,r.sha256,r.role??'source']));
const diagramKinds=new Set(['graph','cycle','layered','radial','fanout','tree','network','columns','scene']);
export function processingRequirement(route){
 const requirement=route?.processing;
 if(!requirement||!['preserve','rebuild','vector-reletter','raster-reletter','chart-redraw'].includes(requirement.operation)||typeof requirement.basis!=='string'||!requirement.basis.trim())throw Error('独立质量核验缺少已核对的加工要求：文件格式不能代替重绘或换字');
 if((route.method==='raster-preserve')!==(requirement.operation==='preserve'))throw Error('JPG保留路线只能执行明确的保留要求；换字须走可编辑加工入口');
 return requirement;
}
export function assertRebuildLayout(report){
 const {nodes=[],texts=[],assets=[]}=report.layout??{};
 const inside=(outer,inner)=>Array.isArray(inner)&&inner[0]>=outer[0]&&inner[1]>=outer[1]&&inner[2]<=outer[2]&&inner[3]<=outer[3];
 for(const node of nodes){
  if(!node.container||!texts.some(t=>t.id===node.id+':text'&&t.owner===node.id))continue;
  const hasContent=nodes.some(child=>child.id!==node.id&&inside(node.rect,child.rect))||assets.some(asset=>inside(node.rect,asset.rect));
  if(!hasContent)throw Error('ordinary_box_container: '+node.id+' 普通文字框不得使用容器标记绕过测字留白；请使用公共测量分组重建');
 }
}
export function verifyOperation(requirement,spec,report,selectedHash){
 const texts=report.layout?.texts??[],assets=report.assets??[];
 if(!texts.length)throw Error('加工报告缺少可编辑文字');
 switch(requirement.operation){
  case 'rebuild':
   if(!diagramKinds.has(spec.kind)||!report.layout?.nodes?.length)throw Error('公共工具实际加工方法与重绘要求不符');
   assertRebuildLayout(report);
   break;
  case 'chart-redraw': {
   if(spec.kind==='chart'&&Array.isArray(spec.panels)){
    const panels=spec.panels,proof=report.layout?.layout_evidence?.chart_panels;
    if(panels.length<2||panels.length>12||!Array.isArray(proof)||proof.length!==panels.length||panels.some(p=>p.kind!=='chart'||p.panels))throw Error('组合图表缺少完整逐面板证据');
    const prefixes=panels.map((_,i)=>'panel-'+(i+1)+':');
    if(texts.some(t=>!prefixes.some(p=>t.id.startsWith(p)))||assets.some(a=>!prefixes.some(p=>a.id.startsWith(p))))throw Error('组合图表存在未绑定的文字或图形');
    for(let i=0;i<panels.length;i++){
     const prefix=prefixes[i],panel=panels[i];
     if(proof[i].prefix!==prefix||proof[i].source!==panel.source||proof[i].axes_id!==panel.axes_id)throw Error('组合图表面板来源或顺序不符');
     const panelReport={...report,assets:assets.filter(a=>a.id.startsWith(prefix)).map(a=>({...a,id:a.id.slice(prefix.length)})),
      layout:{texts:texts.filter(t=>t.id.startsWith(prefix)).map(t=>({...t,id:t.id.slice(prefix.length)})),layout_evidence:proof[i].layout}};
     verifyOperation(requirement,panel,panelReport,selectedHash);
    }
    break;
   }
   const review=spec.legend_review;
   const absent=review?.present===false&&review.source_sha256===selectedHash&&typeof review.reason==='string'&&review.reason.trim();
   const legendTexts=texts.filter(t=>t.role==='legend-label'),ticks=texts.filter(t=>t.role==='axis-tick');
   if(!ticks.length)throw Error('统计图缺少刻度文字加工证据');
   if(spec.kind==='scene'){
    const layout=report.layout?.layout_evidence?.chart_vector_layout,actualAudit=report.pdf_audit?.chart_vector_layout;
    if(!layout?.source_geometry_verified||layout.source_sha256!==selectedHash||actualAudit?.passed!==true||actualAudit.source_sha256!==selectedHash||actualAudit.curve_data_reconstructed!==false)throw Error('原矢量图表须经公共图表布局和最终PDF刻度间距检查');
    const ids=requirement.targetTextIds,body=assets.filter(a=>a.source_hash===selectedHash&&a.preparation_mode==='source-vector-reletter'&&a.source_path_multiset_preserved===true&&a.text_replacements?.length);
    if(!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length||!body.length||!texts.some(t=>t.role==='axis-title'))throw Error('矢量图表缺少来源、文字或曲线保留证据');
    if(absent){if(legendTexts.length||layout.legend_bindings?.length)throw Error('无图例声明与实际图例矛盾');}
    else{
     const entries=review?.entries,bindings=layout.legend_bindings;
     const groupedIds=Array.isArray(entries)?entries.flatMap(e=>e.text_ids??[e.text_id]):[];
     if(review?.present!==true||review.source_sha256!==selectedHash||!review.reason?.trim()||!Array.isArray(entries)||!entries.length||new Set(groupedIds).size!==groupedIds.length||JSON.stringify([...groupedIds].sort())!==JSON.stringify(legendTexts.map(t=>t.id).sort())||!Array.isArray(bindings)||bindings.length!==entries.length||actualAudit.legend_bindings_verified!==entries.length)throw Error('矢量图表缺少完整图例绑定及最终检查');
     for(const entry of entries){
      const binding=bindings.find(b=>b.text_id===entry.text_id);
      if(!binding||!legendTexts.some(t=>t.id===entry.text_id)||JSON.stringify(entry.text_ids??[entry.text_id])!==JSON.stringify(binding.text_ids??[binding.text_id])||['series_path_index','series_marker_index','swatch_path_index','swatch_marker_index'].some(k=>!Number.isSafeInteger(entry[k])||entry[k]<0||binding[k]!==entry[k]))throw Error('图例文字、样符与曲线的源绑定不一致');
     }
     if(new Set(entries.map(e=>e.text_id)).size!==entries.length||new Set(entries.map(e=>e.series_path_index)).size!==entries.length||new Set(entries.map(e=>e.swatch_path_index)).size!==entries.length)throw Error('图例绑定重复');
    }
    const replacements=body.flatMap(a=>a.text_replacements),actual=replacements.map(r=>r.target_text_id);
    if(actual.length!==ids.length||new Set(actual).size!==actual.length||ids.some(id=>!actual.includes(id))||replacements.some(r=>!texts.some(t=>t.id===r.target_text_id&&t.text?.replace(/\r?\n/g,'')===(r.target_text??r.source_text))))throw Error('图表换字目标不完整或文字不符');
    break;
   }
   const plot=assets.find(a=>a.id==='plot'&&a.source_hash===selectedHash);
   const preserved=plot&&(plot.mode==='svg-vector-preserve'&&typeof plot.geometry_before==='string'&&/^[a-f0-9]{64}$/.test(plot.geometry_before)&&JSON.stringify(plot.geometry_before)===JSON.stringify(plot.geometry_after)||plot.mode==='raster-protected-viewport'&&plot.protected_pixels_unchanged_before_color_conversion===true);
   if(spec.kind!=='chart'||!preserved)throw Error('统计图缺少原数据图形保留证据');
   if(absent){if(legendTexts.length||spec.series?.length||spec.masks?.length)throw Error('无图例声明与实际图例或遮盖矛盾');}
   else if(!Array.isArray(spec.series)||!spec.series.length||legendTexts.length!==spec.series.length||spec.series.some(e=>!legendTexts.some(t=>t.id==='legend:'+e.id&&t.text===e.label)))throw Error('统计图加工缺少完整图例换字证据');
   if(spec.bar_labels?.length){
    const proof=report.layout?.layout_evidence?.source_bar_labels,sections=spec.section_labels??[];
    if(!Array.isArray(spec.bar_labels)||!proof||proof.count!==spec.bar_labels.length||!Array.isArray(proof.bindings)||proof.bindings.length!==spec.bar_labels.length||report.pdf_audit?.numeric_grouping_in_actual_pdf!==true||!Array.isArray(proof.section_bindings)||proof.section_bindings.length!==sections.length)throw Error('柱图缺少逐柱数值和区段标题证据');
    for(const item of spec.bar_labels){
     const binding=proof.bindings.find(x=>x.id===item.id),text=texts.find(x=>x.id===item.id&&x.role==='numeric-value');
     if(!binding||binding.text_group!==item.text_group||binding.bar_group!==item.bar_group||typeof binding.source_text!=='string'||!text||text.text.replace(/\s/g,'')!==binding.source_text.replace(/\s/g,''))throw Error('柱顶数值未与源柱和原字一一对应');
    }
    for(const item of sections){const binding=proof.section_bindings.find(x=>x.id===item.id),text=texts.find(x=>x.id===item.id);if(!binding||binding.text_group!==item.text_group||!text||text.text!==binding.source_text)throw Error('柱图区段标题未绑定原文');}
    if(new Set(spec.bar_labels.map(x=>x.id)).size!==spec.bar_labels.length||new Set(spec.bar_labels.map(x=>x.bar_group)).size!==spec.bar_labels.length)throw Error('柱顶数值绑定重复');
   }else if(spec.section_labels?.length)throw Error('柱图区段标题缺少柱形绑定');
   break;
  }
  case 'vector-reletter':
  case 'raster-reletter': {
   if(texts.some(t=>t.role==='axis-tick')&&texts.some(t=>t.role==='axis-title'))throw Error('含坐标轴图表须使用公共图表加工路线，不得仅按通用换字回传');
   const raster=requirement.operation==='raster-reletter',ids=requirement.targetTextIds;
   if(spec.kind!=='scene'||!Array.isArray(ids)||!ids.length||ids.some(id=>typeof id!=='string'||!id.trim())||new Set(ids).size!==ids.length)throw Error('换字要求须明确唯一的目标文字ID集合');
   const bodies=assets.filter(a=>a.source_hash===selectedHash&&a.text_replacements?.length);
   const mixedVerified=a=>{
    const paths=report.pdf_audit?.source_path_ownership,images=report.pdf_audit?.source_image_ownership;
    return a.mode==='source-mixed-body'&&a.noncolor_geometry_and_style_exact===true&&a.original_image_placements_preserved===true&&
     a.original_smask_preserved===true&&a.font_count===0&&a.source_text_character_count===0&&a.image_instance_count>0&&
     paths?.source_geometry_and_style_exact===true&&paths.bindings?.some(b=>b.id===a.id&&b.source_sha256===selectedHash&&b.mode==='source-mixed-body')&&
     images?.bidirectional_instance_multiset_exact===true&&images.original_smask_exact===true&&images.derived_grayscale_pixels_exact===true&&
     images.matched_instance_count===a.image_instance_count&&images.expected_instance_count===a.image_instance_count&&
     report.pdf_audit?.neutral_rgb_300dpi===true&&report.pdf_audit?.text_multiset_exact===true;
   };
   if(!bodies.length||bodies.some(a=>raster?a.mode!=='raster-protected-viewport'||a.protected_pixels_unchanged_before_color_conversion!==true||a.grayscale!==true:!(a.preparation_mode==='source-vector-reletter'&&a.source_path_multiset_preserved===true)&&!mixedVerified(a)))throw Error('换字报告未证明已清除原字并保留源图形/像素');
   const replacements=bodies.flatMap(a=>a.text_replacements),actual=replacements.map(r=>r.target_text_id);
   if(actual.length!==ids.length||new Set(actual).size!==actual.length||ids.some(id=>!actual.includes(id))||replacements.some(r=>!texts.some(t=>t.id===r.target_text_id&&t.text?.replace(/\r?\n/g,'')===(r.target_text??r.source_text))))throw Error('换字目标不完整、重复或实际文字不符');
   break;
  }
  default:throw Error('此入口要求PDF加工证据');
 }
}
function readEvidence(ref,attempt){
 if(!ref?.path||! /^[a-f0-9]{64}$/.test(ref.sha256||''))throw Error('加工证据缺少路径或SHA256');
 const actual=fs.realpathSync(ref.path),relative=path.relative(fs.realpathSync(attempt),actual);
 if(!relative||relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative)||hash(actual)!==ref.sha256)throw Error('加工证据必须位于本次尝试且哈希匹配');
 return JSON.parse(fs.readFileSync(actual,'utf8').replace(/^\uFEFF/,''));
}
// New publication only. Historical display/restoration and user acceptance are not rewritten.
export function verifyProcessingEvidence(task,outputs,evidence,{python}={}){
 processingRequirement(task.productionRoute);
 if(!Array.isArray(evidence)||evidence.length!==task.outputNumbers.length)throw Error('缺少逐图公共工具加工证据；未终检旧候选须回到对应工具加工');
 if(!python)throw Error('未配置加工证据核验Python');
 const seen=new Set(),receipts=[];
 for(const entry of evidence){
  if(!task.outputNumbers.includes(entry.number)||seen.has(entry.number))throw Error('加工证据图号重复或不属于当前任务');seen.add(entry.number);
  const output=outputs.find(o=>o.number===entry.number);
  const route=task.outputRoutes?.find(r=>r.number===entry.number)?.productionRoute??task.productionRoute,requirement=processingRequirement(route);
  if(!output||hash(output.path)!==output.sha256)throw Error('加工证据对应的候选缺失或变化');
  const report=readEvidence(entry.report,task.attemptDir),spec=readEvidence(entry.spec,task.attemptDir);
  if(report.backend!=='direct-pdf'||report.status!=='candidate-rendered'||report.mechanical_checks_passed!==true||report.pdf_sha256!==output.sha256||report.id!==spec.id||report.kind!==spec.kind||report.font?.purpose!=='production')throw Error('候选未绑定公共工具的正式字体加工报告');
  const bindings=report.source_bindings;
  if(!Array.isArray(bindings)||bindingKeys(bindings)!==bindingKeys(spec.sources)||hash(route.sourceReview.selected.path)!==route.sourceReview.selected.sha256||!bindings.some(b=>b.sha256===route.sourceReview.selected.sha256)||bindings.some(b=>hash(path.resolve(entry.sourceRoot??path.dirname(entry.spec.path),b.path))!==b.sha256))throw Error('加工报告没有绑定本图已核对的原始来源');
  if(!report.pdf_audit?.text_multiset_exact||!report.pdf_audit?.neutral_rgb_300dpi||!report.pdf_audit?.all_fonts_embedded||!report.pdf_audit?.editable_text_pure_black||report.pdf_audit?.editable_text_margin_passed!==true||!(report.pdf_audit.minimum_text_margin_pt>=1.99))throw Error('加工报告缺少实际PDF文字、字体、灰度及页边检查');
  const checklist=assertDeliveryChecklist(report,{outputSha256:output.sha256,widthMm:route.requirements.widthMm});
  verifyOperation(requirement,spec,report,route.sourceReview.selected.sha256);
  const proof=JSON.parse(execFileSync(python,['-c','import json,sys; from journal_pdf.common import read_json,digest_json; from journal_pdf.editorial import engine_signature; print(json.dumps({"engine":engine_signature(),"spec":digest_json(read_json(sys.argv[1]))}))',entry.spec.path],{cwd:engineRoot,env:{...process.env,PYTHONPATH:engineRoot,PYTHONUTF8:'1'},encoding:'utf8',windowsHide:true,timeout:30000}));
  if(report.engine_signature!==proof.engine||report.spec_hash!==proof.spec)throw Error('加工报告的公共工具版本或制作说明已变化');
  if(hash(entry.report.path)!==entry.report.sha256||hash(entry.spec.path)!==entry.spec.sha256||hash(output.path)!==output.sha256)throw Error('加工证据在核验期间变化');
  receipts.push({number:entry.number,operation:requirement.operation,report:entry.report,spec:entry.spec,...(entry.sourceRoot?{sourceRoot:entry.sourceRoot}:{}),outputSha256:output.sha256,checklist});
 }
 return receipts;
}
