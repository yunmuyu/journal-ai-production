import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {resolveLocal} from './paths.mjs';
const fail=(message,status=400)=>{throw Object.assign(Error(message),{status});};
export function validateSourceInput(input){
 const allowed=input.action==='source-confirm'?['action','revision','proposalVersion']:['action','revision','proposalVersion','text','choice','images','subfigures'];
 if(Object.keys(input).some(k=>!allowed.includes(k)))fail('图源反馈字段不正确');
 if(input.action==='source-confirm')return input;
 if(input.subfigures!==undefined&&(typeof input.subfigures!=='string'||input.subfigures.length>2000))fail('子图题说明过长或格式错误');
 if(typeof input.text!=='string'||input.text.length>20000||!['','word','attachment','replace'].includes(input.choice)||!Array.isArray(input.images)||input.images.length>12)fail('图源反馈或截图数量不正确');
 return input;
}
export function saveSourceReview({previous,proposal,figure,pilot,input,recordsPath,created}){
 if(previous&&(previous.proposalVersion!==proposal.version||previous.aiProposal.sourceFingerprint!==proposal.sourceFingerprint))fail('原审核对应旧建议，请刷新核对',409);
 const old=previous?.sourceReview;
 const base=previous||{revision:0,proposalVersion:proposal.version,aiProposal:structuredClone(proposal),fields:Object.fromEntries(Object.entries(proposal.fields).map(([k,v])=>[k,v.value])),changes:[],resolutions:{},state:'draft',userConfirmed:false,semanticReview:'not-required',history:[]};
 let review;
 if(input.action==='source-confirm'){
  const hasAsset=id=>!!pilot.assets?.[id]?.path&&fs.existsSync(resolveLocal(pilot.assets[id].path));
  if(proposal.fields.sourceMatch.certainty!=='verified'||!hasAsset(figure.sourceViews?.[0]?.cropAsset)||!figure.attachments?.some(a=>a.role!=='局部素材'&&hasAsset(a.asset)))fail('完整对照证据不足，图源不能确认',422);
  if(old?.text?.trim()||old?.attachments?.length||old?.choice||previous?.resolutions?.sourceMatch)fail('本图仍有图源问题，暂不批量通过',422);
  review={...old,subfigures:old?.subfigures??figure.subfigureAssessment?.summary??'',text:old?.text||'',choice:old?.choice||'',attachments:old?.attachments||[],state:'confirmed'};
 }else{
  if(!/^[A-Za-z0-9_-]+$/.test(figure.id))fail('图件ID不能用于附件目录');
  const attachments=input.images.map(image=>{
   if(!image||typeof image!=='object'||Array.isArray(image)||Object.keys(image).some(k=>!['path','data'].includes(k))||(image.path&&image.data))fail('截图引用格式不正确');
   if(image.path){const known=old?.attachments?.find(a=>a.path===image.path);if(!known||!fs.existsSync(resolveLocal(known.path)))fail('图片不是本图已保存的图源附件');return known;}
   if(typeof image.data!=='string'||image.data.length>12*1024*1024)fail('单张截图过大或格式错误');
   const bytes=Buffer.from(image.data,'base64');let ext,mime;
   if(bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))){ext='png';mime='image/png';}
   else if(bytes[0]===255&&bytes[1]===216&&bytes[2]===255){ext='jpg';mime='image/jpeg';}
   else if(bytes.subarray(0,4).toString()==='RIFF'&&bytes.subarray(8,12).toString()==='WEBP'){ext='webp';mime='image/webp';}
   else fail('只支持PNG、JPEG或WebP截图');
   const dir=path.join(path.dirname(recordsPath),'反馈附件','图源匹配',figure.id);fs.mkdirSync(dir,{recursive:true});const file=path.join(dir,randomUUID()+'.'+ext);fs.writeFileSync(file,bytes,{flag:'wx'});created.push(file);return {path:file,mime,name:'图源问题截图.'+ext};
  });
  review={text:input.text,subfigures:input.subfigures||'',choice:input.choice,attachments,state:input.text.trim()||attachments.length||input.choice?'needs-review':'draft'};
 }
 const at=new Date().toISOString();review.originalAISuggestion=old?.originalAISuggestion||structuredClone(proposal.fields.sourceMatch);review.updatedAt=at;review.history=[...(old?.history||[]),{action:input.action,at,text:review.text,subfigures:review.subfigures||'',choice:review.choice,attachments:structuredClone(review.attachments),state:review.state,sourceFingerprint:proposal.sourceFingerprint}];
 return {...base,revision:input.revision+1,sourceReview:review};
}
