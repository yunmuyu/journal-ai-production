(() => {
 const open=document.getElementById('archive-intake-open');if(!open)return;
 const dialog=document.createElement('dialog');dialog.className='archive-intake-dialog';
 dialog.setAttribute('aria-labelledby','archive-intake-title');
 dialog.innerHTML=`<form id="archive-intake-form"><h2 id="archive-intake-title" class="card-title">上传作图包</h2><p class="text-secondary">保留原包，登记文章并显示到工作台。已有批注和制作进度保留。</p><label class="form-label" for="archive-file">原始压缩包</label><input class="form-control mb-3" id="archive-file" type="file" accept=".zip,.rar" required><div class="archive-intake-fields"><label class="form-label">月份<input class="form-control" name="month" type="number" min="1" max="12" required></label><label class="form-label">编辑<input class="form-control" name="editor" list="archive-editors" required><datalist id="archive-editors"><option>李秀梅</option><option>訾磊</option><option>李颖</option><option>王玉</option><option>靳宣</option></datalist></label><label class="form-label">文章篇数<input class="form-control" name="count" type="number" min="1" max="999" required></label></div><p class="text-secondary">登记不代表已开始作图或验收通过。单个包完整即可继续处理。</p><progress hidden style="width:100%" aria-label="上传进度" max="100"></progress><p role="status" aria-live="polite"></p><div class="d-flex gap-2 justify-content-end"><button type="button" class="btn" data-close>关闭</button><button class="btn btn-primary" type="submit">上传并登记</button></div></form>`;
 document.body.append(dialog);const form=dialog.querySelector('form'),file=dialog.querySelector('[type=file]'),status=dialog.querySelector('[role=status]'),progress=dialog.querySelector('progress');let busy=false;
 open.onclick=()=>dialog.showModal();dialog.querySelector('[data-close]').onclick=()=>dialog.close();dialog.addEventListener('cancel',ev=>{if(busy)ev.preventDefault();});
 file.onchange=()=>{const name=file.files[0]?.name||'',month=name.match(/(\d{1,2})月/),count=name.match(/(\d+)篇/),editor=name.match(/(?:李秀梅|訾磊|李颖|王玉|靳宣)/);if(month)form.elements.month.value=month[1];if(count)form.elements.count.value=count[1];if(editor)form.elements.editor.value=editor[0];status.textContent='';};
 form.onsubmit=event=>{
  event.preventDefault();if(busy||!file.files[0])return;
  const selected=file.files[0],query=new URLSearchParams({filename:selected.name,month:form.elements.month.value,editor:form.elements.editor.value.trim(),count:form.elements.count.value});
  busy=true;form.querySelectorAll('input,button').forEach(n=>n.disabled=true);progress.hidden=false;progress.value=0;status.textContent='正在上传…';
  const xhr=new XMLHttpRequest();xhr.open('POST','/archive-intake?'+query);xhr.timeout=300000;
  xhr.upload.onprogress=ev=>{if(ev.lengthComputable){progress.value=100*ev.loaded/ev.total;if(ev.loaded===ev.total)status.textContent='上传完成，正在核对原包、建立目录和登记文章…';}};
  xhr.onload=async()=>{try{const result=JSON.parse(xhr.responseText);if(xhr.status!==200)throw Error(result.error||'登记失败');status.textContent=`${result.batch.duplicate?'此包已登记，已保留原记录':'登记完成'}：${result.batch.editor}，${result.batch.articles}篇、${result.batch.authors}位作者。`;if(typeof refresh==='function'){signature='';await refresh();}}catch(error){status.textContent='未完成登记：'+error.message;}};
  xhr.onerror=()=>status.textContent='连接中断，请重试；相同原包不会重复登记。';xhr.ontimeout=()=>status.textContent='请求超时，请重试核对登记结果。';
  xhr.onloadend=()=>{busy=false;form.querySelectorAll('input,button').forEach(n=>n.disabled=false);progress.hidden=true;};xhr.send(selected);
 };
})();
