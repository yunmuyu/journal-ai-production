import fs from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import path from 'node:path';
const digest=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
export function userAccepted(record){
 if(record?.userAcceptance?.accepted===false)return false;
 return record?.status==='用户最终验收通过'||record?.status==='最终验收通过'&&(record.userAcceptance?.accepted===true||typeof record.userAcceptance==='string'&&/用户/.test(record.userAcceptance)&&/通过|都过了/.test(record.userAcceptance));
}
// Rebuildable internal index, never a production-state writer.
export function refreshIndex({inventory,production,evidence}){
 const byId=new Map((evidence.cases||[]).map(c=>[c.id,c]));
 const cases=[];
 for(const figure of inventory.figures){
  const record=production.figures[figure.id];if(!userAccepted(record))continue;
  const supplied=byId.get(figure.id);
  const sourceVersion=digest({figure,record});
  const currentOutputs=record.subfigures||[record];
  const fingerprint=c=>c.map(x=>x.outputHash||x.sha256||'').filter(Boolean).sort().join(':');
  const evidenceCurrent=!!supplied&&currentOutputs.length>0&&(supplied.finalOutputs||[]).length===currentOutputs.length&&supplied.finalOutputs.every(x=>x.exists===true&&x.hashCheck==='match')&&fingerprint(currentOutputs)===fingerprint(supplied.finalOutputs||[])&&
    JSON.stringify(supplied.acceptanceEvidence?.userAcceptance)===JSON.stringify(record.userAcceptance);
  const review=String(record.review||'');
  // Content tags alone cannot establish the executed route or structural relation.
  const method=/(?:重建|重绘)/.test(review)&&!/(?:不|未|没有).{0,3}(?:重建|重绘)/.test(review)?'redraw':
    /(?:保留|不改).{0,15}(?:曲线|图形|原对象|矢量)/.test(review)&&/换字|文字/.test(review)?'relabel':null;
  const structure=/节点|连接关系|区域框|流程/.test(review)?'node-link':/曲线|坐标|图例/.test(review)?'chart':null;
  const sourceFormats=[...new Set((supplied?.recordedSources||[]).map(s=>s.path.split('.').pop().toLowerCase()))];
  cases.push({id:figure.id,author:figure.author,number:figure.number,sourceVersion,evidenceCurrent,
    features:{method,structure,sourceFormats},review,
    fields:evidenceCurrent?supplied.fields:{},productionDecision:record.productionDecision||null,
    evidenceRefs:[{file:'production-results.json',pointer:'/figures/'+figure.id+'/review',quote:review}],
    reusable:evidenceCurrent&&!!method&&!!structure});
 }
 return {schemaVersion:1,sourceFingerprint:digest({inventory,production}),cases};
}
export function retrieveCases(index,query){
 if(query.sourceMatched!==true||!query.method||!query.structure)return {matches:[],reason:'先明确图源配对、具体加工方式及结构关系，证据不足不套用案例'};
 const matches=index.cases.filter(c=>c.reusable&&c.features.method===query.method&&c.features.structure===query.structure)
  .map(c=>({id:c.id,sourceVersion:c.sourceVersion,score:2+(c.features.sourceFormats.some(x=>(query.sourceFormats||[]).includes(x))?1:0),
    reason:'已验收记录同时支持相同加工方式与结构关系',evidenceRefs:c.evidenceRefs,
    reusableFacts:c.fields,limits:['只复用有记录的局部检查办法，不照搬尺寸、栏宽、节点数量或数据','当前用户明确要求优先；未知历史耗时和工具步骤不补写']}))
  .sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id)).slice(0,3);
 return {matches,reason:matches.length?'找到了可限定参考的已通过案例':'没有足够相似且证据完整的已通过案例；保留现有判断依据，不强套路线'};
}
export function applyCaseEvidence(figure,result){
 const next=structuredClone(figure);
 next.aiProposal.caseRetrieval={query:figure.retrievalQuery,...result};
 const match=result.matches.find(m=>/居中|留边|避让|净距/.test(m.evidenceRefs[0]?.quote||''));
 if(match&&next.aiProposal.fields.preflight){
  next.aiProposal.fields.preflight.basis+=' 已参考相似已通过图件的审校记录：检查框内留边及文字与线的避让；不照搬其栏宽、尺寸或数据。';
 }
 return next;
}
export function writeIndex(file,index){
 if(fs.existsSync(file)){const old=JSON.parse(fs.readFileSync(file,'utf8'));if(old.sourceFingerprint===index.sourceFingerprint&&digest(old.cases)===digest(index.cases))return false;const dir=file+'.history';fs.mkdirSync(dir,{recursive:true});const archived=path.join(dir,digest(old)+'.json');if(!fs.existsSync(archived))fs.writeFileSync(archived,JSON.stringify(old,null,2),{flag:'wx'});}
 const temp=file+'.'+randomUUID()+'.tmp';fs.writeFileSync(temp,JSON.stringify(index,null,2));fs.renameSync(temp,file);return true;
}
