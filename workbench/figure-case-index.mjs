// Evidence-bound method retrieval; never copies another figure's data or bindings.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');

export function projectCaseOutcome(item,row){
 if(!['candidate','approved','rejected'].includes(item.outcome))return item.outcome;
 if(!row||!item.outputSha256)return 'historical_unverified';
 const output=row.outputs?.find(o=>o.file?.meta?.sha256===item.outputSha256);
 if(!output)return 'superseded';
 try{if(!output.file.path||hash(output.file.path)!==item.outputSha256)return 'historical_unverified';}catch{return 'historical_unverified';}
 if(row.status==='终检通过')return 'approved';
 if(row.status==='异常'&&row.feedback?.needsRevision)return 'rejected';
 return 'candidate';
}

export function sourceBindingFingerprint(asset){
 const keys=['source_text','source_bbox','source_instances','source_occurrences'];
 const replacements=asset.text_replacements.map(row=>Object.fromEntries(keys.filter(k=>Object.hasOwn(row,k)).map(k=>[k,row[k]])));
 replacements.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
 return createHash('sha256').update(JSON.stringify({page:asset.page??0,clip:asset.clip,replacements})).digest('hex');
}

export function matchesSourceVectorAsset(asset,sourceRoot,sourceSha256){
 if(asset?.source_vector_body!==true||!asset.path||!sourceRoot||!Array.isArray(asset.clip)||asset.clip.length!==4||!Array.isArray(asset.text_replacements))return false;
 try{
  const root=fs.realpathSync(sourceRoot),file=fs.realpathSync(path.resolve(root,asset.path)),rel=path.relative(root,file);
  return rel!==''&&!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel)&&hash(file)===sourceSha256;
 }catch{return false;}
}

export function shouldBlockIdenticalAttempt(item,attempt){
 const keys=['sourceSha256','engineSignature','operation','bindingSha256'];
 return item.outcome==='failure'&&!item.resolved&&keys.every(k=>typeof item.guard?.[k]==='string'&&item.guard[k]&&item.guard[k]===attempt?.[k]);
}

export function loadCaseIndex(file,rows=[]){
 if(!file||!fs.existsSync(file))return {cases:[],invalid:[]};
 const data=JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
 if(data.version!==1||!Array.isArray(data.cases))throw Error('invalid_case_index');
 const cases=[],invalid=[];
 for(const item of data.cases){
  if(!item.id||!item.evidence?.path||!item.evidence.sha256||!item.features||!item.entry||!['candidate','approved','rejected','intermediate','failure'].includes(item.outcome))throw Error('invalid_case_record: '+item.id);
  let verified=false;try{verified=hash(item.evidence.path)===item.evidence.sha256;}catch{}
  if(!verified){invalid.push({id:item.id,reason:'case_evidence_changed_or_missing'});continue;}
  const row=rows.find(r=>r.id===item.figureId);
  let resolved=false;
  if(item.resolved&&item.resolutionEvidence?.path&&item.resolutionEvidence?.sha256){try{resolved=hash(item.resolutionEvidence.path)===item.resolutionEvidence.sha256;}catch{}}
  cases.push({...item,resolved,author:item.author??row?.author,editor:item.editor??row?.editor,articleId:item.articleId??row?.articleId,number:item.number??row?.number,outcome:projectCaseOutcome(item,row)});
 }
 return {cases,invalid};
}

export function rankCases(cases,features,{limit=8}={}){
 return cases.map(item=>{
  const reasons=[];let score=0;
  for(const [key,weight] of [['kind',8],['format',8],['nativeText',4],['vector',4],['color',2],['legend',3],['panels',6],['layout',3]]){
   if(features[key]===undefined||item.features?.[key]===undefined)continue;
   if(features[key]===item.features[key]){score+=weight;reasons.push(key+'相同');}
   else if(key==='kind'||key==='format')score-=weight;
  }
  const exactError=Boolean(features.errorCode&&item.errorCode===features.errorCode);
  if(exactError){score+=100;reasons.push('错误码相同');}
  return {id:item.id,figureId:item.figureId,author:item.author,editor:item.editor,articleId:item.articleId,number:item.number,outcome:item.outcome,resolved:!!item.resolved,recordType:item.recordType??'case',entry:item.entry,features:item.features,errorCode:item.errorCode??null,
          result:item.result,conditions:item.conditions,evidence:item.evidence,match:{score,reasons,exactError},
          usage:'仅参考工具和方法；当前图的对象、数据、图例及来源必须重新绑定'};
 }).filter(item=>item.match.score>0).sort((a,b)=>b.match.score-a.match.score||a.id.localeCompare(b.id)).slice(0,limit);
}

export function casesFromWorkbench(rows,features={}){
 const results=[];
 for(const row of rows){
  const route=row.productionRoute,selected=route?.sourceReview?.selected;
  const kind=/图表|曲线|柱状/.test(row.type??'')?'chart':/流程|结构/.test(row.type??'')?'diagram':'other';
  if(features.kind&&kind!==features.kind)continue;
  if(!selected?.path||!route.processing?.operation)continue;
  for(const output of row.outputs??[]){
   if(!output.file?.path||!/^[a-f0-9]{64}$/.test(output.file?.meta?.sha256??''))continue;
   const format=output.file.path.toLowerCase().endsWith('.pdf')?'pdf':null;
   const sourceFormat=selected.path.toLowerCase().split('.').pop();
   const item={id:'workbench:'+row.id+':'+output.number+':'+output.file.meta.sha256,figureId:row.id,author:row.author,editor:row.editor,articleId:row.articleId,number:output.number,outputSha256:output.file.meta.sha256,outcome:'candidate',
    features:{kind,format:sourceFormat},
    entry:route.processing.operation,result:'工作台当前候选；质量状态随终审变化',conditions:route.processing.basis??'需核对当前来源与图件要求',
    evidence:{path:output.file.path,sha256:output.file.meta.sha256},outputFormat:format};
   try{if(hash(item.evidence.path)!==item.outputSha256)continue;}catch{continue;}
   item.outcome=projectCaseOutcome(item,row);results.push(item);
  }
 }
 return results;
}

export function recommendCases({registryPath,eventDirectory,rows=[],features}){
 const curated=loadCaseIndex(registryPath,rows),events=loadCaseEvents(eventDirectory,rows),live=casesFromWorkbench(rows,features);
 const known=new Set([...curated.cases,...events.cases].filter(c=>c.outputSha256).map(c=>c.figureId+':'+c.outputSha256));
 const current=live.filter(c=>!known.has(c.figureId+':'+c.outputSha256));
 const matches=rankCases([...curated.cases,...events.cases,...current],features);
 return {cases:matches,byOutcome:{approved:matches.filter(c=>c.outcome==='approved'),candidate:matches.filter(c=>c.outcome==='candidate'),rejected:matches.filter(c=>c.outcome==='rejected'),failure:matches.filter(c=>c.outcome==='failure'&&!c.resolved),resolvedFailure:matches.filter(c=>c.outcome==='failure'&&c.resolved),intermediate:matches.filter(c=>c.outcome==='intermediate'),unverified:matches.filter(c=>['superseded','historical_unverified'].includes(c.outcome))},invalidEvidence:[...curated.invalid,...events.invalid],curatedCount:curated.cases.length,eventCount:events.cases.length,currentWorkbenchCount:current.length};
}

export function loadCaseEvents(directory,rows=[]){
 if(!directory||!fs.existsSync(directory))return {cases:[],invalid:[]};
 const cases=[],invalid=[];
 for(const name of fs.readdirSync(directory).filter(n=>n.endsWith('.json'))){
  const loaded=loadCaseIndex(path.join(directory,name),rows);
  cases.push(...loaded.cases);invalid.push(...loaded.invalid);
 }
 return {cases,invalid};
}

function writeEvent(directory,item){
 fs.mkdirSync(directory,{recursive:true});
 const key=createHash('sha256').update(JSON.stringify(item)).digest('hex'),file=path.join(directory,key+'.json');
 const bytes=JSON.stringify({version:1,cases:[item]},null,2)+'\n';
 try{fs.writeFileSync(file,bytes,{flag:'wx'});}catch(error){if(error.code!=='EEXIST'||fs.readFileSync(file,'utf8')!==bytes)throw error;}
 return file;
}

function diagnostic(error){
 const raw=String(error.stdout??'')+'\n'+String(error.stderr??'');
 for(const line of raw.split(/\r?\n/).reverse()){
  try{const value=JSON.parse(line);if(value.error?.code)return {code:value.error.code,message:value.error.message??'',raw,fromTool:true};}catch{}
 }
 return {code:typeof error.code==='string'?error.code:'unknown',message:error.message??String(error),raw:raw||String(error.message??error)};
}

export function searchFailureAlternatives({registryPath,eventDirectory,error,plan,features={}}){
 const found=diagnostic(error),selected=plan.outputRoutes?.[0]?.productionRoute?.sourceReview?.selected;
 const query={...features,...(!features.format&&selected?.path?{format:path.extname(selected.path).slice(1).toLowerCase()}:{}),errorCode:found.code};
 const recommendations=recommendCases({registryPath,eventDirectory,features:query});
 return {status:'searched',errorCode:found.code,query,recommendations,usage:'候选方法须按当前图源和加工要求验证，不能直接复用其他图的数据或降低检查标准'};
}

export function recordFailureCase(directory,{figureId,plan,error,stage,engineSignature}){
 if(!['render','check'].includes(stage)||plan.outputRoutes?.length!==1)return null;
 const found=diagnostic(error),route=plan.outputRoutes?.[0]?.productionRoute,selected=route?.sourceReview?.selected;
 if(!found.fromTool)return null;
 if(!selected?.path||!selected.sha256)return null;
 try{if(hash(selected.path)!==selected.sha256)return null;}catch{return null;}
 const evidenceRoot=path.join(directory,'evidence');fs.mkdirSync(evidenceRoot,{recursive:true});
 const bytes=Buffer.from(found.raw,'utf8'),sha=createHash('sha256').update(bytes).digest('hex'),evidencePath=path.join(evidenceRoot,sha+'.log');
 try{fs.writeFileSync(evidencePath,bytes,{flag:'wx'});}catch(e){if(e.code!=='EEXIST'||hash(evidencePath)!==sha)throw e;}
 const features={kind:plan.qualityRoute==='source-preserving-chart'?'chart':'other',format:path.extname(selected.path).slice(1).toLowerCase()};
 const item={id:'failure:'+figureId+':'+sha,figureId,outcome:'failure',errorCode:found.code,features,
  entry:plan.qualityRoute??stage,result:found.message,conditions:'仅复用失败原因；新图的来源和绑定须重新核对',evidence:{path:evidencePath,sha256:sha}};
 if(found.code==='source_icon_pixels_changed'){
  const specItem=(plan.render??plan.rendered?.processingEvidence??[])[0],ref=specItem?.spec;
  try{
   if(ref?.path&&hash(ref.path)===ref.sha256){const spec=JSON.parse(fs.readFileSync(ref.path,'utf8'));const assets=(spec.assets??[]).filter(a=>matchesSourceVectorAsset(a,specItem.sourceRoot,selected.sha256));
    if(assets.length===1)item.guard={sourceSha256:selected.sha256,engineSignature,operation:'source-vector-reletter',bindingSha256:sourceBindingFingerprint(assets[0])};}
  }catch{}
 }
 return writeEvent(directory,item);
}

export function recordDeliveryCases(directory,{figure,plan,outputs,discovery,engineSignature}){
 const result=[];
 for(const output of outputs??[]){
  const entry=plan.outputRoutes?.find(r=>String(r.number)===String(output.number));
  const route=entry?.productionRoute,selected=route?.sourceReview?.selected;
  if(!selected?.path||!selected.sha256)throw Error('case_delivery_route_missing');
  const format=path.extname(selected.path).slice(1).toLowerCase();
  if(!output.path||!output.sha256||hash(output.path)!==output.sha256)throw Error('case_delivery_output_changed');
  const features={kind:plan.qualityRoute==='source-preserving-chart'?'chart':plan.qualityRoute==='diagram'?'diagram':'other',format};
  const sameSource=discovery?.sourceSha256===selected.sha256;
  const facts=sameSource?discovery?.facts:undefined,featureCandidates=sameSource?discovery?.featureCandidates:undefined;
  if(facts){features.nativeText=facts.textSpans>0;features.vector=facts.vectorPaths>0;features.color=Boolean(facts.pages?.some(p=>p.coloredPaths?.length));}
  for(const key of ['panels','legend','layout'])if(featureCandidates?.[key]!==undefined)features[key]=featureCandidates[key];
  const item={id:'delivery:'+figure.id+':'+output.number+':'+output.sha256,figureId:figure.id,articleId:figure.articleId,number:output.number,outputSha256:output.sha256,outcome:'candidate',
   features,featureEvidence:featureCandidates?'panel/legend are unconfirmed discovery candidates':'not supplied',engineSignature:engineSignature??null,entry:route.processing.operation,
   result:'候选已回传，质量状态以当前工作台终审为准',conditions:route.processing.basis,evidence:{path:output.path,sha256:output.sha256},
   sourceBinding:{archiveSha256:route.sourceReview.archive.sha256,wordSha256:route.sourceReview.word.sha256,sourceSha256:selected.sha256},requirements:route.requirements,specSha256:(plan.render??plan.rendered?.processingEvidence??[]).find(x=>x.number===output.number)?.spec?.sha256??null};
  result.push(writeEvent(directory,item));
 }
 return result;
}
