function pointSummary(f,d){
 return (d.points||[]).map((p,i)=>{
  const output=f.outputs.find(o=>o.file?.token===p.token&&o.file?.meta?.sha256===p.sha256);
  return '<section class="card-point-note"><strong>位置批注 '+(i+1)+' · 图'+e(p.output)+'</strong>'+(output?' <button class="btn btn-sm btn-outline-secondary" data-open-viewer="'+e(p.token)+'">查看位置</button>':' <span class="text-secondary">旧版本</span>')+'<p>'+e(p.text||'（尚未填写内容）')+'</p></section>';
 }).join('');
}
function syncPointSummary(id){
 const container=document.querySelector('[data-point-summary="'+id+'"]'),f=find(id),d=drafts.get(id);
 if(container&&f&&d)container.innerHTML=pointSummary(f,d);
}
