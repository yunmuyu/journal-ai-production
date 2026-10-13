import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {validateSourceInput,saveSourceReview} from './source-review-store.mjs';
import {ATTRIBUTE_OPTIONS,normalizeAttribute} from './decision-attributes.mjs';
import {resolveLocal} from './paths.mjs';

const names=['sourceMatch','method','columns','split','contentTypes','preflight'];
const labels={kind:'基础分类',sourceMatch:'图源匹配',method:'制作方法',columns:'栏宽',split:'拆分规格',contentTypes:'内容类型',preflight:'制作前检查'};
const actions=new Set(['draft','confirm','recheck','defer']);
const attributeActions=new Set(['attribute-draft','attribute-confirm']);
const fail=(status,message,fields)=>{throw Object.assign(Error(message),{status,...(fields?{fields}:{})});};
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const keysFit=(value,allowed)=>object(value)&&Object.keys(value).every(key=>allowed.includes(key));
const textOk=(value,limit=2000)=>typeof value==='string'&&value.length<=limit;
const unresolved=value=>/(?:未知|待判断|待填写|待确认|待验证|待确定|待人工决定|待核对|未核实|证据不足|证据不够)/.test(value);
const snapshot=value=>JSON.parse(JSON.stringify(value));

function loadPilot(pilotPath){
 const pilot=JSON.parse(fs.readFileSync(pilotPath,'utf8'));
 if(pilot.schemaVersion!==1||!Array.isArray(pilot.figures)||!Array.isArray(pilot.cases))fail(500,'试用资料格式错误');
 return pilot;
}

function parseInput(input){
 if(!object(input)||!Number.isSafeInteger(input.revision)||input.revision<0||
   !textOk(input.proposalVersion,200)||!input.proposalVersion)
  fail(400,'制作决策格式不正确');
 if(input.action==='delivery-note'){if(!keysFit(input,['revision','proposalVersion','action','text'])||!textOk(input.text,20000))fail(400,'拆分备注格式不正确');return input;}
 if(['source-save','source-confirm'].includes(input.action))return validateSourceInput(input);
 if(attributeActions.has(input.action)){
  if(!keysFit(input,['revision','proposalVersion','action','attribute','value','operationId'])||
    !Object.hasOwn(ATTRIBUTE_OPTIONS,input.attribute)||
    !ATTRIBUTE_OPTIONS[input.attribute].includes(input.value)||
    (input.operationId!==undefined&&(!textOk(input.operationId,100)||!input.operationId)))
   fail(400,'属性决策格式不正确');
  return input;
 }
 if(!keysFit(input,['revision','proposalVersion','action','fields','resolutions'])||!actions.has(input.action)||
   !keysFit(input.fields,names)||names.some(name=>!textOk(input.fields[name]))||
   !keysFit(input.resolutions||{},names)||Object.values(input.resolutions||{}).some(value=>!textOk(value)))
  fail(400,'制作决策格式不正确');
 return {...input,resolutions:input.resolutions||{}};
}

function saveAttribute(previous,proposal,figure,input){
 if(previous&&(previous.proposalVersion!==proposal.version||
   previous.aiProposal?.sourceFingerprint!==proposal.sourceFingerprint))
  fail(409,'原审核对应旧建议，请刷新后核对');
 const key=input.attribute,originalAIValue=normalizeAttribute(key,key==='kind'?figure.basicClassification?.value??proposal.fields.contentTypes.value:proposal.fields[key].value);
 if(input.action==='attribute-confirm'&&(input.value==='待判断'||
   ((key==='kind'?proposal.fields.contentTypes:proposal.fields[key]).certainty==='unknown'&&input.value===originalAIValue)))
  fail(422,`请先明确${labels[key]}`, [key]);
 const base=previous||{revision:0,proposalVersion:proposal.version,aiProposal:snapshot(proposal),
  fields:Object.fromEntries(names.map(name=>[name,proposal.fields[name].value])),changes:[],resolutions:{},
  state:'draft',userConfirmed:false,semanticReview:'not-required',history:[]};
 const at=new Date().toISOString(),before=previous?.attributes?.[key]?.value??originalAIValue;
 const entry={action:input.action,op:input.operationId?.startsWith('undo:')?input.operationId:input.action,
  operationId:input.operationId??null,before,value:input.value,originalAIValue,at,
  sourceFingerprint:proposal.sourceFingerprint};
 const current=previous?.attributes?.[key];
 const updated={...current,value:input.value,originalAIValue,
  state:input.action==='attribute-confirm'?'confirmed':'draft',history:[...(current?.history||[]),entry]};
 const attributes={...previous?.attributes,[key]:updated};
 if(key==='method'){
  updated.capacityCheck=input.value===before?(current?.capacityCheck||'not-required'):'pending-agent';
  const column=attributes.columns,evidence=figure.capacityEvidence,calc=evidence?.calculation;
  if(input.value!==before&&column&&evidence?.method===input.value&&
    typeof evidence.basis==='string'&&evidence.basis.trim()&&
    Array.isArray(evidence.allowedColumns)&&!evidence.allowedColumns.includes(column.value)&&
    !evidence.userSpecifiedColumns&&calc?.columns===column.value&&
    Number.isFinite(calc.requiredWidthMm)&&Number.isFinite(calc.availableWidthMm)&&
    calc.requiredWidthMm>calc.availableWidthMm){
   updated.capacityCheck='conflict';
   attributes.columns={...column,state:'needs-review',history:[...column.history,
    {action:'capacity-conflict',op:'capacity-conflict',operationId:input.operationId??null,
      before:column.value,value:column.value,originalAIValue:column.originalAIValue,at,
      sourceFingerprint:proposal.sourceFingerprint}]};
  }
 }
 return {...base,revision:input.revision+1,attributes};
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
 if(issues.length){const fields=[...new Set(issues)];fail(422,`请核对后再确认：${fields.map(name=>labels[name]).join('、')}`,fields);}
}

function checkSources(figure,pilotPath){
 if(figure.sourceFiles===undefined)return;
 if(!Array.isArray(figure.sourceFiles))fail(409,'源文件清单不可读取，请刷新后核对');
 for(const source of figure.sourceFiles){
  if(!object(source)||!textOk(source.path,2000)||!source.path||
    typeof source.sha256!=='string'||!/^[a-f\d]{64}$/i.test(source.sha256))
   fail(409,'源文件清单不可读取，请刷新后核对');
  let actual;
  try{actual=createHash('sha256').update(fs.readFileSync(path.resolve(path.dirname(pilotPath),resolveLocal(source.path)))).digest('hex');}
  catch{fail(409,'源文件不可读取，请刷新后核对');}
  if(actual.toLowerCase()!==source.sha256.toLowerCase())fail(409,'源文件已变化，请刷新后核对');
 }
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
    const production=records.figures?.[figure.id]||{};
    const productionComplete=production.userAcceptance?.accepted===true||production.deliveryComplete===true||(production.normalRenderCompleted===true&&production.internalReviewDecision==='pass'&&!!production.outputHash)||(/本图内部复核完成|已制作|制作完成|内部复核通过|最终验收通过/.test(production.stage||production.status||'')&&!!production.output&&!!production.outputHash);
    return {...figure,productionComplete,decision:saved?{...saved,...(stale?{state:'stale',stale:true}:{stale:false})}:null};
   })};
  },
  save(id,rawInput){
   const input=parseInput(rawInput);
   if(typeof id!=='string'||id.length>200)fail(404,'图件未登记');
   const lock=recordsPath+'.feedback.lock';let handle;
   try{handle=fs.openSync(lock,'wx');}catch{fail(409,'生产记录正在保存，请稍后重试');}
   let tmp;const created=[];
   try{
    const pilotBefore=fs.readFileSync(pilotPath,'utf8');
    const pilot=loadPilot(pilotPath);
    const figure=pilot.figures.find(item=>item.id===id);
    if(!figure)fail(404,'图件未登记');
    checkSources(figure,pilotPath);
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
    let previous=prior.productionDecision;
    if((previous?.revision||0)!==input.revision)fail(409,'制作决策已更新，请刷新后核对');
    if(previous&&(previous.proposalVersion!==proposal.version||previous.aiProposal?.sourceFingerprint!==proposal.sourceFingerprint)){const oldProposal=snapshot(previous.aiProposal);previous={...previous,fields:Object.fromEntries(names.map(k=>[k,previous.fields?.[k]!==previous.aiProposal?.fields?.[k]?.value?previous.fields[k]:proposal.fields[k].value])),proposalVersion:proposal.version,aiProposal:snapshot(proposal),proposalHistory:[...(previous.proposalHistory||[]),{aiProposal:oldProposal,at:new Date().toISOString(),reason:'当前来源更新，保留已有人工属性与反馈'}],sourceReview:previous.sourceReview?{...previous.sourceReview,state:'draft'}:undefined};}

    let decision;
    if(input.action==='delivery-note'){const base=previous||{revision:0,proposalVersion:proposal.version,aiProposal:snapshot(proposal),fields:Object.fromEntries(names.map(name=>[name,proposal.fields[name].value])),changes:[],resolutions:{},state:'draft',userConfirmed:false,semanticReview:'not-required',history:[]};const at=new Date().toISOString();decision={...base,revision:input.revision+1,deliveryReview:{...previous?.deliveryReview,text:input.text,updatedAt:at,history:[...(previous?.deliveryReview?.history||[]),{action:'delivery-note',text:input.text,at,proposalVersion:proposal.version,sourceFingerprint:proposal.sourceFingerprint}]}};}
    else if(['source-save','source-confirm'].includes(input.action))decision=saveSourceReview({previous,proposal,figure,pilot,input,recordsPath,created});
    else if(attributeActions.has(input.action))decision=saveAttribute(previous,proposal,figure,input);
    else{
    const changes=names.filter(name=>input.fields[name]!==proposal.fields[name].value)
      .map(field=>({field,from:proposal.fields[field].value,to:input.fields[field]}));
    if(input.action==='confirm'){if(previous?.sourceReview?.state==='needs-review')fail(422,'图源仍有未解决问题，请先完成图源核查',['sourceMatch']);checkConfirm(proposal,input,changes);}
    const userConfirmed=input.action==='confirm';
    const requiresReview=changes.length>0||names.some(name=>proposal.fields[name].certainty==='unknown');
    const state=input.action==='confirm'?(requiresReview?'needs-review':'confirmed'):
      input.action==='recheck'?'needs-review':input.action==='defer'?'deferred':'draft';
    const semanticReview=input.action==='recheck'||requiresReview?'pending':'not-required';
    const at=new Date().toISOString();
    const aiProposal=snapshot(proposal);
    decision={revision:input.revision+1,proposalVersion:proposal.version,aiProposal,
      fields:{...input.fields},changes,resolutions:{...input.resolutions},state,userConfirmed,semanticReview,
      history:[...(previous?.history||[]),{action:input.action,at,aiProposal:snapshot(proposal),changes:snapshot(changes),
        finalFields:{...input.fields},sourceFingerprint:proposal.sourceFingerprint}],
      ...(previous?.attributes?{attributes:previous.attributes}:{}),
      ...(previous?.sourceReview?{sourceReview:previous.sourceReview}:{}),
      ...(previous?.deliveryReview?{deliveryReview:previous.deliveryReview}:{}),
      ...(previous?.proposalHistory?{proposalHistory:previous.proposalHistory}:{})};
    }
    records.figures[id]={...prior,productionDecision:decision};
    tmp=recordsPath+'.'+randomUUID()+'.tmp';
    fs.writeFileSync(tmp,JSON.stringify(records,null,2),'utf8');
    if(fs.readFileSync(recordsPath,'utf8')!==before||fs.readFileSync(pilotPath,'utf8')!==pilotBefore)
      fail(409,'资料有并发更新，本次未保存，请重试');
    fs.renameSync(tmp,recordsPath);tmp=null;
    return decision;
   }catch(error){for(const file of created)if(fs.existsSync(file))fs.unlinkSync(file);throw error;}finally{
    if(tmp&&fs.existsSync(tmp))fs.unlinkSync(tmp);
    fs.closeSync(handle);fs.unlinkSync(lock);
   }
  }
 };
}
