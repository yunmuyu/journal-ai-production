import fs from 'node:fs';
import {randomUUID} from 'node:crypto';

const names=['sourceMatch','method','columns','split','contentTypes','preflight'];
const actions=new Set(['draft','confirm','recheck','defer']);
const fail=(status,message,fields)=>{throw Object.assign(Error(message),{status,...(fields?{fields}:{})});};
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const keysFit=(value,allowed)=>object(value)&&Object.keys(value).every(key=>allowed.includes(key));
const textOk=(value,limit=2000)=>typeof value==='string'&&value.length<=limit;
const unresolved=value=>/(?:未知|待确认|待验证|待确定|证据不足)/.test(value);
const snapshot=value=>JSON.parse(JSON.stringify(value));

function loadPilot(pilotPath){
 const pilot=JSON.parse(fs.readFileSync(pilotPath,'utf8'));
 if(pilot.schemaVersion!==1||!Array.isArray(pilot.figures)||!Array.isArray(pilot.cases))fail(500,'试用资料格式错误');
 return pilot;
}

function parseInput(input){
 if(!keysFit(input,['revision','proposalVersion','action','fields','resolutions'])||
   !Number.isSafeInteger(input.revision)||input.revision<0||
   !textOk(input.proposalVersion,200)||!input.proposalVersion||!actions.has(input.action)||
   !keysFit(input.fields,names)||names.some(name=>!textOk(input.fields[name]))||
   !keysFit(input.resolutions||{},names)||Object.values(input.resolutions||{}).some(value=>!textOk(value)))
  fail(400,'制作决策格式不正确');
 return {...input,resolutions:input.resolutions||{}};
}

function checkConfirm(proposal,input,changes){
 const issues=[];
 for(const name of names){
  const value=input.fields[name].trim();
  const original=proposal.fields[name];
  if(!value||unresolved(value))issues.push(name);
  else if(original.certainty==='unknown'&&!changes.some(change=>change.field===name)&&!input.resolutions[name]?.trim())issues.push(name);
 }
 if(/(?:错误|不匹配|不是|找不到图源)/.test(input.fields.sourceMatch))issues.push('sourceMatch');
 const split=input.fields.split;
 if(/(?:拆分|分成|分为).{0,12}(?:[2-9]|两|三|四|五|六|七|八|九)(?:张|幅|个|栏)/.test(split)&&!/(?:\d+(?:\.\d+)?\s*(?:mm|cm|毫米|厘米))/i.test(split))issues.push('split');
 if(issues.length)fail(422,`请核对后再确认：${[...new Set(issues)].join('、')}`,[...new Set(issues)]);
}

export function createDecisionStore({recordsPath,pilotPath}){
 return {
  read(){
   const pilot=loadPilot(pilotPath);
   const records=JSON.parse(fs.readFileSync(recordsPath,'utf8'));
   return {...pilot,figures:pilot.figures.map(figure=>{
    const saved=records.figures?.[figure.id]?.productionDecision;
    const stale=!!saved&&(saved.proposalVersion!==figure.aiProposal?.version||
      saved.aiProposal?.sourceFingerprint!==figure.aiProposal?.sourceFingerprint);
    return {...figure,decision:saved?{...saved,...(stale?{state:'stale',stale:true}:{stale:false})}:null};
   })};
  },
  save(id,rawInput){
   const input=parseInput(rawInput);
   if(typeof id!=='string'||id.length>200)fail(404,'图件未登记');
   const lock=recordsPath+'.feedback.lock';let handle;
   try{handle=fs.openSync(lock,'wx');}catch{fail(409,'生产记录正在保存，请稍后重试');}
   let tmp;
   try{
    const pilotBefore=fs.readFileSync(pilotPath,'utf8');
    const pilot=loadPilot(pilotPath);
    const figure=pilot.figures.find(item=>item.id===id);
    if(!figure)fail(404,'图件未登记');
    const proposal=figure.aiProposal;
    if(!proposal||!textOk(proposal.version,200)||!proposal.version||!textOk(proposal.sourceFingerprint,500)||
      !object(proposal.fields)||names.some(name=>!object(proposal.fields[name])||!textOk(proposal.fields[name].value)||
        !['verified','inferred','unknown'].includes(proposal.fields[name].certainty)||!textOk(proposal.fields[name].basis)))
      fail(500,'图件建议格式错误');
    if(input.proposalVersion!==proposal.version)fail(409,'AI建议已更新，请刷新后核对');
    const before=fs.readFileSync(recordsPath,'utf8');
    const records=JSON.parse(before);
    if(!object(records.figures))fail(500,'生产记录格式错误');
    const prior=records.figures[id]||{};
    const previous=prior.productionDecision;
    if((previous?.revision||0)!==input.revision)fail(409,'制作决策已更新，请刷新后核对');
    const changes=names.filter(name=>input.fields[name]!==proposal.fields[name].value)
      .map(field=>({field,from:proposal.fields[field].value,to:input.fields[field]}));
    if(input.action==='confirm')checkConfirm(proposal,input,changes);
    const userConfirmed=input.action==='confirm';
    const requiresReview=changes.length>0||names.some(name=>proposal.fields[name].certainty==='unknown');
    const state=input.action==='confirm'?(requiresReview?'needs-review':'confirmed'):
      input.action==='recheck'?'needs-review':input.action==='defer'?'deferred':'draft';
    const semanticReview=requiresReview?'pending':'not-required';
    const at=new Date().toISOString();
    const aiProposal=snapshot(proposal);
    const decision={revision:input.revision+1,proposalVersion:proposal.version,aiProposal,
      fields:{...input.fields},changes,resolutions:{...input.resolutions},state,userConfirmed,semanticReview,
      history:[...(previous?.history||[]),{action:input.action,at,aiProposal:snapshot(proposal),changes:snapshot(changes),
        finalFields:{...input.fields},sourceFingerprint:proposal.sourceFingerprint}]};
    records.figures[id]={...prior,productionDecision:decision};
    tmp=recordsPath+'.'+randomUUID()+'.tmp';
    fs.writeFileSync(tmp,JSON.stringify(records,null,2),'utf8');
    if(fs.readFileSync(recordsPath,'utf8')!==before||fs.readFileSync(pilotPath,'utf8')!==pilotBefore)
      fail(409,'资料有并发更新，本次未保存，请重试');
    fs.renameSync(tmp,recordsPath);tmp=null;
    return decision;
   }finally{
    if(tmp&&fs.existsSync(tmp))fs.unlinkSync(tmp);
    fs.closeSync(handle);fs.unlinkSync(lock);
   }
  }
 };
}
