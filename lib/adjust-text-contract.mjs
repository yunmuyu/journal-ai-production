import path from 'node:path';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
export const hash=value=>createHash('sha256').update(value).digest('hex');
export const fileHash=file=>hash(readFileSync(file));
const read=file=>JSON.parse(readFileSync(file,'utf8').replace(/^\uFEFF/,''));
function bound(file,digest){if(!file||!digest||!existsSync(file)||fileHash(file)!==digest)throw Error('Changed/missing text-only binding: '+file);return read(file);}
export function prepareTextAdjustment(request,tools){
 const allowed=['version','figureId','sourceHash','sourceAI','sourceAIHash','sourcePdf','sourcePdfHash','sourceSnapshotFile','sourceSnapshotHash','sourceRecordFile','sourceRecordHash','sourceColorAuditFile','sourceColorAuditHash','finalPlanFile','finalPlanHash','outputDirectory','edits'];
 if(Object.keys(request).some(k=>!allowed.includes(k))||request.version!==1||!request.figureId||!request.sourceHash||!request.outputDirectory)throw Error('Invalid text-only request fields');
 if(!request.sourceAI||fileHash(request.sourceAI)!==request.sourceAIHash||!request.sourcePdf||fileHash(request.sourcePdf)!==request.sourcePdfHash)throw Error('Changed source AI/PDF');
 const old=bound(request.sourceRecordFile,request.sourceRecordHash),raw=bound(request.sourceSnapshotFile,request.sourceSnapshotHash),audit=bound(request.sourceColorAuditFile,request.sourceColorAuditHash),plan=bound(request.finalPlanFile,request.finalPlanHash),snapshot=raw.snapshot||raw.adobe?.snapshot;
 if(old.ok!==true||old.figureId!==request.figureId||old.sourceHash!==request.sourceHash||old.aiHash!==request.sourceAIHash||old.pdfHash!==request.sourcePdfHash||old.ai!==request.sourceAI||old.pdf!==request.sourcePdf||old.pdfAudit?.ok!==true||old.adobe?.mechanicalIssues?.length!==0||!snapshot?.pathGeometry||JSON.stringify(snapshot)!==JSON.stringify(old.adobe.snapshot))throw Error('Unbound/failed old render or native snapshot');
 if(audit.ok!==true||audit.pixelAudit?.ok!==true||audit.objectAudit?.ok!==true||audit.bindings?.aiHash!==request.sourceAIHash||audit.bindings?.pdfHash!==request.sourcePdfHash||audit.bindings?.sourceHash!==request.sourceHash||old.colorAudit?.auditHash!==request.sourceColorAuditHash||JSON.stringify(old.colorAudit.bindings)!==JSON.stringify(audit.bindings))throw Error('Old final color audit does not bind this AI/PDF');
 for(const key of ['source','planFile','pdf','output','ai','preview']){const h=key==='planFile'?'planFileHash':key+'Hash';if(!old[key]||fileHash(old[key])!==old[h]||audit.bindings[h]!==old[h])throw Error('Old artifact/color cross-binding mismatch: '+key);}
 if(audit.bindings.planHash!==old.planHash||audit.bindings.toolFingerprint!==hash(old.toolHashes.map(t=>t.sha256).join('')))throw Error('Old plan/tool fingerprint binding mismatch');
 if(old.adobe.ok!==true||raw.ok!==true||raw.mechanicalIssues?.length!==0)throw Error('Old native snapshot did not pass');
 if(plan.figureId!==request.figureId||plan.sourceHash!==request.sourceHash)throw Error('Final plan identity changed');
 for(const p of snapshot.pathGeometry){if(!Array.isArray(p.points)||typeof p.closed!=='boolean'||typeof p.clipping!=='boolean')throw Error('Incomplete protected path topology');for(const point of p.points)if(point.length!==2||point[0].length!==4||point[1].length!==2||!point.flat().every(Number.isFinite))throw Error('Incomplete protected double coordinates');}
 if(!Array.isArray(request.edits)||!request.edits.length)throw Error('No text-only edits');const seen=new Set();
 for(const edit of request.edits){
  if(Object.keys(edit).some(k=>!['index','expected','dx','dy','fontSize','anchor'].includes(k))||!Number.isInteger(edit.index)||edit.index<0||seen.has(edit.index))throw Error('Forbidden/duplicate text-only edit');seen.add(edit.index);
  const t=snapshot.texts[edit.index],e=edit.expected;
  if(!t||!e||Object.keys(e).some(k=>!['text','size','inkBounds'].includes(k))||t.index!==edit.index||e.text!==t.text||e.size!==t.size||JSON.stringify(e.inkBounds)!==JSON.stringify(t.inkBounds))throw Error('Text expected identity/size/bounds mismatch');
  if((edit.fontSize!==undefined&&(!Number.isFinite(edit.fontSize)||edit.fontSize<6||edit.fontSize>8))||[edit.dx??0,edit.dy??0].some(v=>!Number.isFinite(v))||!['left','center','right'].includes(edit.anchor||'center'))throw Error('Text size/translation/anchor invalid');
  if(edit.fontSize!==undefined&&((t.characterStyles||[]).length||!/^[0-9 .,\-−]+$/.test(t.text)))throw Error('Font size edits require plain numeric text');
  if(edit.fontSize===undefined&&edit.dx===undefined&&edit.dy===undefined)throw Error('Empty text edit');
 }
 if(!tools?.length||tools.some(t=>fileHash(t.file)!==t.sha256))throw Error('Text adjustment tool changed');
 return {kind:'controlled-text-v1',operation:'text-only',sourceAIHash:request.sourceAIHash,sourceSnapshotHash:request.sourceSnapshotHash,sourceColorAuditHash:request.sourceColorAuditHash,pathGeometryHash:hash(JSON.stringify(snapshot.pathGeometry)),pathGeometry:structuredClone(snapshot.pathGeometry),sourceTexts:structuredClone(snapshot.texts),sourceArtboard:structuredClone(snapshot.artboard),toolHashes:tools.map(t=>({...t})),edits:structuredClone(request.edits)};
}
export function assertTextAdjustmentRequest(request){
 if(request.mode!=='adjust-text')return;
 const current=prepareTextAdjustment(request.textAdjustmentRequest,request.textOnlyEvidence.toolHashes),given=request.textOnlyEvidence;
 const privateInput=path.join(path.dirname(request.ai),'protected-source.ai');
 if(path.resolve(request.ai)!==path.join(path.resolve(request.textAdjustmentRequest.outputDirectory),'figure.ai')||path.resolve(request.input)!==privateInput||path.resolve(request.input)===path.resolve(request.textAdjustmentRequest.sourceAI)||fileHash(request.input)!==current.sourceAIHash||JSON.stringify(current)!==JSON.stringify(given)||request.preflightInputHash!==current.sourceAIHash)throw Error('Changed text-only execution evidence');
}
