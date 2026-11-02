function revisionControls(f){
 const job=f.revisionJob,active=job&&['queued','running'].includes(job.state),accepted=f.status==='终检通过';
 const labels={queued:'已排队',running:'AI 修订中',ready:'修订待确认',failed:'执行失败',interrupted:'执行中断',needs_input:'需要补充信息'};
 const retry=job&&['failed','interrupted','needs_input'].includes(job.state);
 return `<div class="revision-controls mt-2 mb-2"><button class="btn btn-sm btn-primary" data-revise="${e(f.id)}" data-retry="${retry?'1':'0'}" ${active||accepted?'disabled':''}>${active?e(labels[job.state]):retry?'重新提交修订':'开始修订'}</button><span class="text-secondary ms-2" role="status" data-revision-message="${e(f.id)}">${accepted?'已通过；新增或修改批注后可修订':job?e(labels[job.state]+'：'+job.message):'保存批注后，点击开始修订'}</span></div>`;
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-revise]');if(!button||button.disabled)return;
 const id=button.dataset.revise;button.disabled=true;
 const message=text=>{const node=document.querySelector('[data-revision-message="'+id+'"]');if(node)node.textContent=text;};
 try{
  if(!await save(id)||drafts.get(id)?.dirty)throw Error('批注尚未保存完成，请稍后重试');
  const figure=find(id);
  const response=await fetch('/revision-jobs/'+encodeURIComponent(id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:figure.reviewVersion,retry:button.dataset.retry==='1'})});
  const data=await response.json();if(!response.ok)throw Error(data.error||'提交失败');
  message('已排队，可关闭预览；后台会继续处理');signature='';await refresh();
 }catch(error){message(error.message);button.disabled=false;}
});
