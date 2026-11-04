// Resolve confirmed series candidates into the existing chart spec, without copying curve data.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const checked=ref=>{if(!ref?.path||!/^[a-f0-9]{64}$/.test(ref.sha256??'')||hash(ref.path)!==ref.sha256)throw Error('binding_evidence_changed');};

export function materializeConfirmedSeries(input,write){
 const plan=structuredClone(input);
 if(!Array.isArray(plan.render))return plan;
 if(plan.rendered&&plan.render.some(item=>item.seriesBinding))throw Error('series_binding_pre_rendered_conflict');
 for(const item of plan.render){
  const binding=item.seriesBinding;if(!binding)continue;
  if(binding.confirmed!==true||typeof binding.reason!=='string'||!binding.reason.trim())throw Error('series_binding_confirmation_required');
  checked(item.spec);checked(binding.candidate);
  const spec=read(item.spec.path),report=read(binding.candidate.path),sourceSha=spec.chart_vector_layout?.source_sha256;
  const selected=plan.outputRoutes?.find(r=>r.number===item.number)?.productionRoute?.sourceReview?.selected;
  if(!sourceSha||spec.legend_review?.present!==true||spec.legend_review.source_sha256!==sourceSha||selected?.sha256!==sourceSha||report.status!=='needs_review'||report.sourceSha256!==sourceSha||!report.source||hash(report.source)!==sourceSha)throw Error('series_binding_source_changed');
  const body=spec.assets?.find(a=>a.id===spec.chart_vector_layout.body_id);
  const root=fs.realpathSync(item.sourceRoot),source=fs.realpathSync(path.resolve(root,body?.path??'')),relative=path.relative(root,source);
  if(!body?.path||relative===''||relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative)||hash(source)!==sourceSha)throw Error('series_binding_source_changed');
  const entries=spec.legend_review.entries,choices=binding.choices;
  if(!Array.isArray(entries)||!entries.length||!Array.isArray(choices)||choices.length!==entries.length||!Array.isArray(report.candidates)||new Set(choices.map(c=>c.textId)).size!==choices.length||new Set(choices.map(c=>c.candidateIndex)).size!==choices.length)throw Error('series_binding_incomplete');
  for(const entry of entries){
   const choice=choices.find(c=>c.textId===entry.text_id),index=choice?.candidateIndex,c=report.candidates[index];
   if(!Number.isSafeInteger(index)||index<0||!c||['series_path_index','series_marker_index','swatch_path_index','swatch_marker_index'].some(k=>!Number.isSafeInteger(c[k])||c[k]<0)||c.swatch_path_index!==entry.swatch_path_index||c.swatch_marker_index!==entry.swatch_marker_index)throw Error('series_binding_conflict');
   for(const key of ['series_path_index','series_marker_index']){
    if(entry[key]!==undefined&&entry[key]!==c[key])throw Error('series_binding_conflict');
    entry[key]=c[key];
   }
  }
  if(new Set(entries.map(e=>e.series_path_index)).size!==entries.length)throw Error('series_binding_duplicate');
  spec.legend_review.semantic_confirmation={candidateSha256:binding.candidate.sha256,sourceSha256:sourceSha,reason:binding.reason,choices};
  item.spec=write('confirmed-series-'+String(item.number).replace(/[^\w.-]/g,'_')+'.json',spec);
  delete item.seriesBinding;
 }
 return plan;
}
