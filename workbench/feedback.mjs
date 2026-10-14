import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {inspectAcceptance} from '../collaboration/acceptance.mjs';
import {root} from './model.mjs';
import {resolveLocal} from './paths.mjs';
const recordsPath=path.join(root,'production-results.json');
export const attachmentRoot=path.join(root,'反馈附件');
export function persistFeedback(id,input,registeredIds,store={recordsPath,attachmentRoot}){
 const recordsPath=store.recordsPath,attachmentRoot=store.attachmentRoot;
 if(!registeredIds.has(id))throw Object.assign(Error('图件未登记'),{status:404});
 if(typeof input.text!=='string'||input.text.length>20000||typeof input.accepted!=='boolean'||!Number.isInteger(input.revision)||!Array.isArray(input.images)||input.images.length>12)throw Object.assign(Error('反馈格式或图片数量不正确'),{status:400});
 const lock=recordsPath+'.feedback.lock';let handle;
 try{handle=fs.openSync(lock,'wx');}catch{throw Object.assign(Error('生产记录正在保存，请稍后重试'),{status:409});}
 const created=[];let tmp;
 try{
  const before=fs.readFileSync(recordsPath,'utf8'),records=JSON.parse(before),prior=records.figures[id]||{};
  if((prior.userFeedback?.revision||0)!==input.revision)throw Object.assign(Error('这张图的反馈已更新，请刷新后核对再保存'),{status:409});
  const artifact=input.accepted?inspectAcceptance(id,prior,{resolve:resolveLocal}):null;
  if(input.accepted){
   if(!artifact.token)throw Object.assign(Error(artifact.error),{status:400});
   if(input.artifactToken!==artifact.token)throw Object.assign(Error('当前成品与页面审核版本不一致，请刷新并重新查看后验收'),{status:409});
  }
  const priorImages=prior.userFeedback?.attachments||[];
  const attachments=input.images.map(image=>{
   if(image.path){const known=priorImages.find(x=>x.path===image.path);if(!known||!fs.existsSync(resolveLocal(known.path)))throw Object.assign(Error('图片不是本图已保存的附件'),{status:400});return known;}
   if(typeof image.data!=='string'||image.data.length>24*1024*1024)throw Object.assign(Error('图片过大或格式错误'),{status:400});
   const bytes=Buffer.from(image.data,'base64');let ext,mime;
   if(bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))){ext='png';mime='image/png';}
   else if(bytes[0]===255&&bytes[1]===216&&bytes[2]===255){ext='jpg';mime='image/jpeg';}
   else if(bytes.subarray(0,4).toString()==='RIFF'&&bytes.subarray(8,12).toString()==='WEBP'){ext='webp';mime='image/webp';}
   else throw Object.assign(Error('仅支持PNG、JPEG或WebP截图'),{status:400});
   const dir=path.join(attachmentRoot,id);fs.mkdirSync(dir,{recursive:true});const file=path.join(dir,randomUUID()+'.'+ext);fs.writeFileSync(file,bytes,{flag:'wx'});created.push(file);
   return {path:file,mime,name:'问题截图.'+ext};
  });
  const hasIssue=!!input.text.trim()||attachments.length>0;
  const feedback={text:input.text,accepted:input.accepted,attachments,revision:input.revision+1,updatedAt:new Date().toISOString()};
  const status=input.accepted?'用户最终验收通过':hasIssue?'待修订':(prior.userFeedback?.workflowStatus||prior.status||'待制作');
  feedback.workflowStatus=prior.userFeedback?.workflowStatus||prior.status||'待制作';
  const wasAccepted=prior.userAcceptance?.accepted===true||(prior.userAcceptance?.accepted!==false&&/最终验收通过|用户.*通过|终检通过/.test(prior.status||''));
  if(!input.accepted&&wasAccepted)feedback.workflowStatus='待终检';
  records.figures[id]={...prior,status:!input.accepted&&!hasIssue&&wasAccepted?'待终检':status,userFeedback:feedback,userAcceptance:{...prior.userAcceptance,accepted:input.accepted,at:feedback.updatedAt,source:'期刊作图工作台',artifactToken:artifact?.token||null,artifacts:artifact?.outputs||[]}};
  tmp=recordsPath+'.'+randomUUID()+'.tmp';fs.writeFileSync(tmp,JSON.stringify(records,null,2),'utf8');
  if(fs.readFileSync(recordsPath,'utf8')!==before)throw Object.assign(Error('生产记录有并发更新，本次未保存，请重试'),{status:409});
  if(input.accepted&&inspectAcceptance(id,prior,{resolve:resolveLocal}).token!==artifact.token)throw Object.assign(Error('验收期间成品发生变化，本次未保存，请重新核对'),{status:409});
  fs.renameSync(tmp,recordsPath);tmp=null;return feedback;
 }catch(error){for(const file of created)fs.unlinkSync(file);if(tmp&&fs.existsSync(tmp))fs.unlinkSync(tmp);throw error;}
 finally{fs.closeSync(handle);fs.unlinkSync(lock);}
}
