(()=>{
const states=new WeakMap();
function state(el){if(!states.has(el))states.set(el,{scale:1,x:0,y:0});return states.get(el);}
function paint(el,s){el.querySelector('img').style.transform='translate('+s.x+'px,'+s.y+'px) scale('+s.scale+')';el.dataset.scale=s.scale.toFixed(2);}
function reset(el){const s=state(el);s.scale=1;s.x=0;s.y=0;paint(el,s);}
document.addEventListener('wheel',e=>{const el=e.target.closest('.panzoom');if(!el)return;e.preventDefault();const s=state(el),r=el.getBoundingClientRect(),px=e.clientX-r.left,py=e.clientY-r.top,next=Math.max(.5,Math.min(8,s.scale*Math.exp(-e.deltaY*.0015)));s.x=px-(px-s.x)*next/s.scale;s.y=py-(py-s.y)*next/s.scale;s.scale=next;paint(el,s);},{passive:false});
document.addEventListener('pointerdown',e=>{const el=e.target.closest('.panzoom');if(!el||e.button!==0||e.target.closest('button'))return;const s=state(el);s.pointer=e.pointerId;s.lastX=e.clientX;s.lastY=e.clientY;el.setPointerCapture(e.pointerId);e.preventDefault();});
document.addEventListener('pointermove',e=>{const el=e.target.closest('.panzoom');if(!el)return;const s=state(el);if(s.pointer!==e.pointerId)return;s.x+=e.clientX-s.lastX;s.y+=e.clientY-s.lastY;s.lastX=e.clientX;s.lastY=e.clientY;paint(el,s);});
for(const type of ['pointerup','pointercancel'])document.addEventListener(type,e=>{const el=e.target.closest('.panzoom');if(!el)return;const s=state(el);if(s.pointer===e.pointerId){delete s.pointer;if(el.hasPointerCapture(e.pointerId))el.releasePointerCapture(e.pointerId);}});
document.addEventListener('click',e=>{if(e.target.closest('.reset-view'))reset(e.target.closest('.panzoom'));});
document.addEventListener('dblclick',e=>{const el=e.target.closest('.panzoom');if(el)reset(el);});
document.addEventListener('keydown',e=>{const el=e.target.closest('.panzoom');if(el&&e.key==='0'){e.preventDefault();reset(el);}});
})();