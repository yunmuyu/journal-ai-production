async function setAcceptance(id,accepted,expectedVersion){
 const d=drafts.get(id),cb=document.querySelector('[data-accept="'+id+'"]');
 if(!d||d.accepting)return;
 d.accepting=true;if(cb)cb.disabled=true;
 try{
  if(d.loadingImages)throw Error('截图正在读取，请稍后确认');
  if(d.dirty&&(!await save(id)||d.dirty))throw Error('批注尚未保存，请保存完成后再确认');
  const version=find(id).reviewVersion;
  if(expectedVersion&&version!==expectedVersion)return;
  feedbackStatus(id,accepted?'正在确认…':'正在撤回…');
  const response=await fetch('/accept/'+encodeURIComponent(id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({accepted,version})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'确认失败');
  Object.assign(find(id),result.figure);d.accepted=result.figure.status==='终检通过';d.reviewVersion=result.figure.reviewVersion;
  signature='';await refresh();feedbackStatus(id,accepted?'已确认通过':'已撤回确认');
 }catch(error){feedbackStatus(id,error.message);if(cb)cb.checked=d.accepted;}
 finally{d.accepting=false;const current=document.querySelector('[data-accept="'+id+'"]');if(current){current.disabled=false;current.checked=d.accepted;}}
}
