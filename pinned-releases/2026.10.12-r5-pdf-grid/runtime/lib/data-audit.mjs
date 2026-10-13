import path from 'node:path';
import {readJson,writeJson,fileHash,resolveInside,logEvent} from './core.mjs';
import {artifactBindings,assertArtifactBindings} from './color-policy.mjs';
export const DATA_RULE_VERSION='jfw-data-2026-10-11-v1';
const kinds=new Set(['paths','pixels','values','topology']);
function validateChecks(checks){
 if(!Array.isArray(checks)||!checks.length)throw Error('Independent data or geometry checks required');
 for(const check of checks){
  if(!kinds.has(check.kind)||typeof check.preservedObjects!=='string'||!check.preservedObjects.trim()||typeof check.evidence!=='string'||!check.evidence.trim())throw Error('Explicit preserved objects and observed data evidence required');
  if(!Array.isArray(check.evidenceFiles)||!check.evidenceFiles.length)throw Error('Data checks require source and output evidence files');
  for(const file of check.evidenceFiles)if(typeof file.path!=='string'||! /^[a-f0-9]{64}$/.test(file.sha256||'')||fileHash(file.path)!==file.sha256)throw Error('Data evidence file changed or missing');
 }
}
export function assertDataAudit(record){
 const audit=record.dataAudit;
 if(audit?.ok!==true||audit.ruleVersion!==DATA_RULE_VERSION||typeof audit.evidence!=='string'||!audit.evidence.trim()||!audit.reviewedAt)throw Error('Current independent data review required');
 assertArtifactBindings(record,audit.bindings);validateChecks(audit.checks);return audit;
}
export function recordDataReview(root,id,{checks,evidence}={}){
 if(typeof evidence!=='string'||!evidence.trim())throw Error('Explicit source and final output observations required');
 root=path.resolve(root);const figure=readJson(path.join(root,'job.json')).figures.find(item=>item.id===id);
 if(!figure?.render)throw Error('No current render for data review');
 const file=resolveInside(root,figure.render),record=readJson(file),bindings=artifactBindings(record);
 assertArtifactBindings(record,bindings);validateChecks(checks);
 record.dataAudit={ok:true,ruleVersion:DATA_RULE_VERSION,bindings,checks,evidence,reviewedAt:new Date().toISOString()};
 assertDataAudit(record);writeJson(file,record);writeJson(path.join(path.dirname(file),'data-review.json'),record.dataAudit);
 logEvent(root,{event:'data_review',id,ruleVersion:DATA_RULE_VERSION,bindings,evidence});return record.dataAudit;
}
