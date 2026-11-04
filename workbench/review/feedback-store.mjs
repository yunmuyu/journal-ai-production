import fs from 'node:fs';
export function createFeedbackStore(file){
 const records=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{};
 return {
  get(id){return records[id]||null;},
  save(id,body){
   if(!body||typeof body.text!=='string'||body.text.length>100000||!Array.isArray(body.images)||body.images.length>30)throw Error('批注内容或图片数量不正确');
   if(body.revision!==(records[id]?.revision||0))throw Error('批注已在其他页面更新，请刷新后重试');
   const attachments=body.images.map(im=>{
    if(typeof im.data!=='string'||!/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+=*$/.test(im.data))throw Error('截图格式不支持，请重新粘贴');
    return {data:im.data};
   });
   const previous=records[id];
   const points=body.points??previous?.points??[];
   if(!Array.isArray(points)||points.length>200)throw Error('位置批注数量不正确');
   const ids=new Set();
   for(const p of points){
    if(!p||typeof p.id!=='string'||p.id.length>80||ids.has(p.id)||typeof p.text!=='string'||p.text.length>10000||typeof p.output!=='string'||p.output.length>40||!/^\w{24}$/.test(p.token)||!/^\w{64}$/.test(p.sha256)||!Number.isFinite(p.x)||!Number.isFinite(p.y)||p.x<0||p.x>1||p.y<0||p.y>1)throw Error('位置批注格式不正确');
    ids.add(p.id);
   }
   const needsRevision=!!(previous?.needsRevision||previous?.text?.trim()||previous?.attachments?.length||body.text.trim()||attachments.length||points.length);
   const next={text:body.text,attachments,points,needsRevision,revision:(previous?.revision||0)+1};
   fs.writeFileSync(file+'.tmp',JSON.stringify({...records,[id]:next},null,2));
   fs.renameSync(file+'.tmp',file); records[id]=next;
   return next;
  }
 };
}
