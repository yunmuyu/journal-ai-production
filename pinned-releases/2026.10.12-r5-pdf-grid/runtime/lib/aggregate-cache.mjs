import {existsSync,mkdirSync,mkdtempSync} from 'node:fs';
import path from 'node:path';
import {adobe,packageRoot} from './adobe.mjs';
import {fileHash,readJson,writeJson,sha256} from './core.mjs';
import {COLOR_RULE_VERSION} from './color-policy.mjs';
import {DATA_RULE_VERSION} from './data-audit.mjs';

export const DELIVERY_RULE_VERSION='jfw-delivery-2026-10-11-v1';
const drivers=['common.jsx','invoke.js','illustrator.jsx','editorial-generator.jsx','vector-labels.jsx','editorial-parallel.jsx','editorial-bars.jsx','editorial-aggregate.jsx','editorial-review-pages.jsx','editorial-copy.jsx'];
function fingerprint(request){
 const layout=request.layout||'figure-pages';if(!['figure-pages','template'].includes(layout))throw Error('Unknown aggregate layout');
 if(layout==='figure-pages'&&request.reviewBadges!==true)throw Error('Figure pages require editable review badges');
 const template=layout==='template'?{template:path.resolve(request.template),templateHash:fileHash(request.template)}:{};
 return {version:4,deliveryRuleVersion:DELIVERY_RULE_VERSION,colorRuleVersion:COLOR_RULE_VERSION,dataRuleVersion:DATA_RULE_VERSION,reviewBadges:request.reviewBadges===true,layout,batchCopy:request.batchCopy===true,...template,
  items:request.items.map(item=>{if(layout==='figure-pages'&&item.columnLabel!=='单栏'&&item.columnLabel!=='双栏')throw Error('Confirmed column required');return {author:item.author,number:String(item.number),columnLabel:item.columnLabel||null,ai:path.resolve(item.ai),aiHash:fileHash(item.ai),evidence:item.evidence||null,colorAuditHash:item.colorAudit?sha256(JSON.stringify(item.colorAudit)):null};}),
  drivers:drivers.map(name=>({name,hash:fileHash(path.join(packageRoot,'adobe',name))})),deliveryTools:['lib/review.mjs','lib/color-policy.mjs','lib/data-audit.mjs','scripts/audit_delivery.py'].map(name=>({name,hash:fileHash(path.join(packageRoot,name))}))};
}
function valid(entry,key){return entry.key===key&&entry.manifest?.version===4&&entry.result?.ok===true&&entry.files.every(item=>existsSync(item.path)&&fileHash(item.path)===item.sha256);}
export function cachedAggregate(directory,request,{invoke=adobe,auditOnly=false}={}){
 if(request.mode!=='aggregate'||!request.items?.length)throw Error('Aggregate inputs required');
 request={...request,layout:request.layout||'figure-pages'};const manifest=fingerprint(request),key=sha256(JSON.stringify(manifest)),cacheFile=path.join(directory,'aggregate-cache',key+'.json');
 if(existsSync(cacheFile)){const entry=readJson(cacheFile);if(valid(entry,key))return {...entry,cached:true};}
 if(auditOnly)throw Error('No verified cached aggregate for current inputs');
 const runRoot=path.join(directory,'aggregate-runs');mkdirSync(runRoot,{recursive:true});const attempt=mkdtempSync(path.join(runRoot,key.slice(0,16)+'-'));
 const ai=path.join(attempt,'author.ai'),pdf=path.join(attempt,'summary.pdf'),preview=path.join(attempt,'native.png');writeJson(path.join(attempt,'input-manifest.json'),{key,manifest,status:'started'});
 try{
  const result=invoke('illustrator',{...request,ai,pdf,preview},attempt);if(!result.ok||result.groups?.length!==request.items.length)throw Error('Incomplete aggregate');
  if(JSON.stringify(fingerprint(request))!==JSON.stringify(manifest))throw Error('Aggregate inputs changed during execution');
  const files=[ai,pdf,preview].map(file=>({path:file,sha256:fileHash(file)})),entry={key,manifest,ai,pdf,preview,attempt,result,files,createdAt:new Date().toISOString()};writeJson(cacheFile,entry);writeJson(path.join(attempt,'input-manifest.json'),{key,manifest,status:'completed'});return {...entry,cached:false};
 }catch(error){writeJson(path.join(attempt,'input-manifest.json'),{key,manifest,status:'failed',error:String(error.message||error)});throw error;}
}
