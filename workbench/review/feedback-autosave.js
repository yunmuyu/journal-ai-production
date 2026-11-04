// Local recovery is written synchronously before the debounced server save.
const feedbackTimers=new Map(),feedbackKey=id=>'november-2026-feedback:'+id;
function feedbackStatus(id,message){
 const node=document.querySelector('[data-save-status="'+id+'"]');
 if(node)node.textContent=message;
 if(typeof viewerFeedbackStatus==='function')viewerFeedbackStatus(id,message);
}
function rememberFeedback(id,d){
 try{
  localStorage.setItem(feedbackKey(id),JSON.stringify({text:d.text,images:d.images,points:d.points||[],revision:d.revision}));
  d.recoveryFailed=false;
 }catch{d.recoveryFailed=true;}
}
function draft(f){
 if(!drafts.has(f.id)){
  const d={text:f.feedback?.text||'',accepted:f.status==='终检通过',points:(f.feedback?.points||[]).map(p=>({...p})),reviewVersion:f.reviewVersion,images:(f.feedback?.attachments||[]).map(a=>({...a,src:a.data||(a.file?'/file/'+a.file.token:'')})),revision:f.feedback?.revision||0,dirty:false};
  try{
   const cached=JSON.parse(localStorage.getItem(feedbackKey(f.id))||'null');
   if(cached){
    const same=cached.text===d.text&&JSON.stringify(cached.points||[])===JSON.stringify(d.points)&&JSON.stringify(cached.images.map(im=>im.src))===JSON.stringify(d.images.map(im=>im.src));
    if(same)localStorage.removeItem(feedbackKey(f.id));
    else{
     Object.assign(d,cached,{dirty:true});
     if(cached.revision!==(f.feedback?.revision||0))d.error='有未同步批注且版本冲突，内容已保留，请核对后再保存';
     else feedbackTimers.set(f.id,setTimeout(()=>save(f.id),400));
    }
   }
  }catch{d.error='本机恢复记录读取失败，请勿刷新';}
  drafts.set(f.id,d);
 }
 return drafts.get(f.id);
}
function dirty(id){
 const d=drafts.get(id);d.dirty=true;d.editVersion=(d.editVersion||0)+1;
 if(typeof syncPointSummary==='function')syncPointSummary(id);
 rememberFeedback(id,d);
 feedbackStatus(id,d.recoveryFailed?'自动保存中；本机缓存已满，完成前请勿刷新':'自动保存中…');
 clearTimeout(feedbackTimers.get(id));
 feedbackTimers.set(id,setTimeout(()=>save(id),400));
}
async function save(id){
 const d=drafts.get(id);if(!d||!d.dirty)return true;
 if(d.saving)return d.savePromise;
 if(d.loadingImages){clearTimeout(feedbackTimers.get(id));feedbackTimers.set(id,setTimeout(()=>save(id),200));return false;}
 const version=d.editVersion||0;
 const body={text:d.text,revision:d.revision,points:d.points||[],images:d.images.map(im=>({data:im.src}))};
 d.saving=true;feedbackStatus(id,'自动保存中…');
 d.savePromise=(async()=>{
  try{
   const response=await fetch('/feedback/'+encodeURIComponent(id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   const result=await response.json();if(!response.ok)throw Error(result.error||'保存失败');
   d.revision=result.figure.feedback.revision;d.reviewVersion=result.figure.reviewVersion;d.accepted=result.figure.status==='终检通过';Object.assign(find(id),result.figure);
   d.error='';
   if((d.editVersion||0)===version){d.dirty=false;localStorage.removeItem(feedbackKey(id));feedbackStatus(id,'已自动保存');}
   else rememberFeedback(id,d);
   const badge=document.querySelector('[data-figure="'+id+'"] .review-status');
   if(badge){badge.dataset.status=result.figure.status;badge.textContent=result.figure.status==='异常'?'待修订':badge.textContent;}
   const cb=document.querySelector('[data-accept="'+id+'"]');if(cb)cb.checked=result.figure.status==='终检通过';
   signature='';await refresh();
   const completed=articles.filter(a=>a.state==='全部通过').length,total=articles.length;
   const percent=total?Math.round(completed/total*100):0;
   if($('counts'))$('counts').innerHTML='<span class="progress-ring" style="--progress:'+percent+'%" aria-hidden="true"></span><span>已通过 <strong>'+completed+'/'+total+'</strong> 篇 · '+percent+'%</span>';
   for(const article of articles){
    const tile=document.querySelector('.author-tile[data-author="'+article.id+'"]');
    if(tile){tile.dataset.state=article.state;tile.title=article.label+' · '+article.state;tile.setAttribute('aria-label',article.label+'，'+article.state);}
   }
   return true;
  }catch(error){d.error='自动保存失败：'+error.message+'（批注保留，请重试）';feedbackStatus(id,d.error);return false;}
  finally{
   d.saving=false;
   if(typeof thumbs==='function')thumbs(id);
   if(!d.dirty&&!d.error)feedbackStatus(id,'已自动保存');
   if(d.dirty&&!d.error){clearTimeout(feedbackTimers.get(id));feedbackTimers.set(id,setTimeout(()=>save(id),0));}
  }
 })();return d.savePromise;
}
window.addEventListener('beforeunload',event=>{
 if([...drafts.values()].some(d=>d.loadingImages||(d.dirty&&d.recoveryFailed))){event.preventDefault();event.returnValue='';}
});
