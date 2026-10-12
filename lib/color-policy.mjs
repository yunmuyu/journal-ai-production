import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
export const COLOR_RULE_VERSION='jfw-color-2026-10-11-v1';
export const COLOR_APPROVAL_REGISTRY=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../../control/color-approvals.json');
const hash=value=>createHash('sha256').update(value).digest('hex');
const fileHash=file=>hash(readFileSync(file));
const read=file=>JSON.parse(readFileSync(file,'utf8').replace(/^\uFEFF/,''));
export function validateColorPlan(p){
 if(p.colorPolicy!==undefined&&!['grayscale','source-color'].includes(p.colorPolicy))throw Error('Unknown color policy');
 if(p.grayscale!==undefined&&typeof p.grayscale!=='boolean')throw Error('grayscale must be boolean');
 if(p.colorPolicy==='source-color'&&(typeof p.colorApprovalId!=='string'||!p.colorApprovalId.trim()))throw Error('Source color requires registered user approval');
 if(p.colorPolicy!=='source-color'&&p.colorApprovalId!==undefined)throw Error('Color approval only applies to source-color policy');
}
export function resolveColorPolicy(p,sourceHash){
 validateColorPlan(p);
 if(p.colorPolicy!=='source-color')return {mode:'grayscale',ruleVersion:COLOR_RULE_VERSION,approval:null};
 if(!existsSync(COLOR_APPROVAL_REGISTRY))throw Error('No trusted color approval registry');
 const registry=read(COLOR_APPROVAL_REGISTRY),a=(registry.approvals||[]).find(x=>x.id===p.colorApprovalId);
 if(registry.version!==1||!a||a.status!=='approved'||a.policy!=='source-color'||a.sourceHash!==sourceHash||a.approvedBy!=='user')throw Error('Source color approval does not match current source/user');
 const e=a.userEvidence;if(!e||typeof e.file!=='string'||!path.isAbsolute(e.file)||!/^[a-f0-9]{64}$/.test(e.sha256||'')||!e.quote||!/彩色|保留颜色|source.color|retain.*colou?r/i.test(e.quote)||!existsSync(e.file)||fileHash(e.file)!==e.sha256||!readFileSync(e.file,'utf8').includes(e.quote))throw Error('Explicit user color approval evidence missing or changed');
 return {mode:'source-color',ruleVersion:COLOR_RULE_VERSION,approval:{id:a.id,registryFile:COLOR_APPROVAL_REGISTRY,registryHash:fileHash(COLOR_APPROVAL_REGISTRY),sourceHash,evidenceFile:e.file,evidenceHash:e.sha256,quote:e.quote}};
}
export function colorPlanHash(plan,tools,policy){return hash(JSON.stringify(plan)+tools.map(x=>x.sha256).join('')+JSON.stringify(policy)+COLOR_RULE_VERSION);}
export function artifactBindings(record){
 const bindings={sourceHash:record.sourceHash,planHash:record.planHash,planFileHash:record.planFileHash,pdfHash:record.pdfHash,outputHash:record.outputHash,aiHash:record.aiHash,previewHash:record.previewHash,toolFingerprint:hash((record.toolHashes||[]).map(x=>x.sha256).join(''))};
 assertArtifactBindings(record,bindings);return bindings;
}
export function assertArtifactBindings(record,bindings){
 for(const key of ['source','planFile','pdf','output','ai','preview']){const h=key==='planFile'?'planFileHash':key+'Hash';if(!record[key]||!existsSync(record[key])||fileHash(record[key])!==record[h]||bindings?.[h]!==record[h])throw Error('Artifact current file/hash mismatch: '+key);}
 const p=read(record.planFile);if(p.sourceHash!==record.sourceHash)throw Error('Artifact plan/source binding mismatch');
 if(!Array.isArray(record.toolHashes)||!record.toolHashes.length)throw Error('Missing current artifact tool fingerprint');
 for(const relative of ['color-policy.mjs','core.mjs','render.mjs','../scripts/normalize_svg_color.py','../scripts/audit_color.py']){const required=path.resolve(path.dirname(fileURLToPath(import.meta.url)),relative),name=path.basename(required),matches=record.toolHashes.filter(t=>path.basename(t.file||'')===name);if(!matches.length||(['color-policy.mjs','normalize_svg_color.py','audit_color.py'].includes(name)&&!matches.some(t=>t.sha256===fileHash(required))))throw Error('Required current artifact tool missing: '+relative);}
 for(const t of record.toolHashes)if(!t.file||!existsSync(t.file)||fileHash(t.file)!==t.sha256)throw Error('Artifact tool revision changed');
 const fingerprint=hash(record.toolHashes.map(x=>x.sha256).join(''));if(bindings.toolFingerprint!==fingerprint||bindings.planHash!==record.planHash||colorPlanHash(p,record.toolHashes,record.colorPolicy)!==record.planHash)throw Error('Artifact plan/tool fingerprint mismatch');
 return bindings;
}
export function assertColorAudit(record){
 const a=record?.colorAudit;if(!a||a.ok!==true||a.ruleVersion!==COLOR_RULE_VERSION)throw Error('Missing/current color audit required');
 assertArtifactBindings(record,a.bindings);
 const p=read(record.planFile),policy=resolveColorPolicy(p,record.sourceHash);if(JSON.stringify(policy)!==JSON.stringify(record.colorPolicy)||a.policy!==policy.mode||JSON.stringify(a.approval)!==JSON.stringify(policy.approval))throw Error('Color policy/approval changed');
 if(!a.auditFile||!existsSync(a.auditFile)||fileHash(a.auditFile)!==a.auditHash)throw Error('Independent color report changed/missing');
 const disk=read(a.auditFile),withoutFile={...a};delete withoutFile.auditFile;delete withoutFile.auditHash;if(JSON.stringify(disk)!==JSON.stringify(withoutFile))throw Error('Color report/record evidence mismatch');
 if(a.pixelAudit?.method!=='pdfium-rgb-300dpi-neutral-v1'||a.pixelAudit.tolerance!==2||a.pixelAudit.pages<1||a.objectAudit?.ok!==true)throw Error('Independent final-PDF color method missing');
 if(policy.mode==='grayscale'&&(a.pixelAudit.ok!==true||a.pixelAudit.coloredPixels!==0))throw Error('Final PDF contains color');
 return a;
}

