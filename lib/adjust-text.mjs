import {auditDiagram} from './diagram-audit.mjs';
import path from 'node:path';
import {mkdirSync,existsSync,copyFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {adobe,packageRoot} from './adobe.mjs';
import {readJson,writeJson,fileHash,sha256,validatePlan,resolveInside,logEvent} from './core.mjs';
import {COLOR_RULE_VERSION,resolveColorPolicy,colorPlanHash,assertColorAudit} from './color-policy.mjs';
import {prepareTextAdjustment} from './adjust-text-contract.mjs';
import {pythonRuntime} from './ingest.mjs';
import {withAdobeSession} from './desktop-notice.mjs';
import {updateFigure} from './jobs.mjs';
export function adjustText(root,requestFile){return withAdobeSession(['Illustrator'],()=>adjust(root,requestFile));}
function adjust(root,requestFile){
 const start=Date.now();root=path.resolve(root);const request=readJson(requestFile),old=readJson(request.sourceRecordFile),p=validatePlan(readJson(request.finalPlanFile));
 const state=readJson(path.join(root,'job.json')),figure=state.figures.find(f=>f.id===request.figureId);if(!figure||figure.sourceHash!==request.sourceHash)throw Error('Unknown/changed adjustment figure');
 const source=resolveInside(root,figure.source);if(fileHash(source)!==request.sourceHash)throw Error('Adjustment manuscript source changed');
 const policy=resolveColorPolicy(p,request.sourceHash);if(JSON.stringify(policy)!==JSON.stringify(old.colorPolicy))throw Error('Text-only cannot change color policy');
 const files=[...(old.toolHashes||[]).map(t=>t.file),...['lib/adjust-text.mjs','lib/adjust-text-contract.mjs','lib/adobe.mjs','adobe/illustrator.jsx','adobe/text-only.jsx','scripts/jfw.mjs','lib/render.mjs','lib/core.mjs','lib/color-policy.mjs','scripts/audit_pdf.py','scripts/audit_color.py'].map(f=>path.join(packageRoot,f))];
 const toolHashes=[...new Set(files)].map(file=>({file,sha256:fileHash(file)})),evidence=prepareTextAdjustment(request,toolHashes);
 const directory=path.resolve(request.outputDirectory);if(!directory.startsWith(path.join(root,'renders')+path.sep)||existsSync(directory))throw Error('Text-only requires a new directory inside this job renders/');
 const plan={...p,textOnlyAdjustment:{kind:evidence.kind,operation:evidence.operation,requestFile:path.resolve(requestFile),requestHash:fileHash(requestFile),sourceAIHash:request.sourceAIHash,sourceSnapshotHash:request.sourceSnapshotHash,edits:request.edits}},planHash=colorPlanHash(plan,toolHashes,policy);
 mkdirSync(directory,{recursive:true});const planFile=path.join(directory,'plan.json');writeJson(planFile,plan);copyFileSync(requestFile,path.join(directory,'adjustment-request.json'));
 const protectedSource=path.join(directory,'protected-source.ai');copyFileSync(request.sourceAI,protectedSource);if(fileHash(protectedSource)!==request.sourceAIHash)throw Error('Private source AI copy hash mismatch');
 const ai=path.join(directory,'figure.ai'),pdf=path.join(directory,'figure.pdf'),preview=path.join(directory,'preview.png');
 const result=adobe('illustrator',{mode:'adjust-text',input:protectedSource,preflightInputHash:request.sourceAIHash,keepDocumentOpen:false,textAdjustmentRequest:request,textOnlyEvidence:evidence,ai,pdf,preview},path.join(directory,'adjust-text'));
 if(result.ok!==true||!Array.isArray(result.mechanicalIssues)||result.mechanicalIssues.length||result.closeError||result.restoreError)throw Error('Text adjustment native/mechanical verification failed');
 if(p.diagramKind||p.route==='rebuild'&&['flowchart','blockDiagram','signalFlow'].includes(p.graph?.kind||'flowchart')){result.diagramAudit=auditDiagram(result.snapshot,{checkPathContainment:p.checkPathContainment===true,expectedNodeIds:(p.graph?.nodes||[]).filter(n=>n.text&&['process','terminator','ellipse','decision'].includes(n.shape)).map(n=>n.id)});if(result.diagramAudit.issues.length)throw Error('Adjusted diagram audit failed');}
 const pdfPreview=path.join(directory,'pdf-preview.png'),pdfAudit=JSON.parse(execFileSync(pythonRuntime(),[path.join(packageRoot,'scripts/audit_pdf.py'),pdf,preview,pdfPreview,p.route],{encoding:'utf8',windowsHide:true,timeout:60000,env:{...process.env,PYTHONIOENCODING:'utf-8'}}));if(pdfAudit.ok!==true||pdfAudit.strokeAudit?.ok!==true)throw Error('Adjusted PDF/actual stroke audit failed');
 const normalizationFile=path.join(directory,'color-normalization.json');writeJson(normalizationFile,{ok:true,kind:'previously-verified-color-preserved-text-only',sourceAIHash:request.sourceAIHash,priorColorAuditHash:request.sourceColorAuditHash});
 const record={ok:true,figureId:request.figureId,source,sourceHash:request.sourceHash,sourceAIHash:request.sourceAIHash,sourceSnapshotHash:request.sourceSnapshotHash,finalPlanFile:request.finalPlanFile,finalPlanHash:request.finalPlanHash,sourceRecordFile:request.sourceRecordFile,sourceRecordHash:request.sourceRecordHash,planFile,planFileHash:fileHash(planFile),planHash,toolHashes,colorPolicy:policy,colorNormalization:readJson(normalizationFile),colorNormalizationFile:normalizationFile,colorNormalizationHash:fileHash(normalizationFile),ai,aiHash:fileHash(ai),pdf,pdfHash:fileHash(pdf),output:pdf,outputHash:fileHash(pdf),preview,previewHash:fileHash(preview),durationMs:Date.now()-start,adobe:result,pdfAudit,pdfPreview,geometryEvidence:result.geometryEvidence};
 const bindings={sourceHash:record.sourceHash,planHash,planFileHash:record.planFileHash,pdfHash:record.pdfHash,outputHash:record.outputHash,aiHash:record.aiHash,previewHash:record.previewHash,toolFingerprint:sha256(toolHashes.map(t=>t.sha256).join(''))},auditFile=path.join(directory,'color-audit.json'),colorRequest=path.join(directory,'color-audit-request.json');
 writeJson(colorRequest,{ruleVersion:COLOR_RULE_VERSION,policy:policy.mode,approval:policy.approval,bindings,route:p.route,source,planFile,pdf,output:pdf,ai,preview,report:auditFile});execFileSync(pythonRuntime(),[path.join(packageRoot,'scripts/audit_color.py'),colorRequest],{encoding:'utf8',windowsHide:true,timeout:60000,env:{...process.env,PYTHONIOENCODING:'utf-8'}});
 record.colorAudit={...readJson(auditFile),auditFile,auditHash:fileHash(auditFile)};assertColorAudit(record);record.durationMs=Date.now()-start;writeJson(path.join(directory,'render.json'),record);updateFigure(root,request.figureId,{status:'needs_review',render:path.relative(root,path.join(directory,'render.json')),planHash});logEvent(root,{event:'adjusted_text',id:request.figureId,planHash,sourceAIHash:request.sourceAIHash,sourceSnapshotHash:request.sourceSnapshotHash});return record;
}
