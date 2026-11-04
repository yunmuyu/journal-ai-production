// Coordinates are fractions of the exact preview image, never of its letterbox.
const figureViewer=document.createElement('dialog');figureViewer.id='figure-viewer';
figureViewer.setAttribute('aria-labelledby','viewer-title');
figureViewer.innerHTML=`<header class="viewer-toolbar"><h2 class="viewer-heading" id="viewer-title"></h2><button class="btn btn-sm btn-outline-secondary" data-v="prev" aria-label="上一张图">← 上一张</button><button class="btn btn-sm btn-outline-secondary" data-v="next" aria-label="下一张图">下一张 →</button><button class="btn btn-sm btn-outline-secondary" data-v="out" aria-label="缩小预览">−</button><button class="btn btn-sm btn-outline-secondary" data-v="in" aria-label="放大预览">＋</button><button class="btn btn-sm btn-outline-secondary" data-v="fit">适合窗口</button><button class="btn btn-sm btn-outline-secondary" data-v="notes">批注</button><button class="btn btn-sm btn-primary" data-v="close">退出预览</button></header><div class="viewer-body"><div class="viewer-stage" tabindex="0" aria-label="图稿画布：滚轮缩放，拖动查看，右键添加批注"><img class="viewer-image" draggable="false"><div class="viewer-pins"></div><p class="viewer-error" hidden></p></div><aside class="viewer-notes" hidden><h3>位置批注</h3><div class="viewer-note-list"></div><button class="btn btn-sm btn-outline-secondary" data-v="retry">重试保存</button></aside></div><footer class="viewer-footer"><span>滚轮缩放 · 拖动查看 · ← → 换图 · 右键添加批注 · 双击 / Esc 退出</span><span role="status" aria-live="polite" id="viewer-save-status"></span></footer>`;
document.body.append(figureViewer);
figureViewer.querySelector('.viewer-footer > span').id='viewer-metadata';
figureViewer.querySelector('#viewer-metadata').textContent='';
const viewerStage=figureViewer.querySelector('.viewer-stage'),viewerImage=figureViewer.querySelector('.viewer-image'),viewerNotes=figureViewer.querySelector('.viewer-notes');
let viewerItems=[],viewerIndex=0,viewerOrigin=null,viewerTransform={x:0,y:0,scale:1},viewerDrag=null,viewerReady=false,viewerReviewVersion=null;
function viewerItem(){return viewerItems[viewerIndex];}
function viewerDraft(){return draft(find(viewerItem().figureId));}
function viewerFeedbackStatus(id,message){if(figureViewer.open&&viewerItem()?.figureId===id)figureViewer.querySelector('#viewer-save-status').textContent=message;}
function viewerApply(){
 const {x,y,scale}=viewerTransform,w=viewerImage.naturalWidth*scale,h=viewerImage.naturalHeight*scale;
 Object.assign(viewerImage.style,{left:x+'px',top:y+'px',width:w+'px',height:h+'px'});
 for(const pin of figureViewer.querySelectorAll('.viewer-pin')){pin.style.left=(x+Number(pin.dataset.x)*w)+'px';pin.style.top=(y+Number(pin.dataset.y)*h)+'px';}
}
function viewerFit(){
 if(!viewerReady)return;
 const scale=Math.min((viewerStage.clientWidth-48)/viewerImage.naturalWidth,(viewerStage.clientHeight-48)/viewerImage.naturalHeight);
 viewerTransform={scale:Math.max(.01,scale),x:(viewerStage.clientWidth-viewerImage.naturalWidth*scale)/2,y:(viewerStage.clientHeight-viewerImage.naturalHeight*scale)/2};viewerApply();
}
function viewerZoom(factor,x=viewerStage.clientWidth/2,y=viewerStage.clientHeight/2){
 if(!viewerReady)return;const t=viewerTransform,s=Math.min(12,Math.max(.02,t.scale*factor)),ratio=s/t.scale;
 viewerTransform={scale:s,x:x-(x-t.x)*ratio,y:y-(y-t.y)*ratio};viewerApply();
}
function viewerRenderNotes(focusId){
 const item=viewerItem(),points=viewerDraft().points||[];
 figureViewer.querySelector('.viewer-pins').innerHTML=points.map((p,i)=>p.token===item.file.token&&p.sha256===item.file.meta?.sha256?`<button class="viewer-pin" data-pin="${e(p.id)}" data-x="${p.x}" data-y="${p.y}" aria-label="编辑位置批注${i+1}">${i+1}</button>`:'').join('');
 figureViewer.querySelector('.viewer-note-list').innerHTML=points.map((p,i)=>`<section class="viewer-note"><div class="viewer-note-label"><strong>批注 ${i+1} · 图${e(p.output)}</strong><button class="btn btn-sm btn-outline-secondary" data-delete-point="${e(p.id)}">删除</button></div>${p.sha256!==item.file.meta?.sha256||p.token!==item.file.token?'<small>其他分图或旧版本的位置批注</small>':''}<textarea class="form-control" data-point-text="${e(p.id)}" aria-label="位置批注${i+1}" placeholder="描述这个位置需要修改的内容">${e(p.text)}</textarea></section>`).join('')||'<p class="text-secondary">在图片上右键点击需要修改的位置，即可添加批注。</p>';
 viewerApply();if(focusId)figureViewer.querySelector('[data-point-text="'+focusId+'"]')?.focus();
}
function viewerLoad(){
 const item=viewerItem();viewerReady=false;viewerImage.hidden=true;viewerDrag=null;
 viewerReviewVersion=find(item.figureId).reviewVersion;
 figureViewer.querySelector('#viewer-metadata').innerHTML=figureDetails(item);
 figureViewer.querySelector('#viewer-title').textContent=item.author+' · 图'+item.number+'　'+(viewerIndex+1)+' / '+viewerItems.length;
 figureViewer.querySelector('[data-v=prev]').disabled=viewerIndex===0;
 figureViewer.querySelector('[data-v=next]').disabled=viewerIndex===viewerItems.length-1;
 figureViewer.querySelector('.viewer-error').hidden=true;
 viewerNotes.hidden=!(viewerDraft().points||[]).length;
 viewerFeedbackStatus(item.figureId,viewerDraft().error||(viewerDraft().dirty?'自动保存中…':''));
 viewerRenderNotes();viewerImage.alt=item.author+' 图'+item.number;
 viewerImage.src='/preview/'+item.file.token;
}
viewerImage.addEventListener('load',()=>{viewerReady=true;viewerImage.hidden=false;viewerFit();});
viewerImage.addEventListener('error',()=>{const error=figureViewer.querySelector('.viewer-error');error.hidden=false;error.textContent='预览加载失败或图稿已更新，请退出后刷新。';});
function openFigureViewer(token,origin){
 const article=articles.find(a=>a.figures.some(f=>f.outputs.some(o=>o.file?.token===token)));if(!article)return;
 viewerItems=article.figures.flatMap(f=>f.outputs.filter(o=>o.file).map(o=>({...o,author:article.label,figureId:f.id})));
 viewerIndex=viewerItems.findIndex(o=>o.file.token===token);viewerOrigin=origin;
 figureViewer.showModal();viewerLoad();viewerStage.focus();
}
function closeFigureViewer(){
 viewerCompleteReview(viewerItem(),viewerReady,viewerReviewVersion);
 const id=viewerItem()?.figureId;if(id&&viewerDraft().dirty)save(id);
 figureViewer.close();if(viewerOrigin?.isConnected)viewerOrigin.focus();else document.querySelector('[data-viewer-token="'+viewerItem()?.file.token+'"]')?.focus();
}
function viewerMove(delta){
 const next=viewerIndex+delta;if(next<0||next>=viewerItems.length)return;
 viewerCompleteReview(viewerItem(),viewerReady,viewerReviewVersion);
 if(viewerDraft().dirty)save(viewerItem().figureId);viewerIndex=next;viewerLoad();viewerStage.focus();
}
document.addEventListener('dblclick',event=>{const node=event.target.closest('[data-viewer-token]');if(node)openFigureViewer(node.dataset.viewerToken,node);});
document.addEventListener('click',event=>{const node=event.target.closest('[data-open-viewer]');if(node)openFigureViewer(node.dataset.openViewer,node);});
document.addEventListener('keydown',event=>{const node=event.target.closest('[data-viewer-token]');if(node&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openFigureViewer(node.dataset.viewerToken,node);}});
figureViewer.addEventListener('cancel',event=>{event.preventDefault();closeFigureViewer();});
window.addEventListener('keydown',event=>{
 if(!figureViewer.open)return;
 if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();closeFigureViewer();return;}
 if(event.target.matches('textarea,input,select')||event.isComposing)return;
 if(['ArrowLeft','ArrowRight','+','-','0'].includes(event.key)){event.preventDefault();event.stopImmediatePropagation();if(event.key==='ArrowLeft')viewerMove(-1);if(event.key==='ArrowRight')viewerMove(1);if(event.key==='+')viewerZoom(1.2);if(event.key==='-')viewerZoom(1/1.2);if(event.key==='0')viewerFit();}
},true);
figureViewer.addEventListener('click',event=>{
 const action=event.target.closest('[data-v]')?.dataset.v;
 if(action==='close')closeFigureViewer();if(action==='prev')viewerMove(-1);if(action==='next')viewerMove(1);
 if(action==='in')viewerZoom(1.2);if(action==='out')viewerZoom(1/1.2);if(action==='fit')viewerFit();
 if(action==='notes'){viewerNotes.hidden=!viewerNotes.hidden;viewerFit();}
 if(action==='retry')save(viewerItem().figureId);
 const pin=event.target.closest('[data-pin]');if(pin){viewerNotes.hidden=false;viewerRenderNotes(pin.dataset.pin);}
 const remove=event.target.closest('[data-delete-point]');if(remove){const d=viewerDraft();d.points=d.points.filter(p=>p.id!==remove.dataset.deletePoint);dirty(viewerItem().figureId);viewerRenderNotes();}
});
figureViewer.addEventListener('input',event=>{const id=event.target.dataset.pointText;if(!id)return;const p=viewerDraft().points.find(p=>p.id===id);if(p){p.text=event.target.value;dirty(viewerItem().figureId);}});
viewerStage.addEventListener('dblclick',event=>{if(!event.target.closest('.viewer-pin'))closeFigureViewer();});
viewerStage.addEventListener('wheel',event=>{event.preventDefault();const r=viewerStage.getBoundingClientRect();viewerZoom(Math.exp(-Math.sign(event.deltaY)*.15),event.clientX-r.left,event.clientY-r.top);},{passive:false});
viewerStage.addEventListener('pointerdown',event=>{if(event.button!==0||event.target.closest('button'))return;viewerDrag={x:event.clientX,y:event.clientY,tx:viewerTransform.x,ty:viewerTransform.y};viewerStage.setPointerCapture(event.pointerId);});
viewerStage.addEventListener('pointermove',event=>{if(!viewerDrag)return;viewerTransform.x=viewerDrag.tx+event.clientX-viewerDrag.x;viewerTransform.y=viewerDrag.ty+event.clientY-viewerDrag.y;viewerApply();});
viewerStage.addEventListener('pointerup',()=>{viewerDrag=null;});viewerStage.addEventListener('pointercancel',()=>{viewerDrag=null;});
viewerStage.addEventListener('contextmenu',event=>{
 event.preventDefault();if(!viewerReady)return;
 const r=viewerImage.getBoundingClientRect(),x=(event.clientX-r.left)/r.width,y=(event.clientY-r.top)/r.height;
 if(x<0||x>1||y<0||y>1){viewerFeedbackStatus(viewerItem().figureId,'请在图片范围内右键添加批注');return;}
 const d=viewerDraft(),item=viewerItem();if(d.points.length>=200)return;
 const p={id:crypto.randomUUID(),x,y,output:String(item.number),token:item.file.token,sha256:item.file.meta.sha256,text:''};
 d.points.push(p);viewerNotes.hidden=false;dirty(item.figureId);viewerRenderNotes(p.id);
});
new ResizeObserver(()=>{if(figureViewer.open)viewerFit();}).observe(viewerStage);
