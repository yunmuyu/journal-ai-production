import {execFileSync} from 'node:child_process';
import {pythonRuntime} from './ingest.mjs';
import {mkdirSync,copyFileSync,existsSync,writeFileSync} from 'node:fs';
import path from 'node:path';
import {readJson,writeJson,fileHash,sha256,resolveInside,logEvent} from './core.mjs';
import {updateFigure} from './jobs.mjs';
import {adobe,packageRoot} from './adobe.mjs';
import {COLOR_RULE_VERSION,assertColorAudit} from './color-policy.mjs';
import {DATA_RULE_VERSION,assertDataAudit} from './data-audit.mjs';
import {DELIVERY_RULE_VERSION,cachedAggregate} from './aggregate-cache.mjs';
function confirmedColumn(root,figure,record){
 const plan=readJson(record.planFile),fitFile=path.join(root,'fit',figure.id,'decision.json'),fit=existsSync(fitFile)?readJson(fitFile):null;
 const declared=plan.column==='single'?'单栏':plan.column==='double'?'双栏':figure.columnLabel;
 const column=declared||((fit?.widthMm===plan.widthMm)?(fit.widthMm<=80?'单栏':fit.widthMm<=160?'双栏':null):null);
 if(column!=='小单栏'&&column!=='单栏'&&column!=='双栏')throw Error('Confirmed column required: plan.column or current fit decision');
 const board=record.adobe.snapshot.artboard,widthPt=board[2]-board[0],limitPt=(column==='双栏'?160:80)*72/25.4;
 if(widthPt<=0||widthPt>limitPt+0.1)throw Error('Actual single PDF width exceeds confirmed column');
 return column;
}
function assertSingleRecord(root,figure,record){
 if(record.ok!==true||record.pdfAudit?.ok!==true||!record.adobe?.snapshot||!Array.isArray(record.adobe.mechanicalIssues)||record.adobe.mechanicalIssues.length)throw Error('Current PDF and resolved mechanical audit required');
 if(record.sourceHash!==figure.sourceHash)throw Error('Job source and current render differ');
 if(!Array.isArray(record.adobe.snapshot.texts)||record.adobe.snapshot.texts.some(text=>!Number.isFinite(text.size)||text.size<6-0.001))throw Error('Actual native text below 6 pt or unmeasured');
 assertColorAudit(record);assertDataAudit(record);return confirmedColumn(root,figure,record);
}
function reviewBindings(record,columnLabel){
 return {deliveryRuleVersion:DELIVERY_RULE_VERSION,colorRuleVersion:COLOR_RULE_VERSION,dataRuleVersion:DATA_RULE_VERSION,sourceHash:record.sourceHash,planHash:record.planHash,planFileHash:record.planFileHash,pdfHash:record.pdfHash,outputHash:record.outputHash,aiHash:record.aiHash,previewHash:record.previewHash,colorAuditHash:sha256(JSON.stringify(record.colorAudit)),dataAuditHash:sha256(JSON.stringify(record.dataAudit)),columnLabel};
}
export function recordReview(root,id,decision,evidence){
 if(!['pass','review','fail'].includes(decision)||!evidence?.trim())throw Error('Explicit review decision and evidence required');
 const figure=readJson(path.join(root,'job.json')).figures.find(x=>x.id===id);if(!figure?.render)throw Error('No current render');const record=readJson(resolveInside(root,figure.render));
 for(const key of ['output','ai','preview'])if(fileHash(record[key])!==record[key+'Hash'])throw Error('Rendered artifacts changed since audit');
 const columnLabel=decision==='pass'?assertSingleRecord(root,figure,record):null;
 const review={decision,evidence,...(decision==='pass'?reviewBindings(record,columnLabel):{planHash:record.planHash,outputHash:record.outputHash,aiHash:record.aiHash,previewHash:record.previewHash}),reviewedAt:new Date().toISOString()};
 writeJson(path.join(path.dirname(record.output),'review.json'),review);updateFigure(root,id,{status:decision==='pass'?'accepted':'needs_revision',review});logEvent(root,{event:'review',id,decision,evidence});return review;
}
export function assertSummaryAudit(report){
 const a=report.summaryAudit;if(!a?.auditFile||fileHash(a.auditFile)!==a.auditHash)throw Error('Summary audit evidence file missing/changed');const disk=readJson(a.auditFile),withoutFile={...a};delete withoutFile.auditFile;delete withoutFile.auditHash;if(JSON.stringify(disk)!==JSON.stringify(withoutFile))throw Error('Summary audit file/record mismatch');if(report.deliveryRuleVersion!==DELIVERY_RULE_VERSION||report.colorRuleVersion!==COLOR_RULE_VERSION||report.dataRuleVersion!==DATA_RULE_VERSION||report.layout!=='figure-pages'||!a||a.ok!==true||a.ruleVersion!==DELIVERY_RULE_VERSION||a.colorRuleVersion!==COLOR_RULE_VERSION||fileHash(report.summaryAi)!==report.summaryAiHash||fileHash(report.summaryPdf)!==report.summaryPdfHash||a.aiHash!==report.summaryAiHash||a.pdfHash!==report.summaryPdfHash||a.pages!==report.items.length||a.figures?.length!==report.items.length)throw Error('Stale/incomplete current summary audit');
 for(let i=0;i<report.items.length;i++){
  const item=report.items[i],r=readJson(item.renderRecord),f=a.figures[i];assertColorAudit(r);assertDataAudit(r);
  if(fileHash(item.source)!==item.sourceHash||!r.dataAudit.checks.some(check=>check.evidenceFiles.some(e=>path.resolve(e.path)===path.resolve(item.source)&&e.sha256===item.sourceHash)))throw Error('Original source missing/changed in data audit');
  for(const [file,hashKey] of [['singleAi','singleAiHash'],['singlePdf','singlePdfHash'],['output','outputHash']])if(fileHash(item[file])!==item[hashKey])throw Error('Delivered single artifact changed');
  if(item.singleAiHash!==r.aiHash||item.singlePdfHash!==r.pdfHash||item.outputHash!==r.outputHash||item.renderSourceHash!==r.sourceHash||f.ok!==true||f.number!==item.number||f.author!==item.author||f.page!==item.page||f.aiHash!==r.aiHash||f.pdfHash!==r.pdfHash||f.outputHash!==r.outputHash||f.colorAuditHash!==sha256(JSON.stringify(r.colorAudit)))throw Error('Summary source/color bindings changed');
 }
 return a;
}
export function safeSegment(value){const bad=[60,62,58,34,47,92,124,63,42];let s=Array.from(String(value),c=>c.charCodeAt(0)<32||bad.includes(c.charCodeAt(0))?'_':c).join('').replace(/[. ]+$/,'').slice(0,80)||'unnamed';if(/^(con|prn|aux|nul|com[1-9]|lpt[1-9])([.]|$)/i.test(s))s='_'+s;return s;}
const safe=safeSegment;
function runSummaryAudit(requestFile){
 try{return JSON.parse(execFileSync(pythonRuntime(),[path.join(packageRoot,'scripts/audit_delivery.py'),requestFile],{encoding:'utf8',windowsHide:true,timeout:120000,env:{...process.env,PYTHONIOENCODING:'utf-8'}}));}
 catch(error){throw Error('Summary visual/color audit failed: '+String(error.stdout||error.message));}
}
function textIdentity(text){return JSON.stringify({text:text.text,font:text.font,fontFamily:text.fontFamily,size:Number(text.size.toFixed(3)),characterStyles:text.characterStyles||null});}
function exportEvidence(root,state,provided){
 const ref=provided||state.exportSetEvidence;if(!ref?.path||!ref.sha256)throw Error('Word-bound exportSetEvidence path/sha256 required');
 const file=path.resolve(root,ref.path);if(fileHash(file)!==ref.sha256)throw Error('Export-set evidence changed');const proof=readJson(file);
 if(!proof.evidence?.trim()||!proof.word?.path||!proof.word.sha256||fileHash(proof.word.path)!==proof.word.sha256||!Array.isArray(proof.items)||!proof.items.length||!Array.isArray(proof.expectedExportNumbers)||JSON.stringify(proof.expectedExportNumbers.map(String).sort())!==JSON.stringify(proof.items.map(item=>String(item.number)).sort()))throw Error('Current Word identity and complete export numbers required');
 return {path:file,sha256:ref.sha256,word:{path:path.resolve(proof.word.path),sha256:proof.word.sha256},expectedExportNumbers:proof.expectedExportNumbers.map(String),items:proof.items,evidence:proof.evidence};
}
function sourceEvidence(figure,record){
 const source=figure.originalSource||figure.originalPath||record.source,sourceHash=figure.originalSourceHash||figure.sourceHash;
 if(fileHash(source)!==sourceHash)throw Error('Original source identity changed: '+figure.id);
 const files=record.dataAudit.checks.flatMap(check=>check.evidenceFiles);
 if(!files.some(file=>path.resolve(file.path)===path.resolve(source)&&file.sha256===sourceHash))throw Error('Original source missing from independent data evidence: '+figure.id);
 return {source:path.resolve(source),sourceHash,renderSource:path.resolve(record.source),renderSourceHash:record.sourceHash,sources:[{role:'original',path:path.resolve(source),sha256:sourceHash},{role:'render-input',path:path.resolve(record.source),sha256:record.sourceHash},...files.map(file=>({role:'data-evidence',path:path.resolve(file.path),sha256:file.sha256}))]};
}
export function deliver(root,{draft=false,layout='figure-pages',expectedItems,exportSetEvidence,invoke=adobe,audit=runSummaryAudit}={}){
 if(layout!=='figure-pages')throw Error('Current deliver requires figure-pages; template is historical aggregate compatibility only');
 root=path.resolve(root);const state=readJson(path.join(root,'job.json')),exportProof=exportEvidence(root,state,exportSetEvidence),accepted=[],pending=[],expected=expectedItems||state.expectedExports||exportProof.items;
 const proofKeys=exportProof.items.map(item=>item.author+'\u0000'+String(item.number)).sort();if(JSON.stringify(proofKeys)!==JSON.stringify(expected.map(item=>item.author+'\u0000'+String(item.number)).sort()))throw Error('Expected exports differ from Word-bound evidence');
 if(!Array.isArray(expected)||!expected.length)throw Error('Complete export item manifest required');
 const identity=item=>item.author+'\u0000'+String(item.number),expectedKeys=expected.map(identity),actualKeys=state.figures.map(identity);
 if(new Set(expectedKeys).size!==expectedKeys.length||new Set(actualKeys).size!==actualKeys.length||expectedKeys.length!==actualKeys.length||expectedKeys.some(key=>!actualKeys.includes(key))||expected.some(item=>item.id&&!state.figures.some(figure=>figure.id===item.id&&identity(figure)===identity(item))))throw Error('Full export item set differs from job manifest');
 for(const figure of state.figures){
  if(!/^(?:4-1|\d+(?:\.\d+)?)$/.test(String(figure.number)))throw Error('Invalid full Word figure number');
  if(!figure.render||(!draft&&figure.status!=='accepted')){pending.push({id:figure.id,author:figure.author,number:String(figure.number),status:figure.status});continue;}
  const record=readJson(resolveInside(root,figure.render)),columnLabel=assertSingleRecord(root,figure,record),bindings=reviewBindings(record,columnLabel);
  if(!draft&&(figure.review?.decision!=='pass'||Object.keys(bindings).some(key=>figure.review[key]!==bindings[key])))throw Error('Stale review under current delivery/color/data rules: '+figure.id);
  accepted.push({figure,record,columnLabel,bindings,provenance:sourceEvidence(figure,record)});
 }
 if(!draft&&pending.length)throw Error('Incomplete reviewed export item set: '+pending.map(item=>item.number).join(','));
 if(!accepted.length)throw Error('No current audited figures to deliver');
 accepted.sort((a,b)=>(a.figure.author+' '+a.figure.number).localeCompare(b.figure.author+' '+b.figure.number,'zh-CN',{numeric:true}));
 const keys=accepted.map(({figure})=>(safe(figure.author)+'/'+safe(figure.author)+'-图'+safe(figure.number)).toLowerCase());if(new Set(keys).size!==keys.length)throw Error('Duplicate delivery author and figure number');
 const out=path.join(root,draft?'draft-delivery':'delivery',new Date().toISOString().replace(/[:.]/g,'-'));mkdirSync(out,{recursive:true});
 const items=accepted.map(({figure,record,columnLabel,bindings})=>({author:figure.author,number:String(figure.number),columnLabel,ai:record.ai,evidence:{...bindings,reviewHash:sha256(JSON.stringify(figure.review||null))}}));
 const aggregate=cachedAggregate(path.join(out,'audit'),{mode:'aggregate',layout:'figure-pages',reviewBadges:true,keepDocumentOpen:true,items},{invoke}),result=aggregate.result;
 if(result.pages!==accepted.length||result.groups?.length!==accepted.length||result.placements?.length!==accepted.length)throw Error('Aggregate page/item count mismatch');
 const badges=accepted.map(({figure,columnLabel})=>figure.author+' 图'+figure.number+' · '+columnLabel),badgeTexts=result.snapshot.texts.filter(text=>/^JFW_REVIEW_LABEL_\d+$/.test(text.name||''));
 if(badgeTexts.length!==badges.length||badges.some((badge,i)=>!badgeTexts.some(text=>text.name==='JFW_REVIEW_LABEL_'+i&&text.text===badge&&text.font==='ATC-73b000205b8b4f530020*1'&&Math.abs(text.size-7)<0.01)))throw Error('Editable author/full-number/column badges missing');
 const expectedText=accepted.flatMap(({record})=>record.adobe.snapshot.texts.map(textIdentity)).sort(),actualText=result.snapshot.texts.filter(text=>!/^JFW_REVIEW_LABEL_\d+$/.test(text.name||'')).map(textIdentity).sort();
 if(JSON.stringify(expectedText)!==JSON.stringify(actualText))throw Error('Aggregate changed source text/font/size/style inventory');
 const summaryAi=path.join(out,draft?'待复核汇总.ai':'汇总.ai'),summaryPdf=path.join(out,'汇总.pdf'),preview=path.join(out,'汇总预览.png');for(const [source,target] of [[aggregate.ai,summaryAi],[aggregate.pdf,summaryPdf],[aggregate.preview,preview]])copyFileSync(source,target);
 const auditDirectory=path.join(out,'audit','summary');mkdirSync(auditDirectory,{recursive:true});const auditRequest=path.join(auditDirectory,'request.json');
 writeJson(auditRequest,{ruleVersion:DELIVERY_RULE_VERSION,colorRuleVersion:COLOR_RULE_VERSION,layout:'figure-pages',ai:summaryAi,aiHash:fileHash(summaryAi),pdf:summaryPdf,pdfHash:fileHash(summaryPdf),directory:auditDirectory,items:accepted.map(({figure,record,columnLabel},i)=>({author:figure.author,number:String(figure.number),columnLabel,colorPolicy:record.colorAudit.policy,placement:result.placements[i],pdf:record.pdf,pdfHash:record.pdfHash,ai:record.ai,aiHash:record.aiHash,output:record.output,outputHash:record.outputHash,colorAuditHash:sha256(JSON.stringify(record.colorAudit))}))});
 const audited=audit(auditRequest),summaryAuditFile=path.join(auditDirectory,'summary-audit.json');if(!existsSync(summaryAuditFile)||JSON.stringify(readJson(summaryAuditFile))!==JSON.stringify(audited))throw Error('Independent summary audit file/result mismatch');const summaryAudit={...audited,auditFile:summaryAuditFile,auditHash:fileHash(summaryAuditFile)};if(summaryAudit?.ok!==true||summaryAudit.ruleVersion!==DELIVERY_RULE_VERSION||summaryAudit.colorRuleVersion!==COLOR_RULE_VERSION||summaryAudit.pdfHash!==fileHash(summaryPdf)||summaryAudit.aiHash!==fileHash(summaryAi)||summaryAudit.pages!==accepted.length||summaryAudit.figures?.length!==accepted.length)throw Error('Current summary audit required');
 for(const {figure,record,columnLabel,bindings} of accepted){assertSingleRecord(root,figure,record);if(JSON.stringify(reviewBindings(record,columnLabel))!==JSON.stringify(bindings))throw Error('Single evidence changed during delivery');}
 const delivered=accepted.map(({figure,record,columnLabel,bindings,provenance},i)=>{const dir=path.join(out,safe(figure.author)),stem=safe(figure.author)+'-图'+safe(figure.number);mkdirSync(dir,{recursive:true});const singleAi=path.join(dir,stem+'.ai'),singlePdf=path.join(dir,stem+'.pdf');copyFileSync(record.ai,singleAi);copyFileSync(record.pdf,singlePdf);let output=singlePdf;if(path.extname(record.output).toLowerCase()!=='.pdf'){output=path.join(dir,stem+path.extname(record.output));copyFileSync(record.output,output);}return {id:figure.id,author:figure.author,number:String(figure.number),columnLabel,page:i+1,status:figure.status,...provenance,renderRecord:resolveInside(root,figure.render),planFile:record.planFile,planHash:record.planHash,planFileHash:record.planFileHash,singleAi,singleAiHash:fileHash(singleAi),singlePdf,singlePdfHash:fileHash(singlePdf),ai:singleAi,aiHash:fileHash(singleAi),pdf:singlePdf,pdfHash:fileHash(singlePdf),output,outputHash:fileHash(output),reviewEvidence:figure.review?.evidence||'draft awaiting visual review',audit:{pdf:record.pdfAudit,data:record.dataAudit,color:record.colorAudit,summary:summaryAudit.figures[i]},bindings,placement:result.placements[i]};});
 const mainFigureCount=new Set(delivered.map(item=>item.author+'\u0000'+item.number.split('.')[0])).size,record={version:2,deliveryRuleVersion:DELIVERY_RULE_VERSION,colorRuleVersion:COLOR_RULE_VERSION,dataRuleVersion:DATA_RULE_VERSION,layout:'figure-pages',draft,readyForPublication:!draft,userFinalReview:false,status:draft?'待内部复核':'待用户终检',createdAt:new Date().toISOString(),summaryAi,summaryAiHash:fileHash(summaryAi),summaryPdf,summaryPdfHash:fileHash(summaryPdf),summary:{ai:summaryAi,pdf:summaryPdf,aiHash:fileHash(summaryAi),pdfHash:fileHash(summaryPdf)},summaryHash:fileHash(summaryAi),pdf:summaryPdf,preview,previewHash:fileHash(preview),summaryAudit,audit:summaryAudit,pages:result.pages,mainFigureCount,exportItemCount:delivered.length,expectedExportNumbers:exportProof.expectedExportNumbers,exportSetEvidence:exportProof,expectedExports:expected,items:delivered,reviewItems:delivered.map(item=>({id:item.id,author:item.author,number:item.number,status:item.status,evidence:item.reviewEvidence,mechanicalIssues:[]})),included:delivered.map(item=>item.id),accepted:delivered.filter(item=>item.status==='accepted').map(item=>item.id),pending,placements:result.placements,documentKeptOpen:result.documentKeptOpen,ownedInputsKeptOpen:result.ownedInputsKeptOpen,aggregateCache:{key:aggregate.key,manifest:aggregate.manifest,cached:aggregate.cached}};
 assertSummaryAudit(record);writeJson(path.join(out,'delivery-manifest.json'),record);writeJson(path.join(out,'delivery.json'),record);if(draft)writeFileSync(path.join(out,'待复核说明.txt'),'这是加工试样，尚待实际视觉复核及用户终检；不是可直接付印的终稿。','utf8');logEvent(root,{event:'delivered',path:out,count:accepted.length,pending:pending.length,layout:'figure-pages',deliveryRuleVersion:DELIVERY_RULE_VERSION});return record;
}

