import fs from 'node:fs';
import {createHash} from 'node:crypto';
export function reviewVersion(figure){
 const outputs=figure.outputs.map(o=>[o.number,o.file?.path,o.file&&fs.existsSync(o.file.path)?createHash('sha256').update(fs.readFileSync(o.file.path)).digest('hex'):null]);
 return createHash('sha256').update(JSON.stringify([outputs,figure.feedback?.revision||0])).digest('hex');
}
export function reviewState(figure,revision,record){
 if(figure.previewCurrent===false)return '待终检';
 if(record?.version===figure.reviewVersion)return record.accepted?'终检通过':'待终检';
 const f=figure.feedback;
 if(f&&(f.needsRevision||f.text?.trim()||f.attachments?.length||f.points?.length))return revision?.addressedFeedbackRevision>=f.revision?'待终检':'异常';
 return revision||record?'待终检':'终检通过';
}
export function createReviewStore(file){
 const records=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{};
 return {get:id=>records[id],save(id,body,version){
  if(typeof body?.accepted!=='boolean'||body.version!==version)throw Error('图稿或批注已更新，请刷新后重新核对');
  const next={accepted:body.accepted,version,updatedAt:new Date().toISOString()};
  fs.writeFileSync(file+'.tmp',JSON.stringify({...records,[id]:next},null,2));
  fs.renameSync(file+'.tmp',file);records[id]=next;return next;
 }};
}
