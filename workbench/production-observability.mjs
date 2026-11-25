import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {verifiedDeliveryState} from './delivery-checklist.mjs';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const identity=r=>[r.origin,r.batchHash,r.articleId,r.figureId];
const receiptId=r=>sha(JSON.stringify([...identity(r),r.outputs]));

export function classifyProductionFailure(error,stage='unknown'){
 const message=error?.message??String(error);let code='unknown',action='inspect_logs';
 if(error?.code==='three_minute_deadline'){code='deadline_exceeded';action='record_stage_and_skip';}
 else if(error?.code==='known_fault'){code='known_fault';action=error.failureAction==='correct_plan'?'correct_plan':'wait_for_verified_fix';}
 else if(message==='Plan baseline is stale'||message==='Figure changed during processing'){code='stale_version';action='refresh_plan';}
 else if(['series_binding_source_changed','binding_evidence_changed'].includes(message)){code='source_changed';action='verify_source';}
 else if(['series_binding_confirmation_required','series_binding_incomplete','series_binding_conflict','series_binding_duplicate'].includes(message)){code='needs_bindings';action='provide_semantic_binding';}
 else if(message.startsWith('Source or evidence changed:')||message==='Registered source changed'){code='source_changed';action='verify_source';}
 else if(stage==='claim'){code='claim_blocked';action='inspect_owner';}
 else if(['Workbench preview unavailable','Workbench unavailable','Workbench download unavailable'].includes(message)){code='visibility_unavailable';action='verify_existing_candidate';}
 else if(['Workbench output hash mismatch','Workbench download failed verification','Workbench output set not visible'].includes(message)){code='visible_output_conflict';action='inspect_workbench';}
 else if(error?.name==='TimeoutError'||error?.name==='AbortError'||['ECONNRESET','ECONNREFUSED','ETIMEDOUT'].includes(error?.cause?.code)){code='transport_failure';action='verify_existing_candidate';}
 else if(stage==='preflight'){code='plan_rejected';action='correct_plan';}
 else if(stage==='render'){code='render_failed';action='inspect_tool';}
 else if(stage==='check'){code='quality_gate_failed';action='inspect_quality_report';}
 else if(stage==='prepare'||stage==='publish'){code='publication_failed';action='inspect_server_state';}
 return {code,stage,action,automaticRetry:false,message};
}

function validateReceipt(r){
 if(r?.type!=='production-delivery'||r.version!==1||typeof r.historical!=='boolean'||!r.figureId||!r.articleId||!r.batchHash||!r.origin||!['ordinary','revision'].includes(r.kind)||!Number.isFinite(Date.parse(r.returnedAt))||!Array.isArray(r.outputs)||!r.outputs.length||
  r.outputs.some(o=>typeof o.number!=='string'||!o.number||!/^[a-f0-9]{64}$/.test(o.sha256))||new Set(r.outputs.map(o=>o.number)).size!==r.outputs.length||receiptId(r)!==r.id)throw Error('invalid_delivery_receipt');
 return r;
}

// Only this boundary may create a successful receipt, after observing the authoritative workbench.
export async function verifyProductionDelivery(config,request){
 const origin=new URL(config.origin).origin;
 const get=url=>fetch(new URL(url,origin),{redirect:'error',signal:AbortSignal.timeout(30000)});
 const response=await get('/data');if(!response.ok)throw Error('Workbench unavailable');
 const rows=(await response.json()).rows.filter(f=>request.figureId?f.id===request.figureId:f.articleId===request.articleId&&f.number===request.figureNumber);
 const f=rows[0],expected=request.outputs;
 if(rows.length!==1||!f?.id||!f.articleId||!['待终检','终检通过'].includes(f.status)||!Array.isArray(expected)||!expected.length||f.outputs?.length!==expected.length||new Set(expected.map(o=>o.number)).size!==expected.length)throw Error('Workbench output set not visible');
 for(const o of expected){
  const actual=f.outputs.find(a=>a.number===o.number);
  if(!/^[a-f0-9]{64}$/.test(o.sha256)||actual?.file?.meta?.sha256!==o.sha256||!actual.file.token)throw Error('Workbench output hash mismatch');
  const file=await get('/file/'+encodeURIComponent(actual.file.token));if(!file.ok)throw Error('Workbench download unavailable');
  if(sha(Buffer.from(await file.arrayBuffer()))!==o.sha256)throw Error('Workbench download failed verification');
  const preview=await get('/preview/'+encodeURIComponent(actual.file.token));if(!preview.ok||!(await preview.arrayBuffer()).byteLength)throw Error('Workbench preview unavailable');
 }
 const latestResponse=await get('/data');if(!latestResponse.ok)throw Error('Workbench unavailable');
 const latest=(await latestResponse.json()).rows.find(row=>row.id===f.id);
 if(!latest||latest.reviewVersion!==f.reviewVersion||latest.articleId!==f.articleId||!['待终检','终检通过'].includes(latest.status)||latest.outputs?.length!==expected.length||
  !expected.every(o=>latest.outputs.some(a=>a.number===o.number&&a.file?.meta?.sha256===o.sha256)))throw Error('Workbench output set not visible');
 const receipt={version:1,type:'production-delivery',origin,batchHash:request.batchHash,articleId:f.articleId,figureId:f.id,author:f.author??null,editor:f.editor??null,number:f.number,
  kind:request.kind??'ordinary',historical:request.historical===true,returnedAt:new Date().toISOString(),outputs:expected.map(o=>({number:o.number,sha256:o.sha256})).sort((a,b)=>a.number.localeCompare(b.number))};
 receipt.id=receiptId(receipt);validateReceipt(receipt);
 fs.mkdirSync(config.receiptRoot,{recursive:true});const file=path.join(config.receiptRoot,receipt.id+'.json');
 try{fs.writeFileSync(file,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});return {figure:latest,receipt,newReceipt:true,deliveryState:verifiedDeliveryState(latest,receipt)};}
 catch(error){if(error.code!=='EEXIST')throw error;const existing=validateReceipt(read(file));if(existing.id!==receipt.id)throw Error('receipt_identity_conflict');return {figure:latest,receipt:existing,newReceipt:false,deliveryState:verifiedDeliveryState(latest,existing)};}
}

export function productionReport({receiptRoots,from,to}){
 const start=Date.parse(from),end=Date.parse(to);
 if(typeof from!=='string'||typeof to!=='string'||!/(Z|[+-]\d\d:\d\d)$/.test(from)||!/(Z|[+-]\d\d:\d\d)$/.test(to)||!Number.isFinite(start)||!Number.isFinite(end)||end<=start)throw Error('invalid_report_window');
 if(!Array.isArray(receiptRoots)||!receiptRoots.length)throw Error('receipt_roots_required');
 const records=new Map();
 for(const root of new Set(receiptRoots.map(r=>fs.realpathSync(r))))for(const file of fs.readdirSync(root).filter(f=>f.endsWith('.json'))){
  const r=validateReceipt(read(path.join(root,file))),old=records.get(r.id);
  if(old&&JSON.stringify(old)!==JSON.stringify(r))throw Error('conflicting_duplicate_receipt');records.set(r.id,r);
 }
 const selected=[...records.values()].filter(r=>!r.historical&&Date.parse(r.returnedAt)>=start&&Date.parse(r.returnedAt)<end),figures=new Set(),outputs=new Set();
 for(const r of selected){figures.add(JSON.stringify(identity(r)));for(const o of r.outputs)outputs.add(JSON.stringify([...identity(r),o.number,o.sha256]));}
 const hours=(end-start)/3600000;
 return {version:1,from,to,windowHours:hours,deliveredFigures:figures.size,deliveredOutputs:outputs.size,deliveryEvents:selected.length,historicalReceipts:[...records.values()].filter(r=>r.historical).length,
  revisionDeliveries:selected.filter(r=>r.kind==='revision').length,figuresPerHour:figures.size/hours,outputsPerHour:outputs.size/hours,
  deliveries:selected.sort((a,b)=>a.returnedAt.localeCompare(b.returnedAt))};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{if(process.argv.length!==3)throw Error('Usage: node production-observability.mjs report-window.json');console.log(JSON.stringify(productionReport(read(process.argv[2])),null,2));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
