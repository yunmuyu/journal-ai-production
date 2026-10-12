// Candidate boundary; does not write production records or call models.
const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
export function protectDecision(raw, local) {
 if(!raw || typeof raw!=='object' || Array.isArray(raw)) throw Error('Invalid model decision');
 const result=structuredClone(raw), errors=[];
 const locked=new Map();
 for(const c of local.constraints||[]) { if(locked.has(c.field)&&!same(locked.get(c.field),c.value)) throw Error('Conflicting local constraints'); locked.set(c.field,c.value); }
 const reject=(code,field,proposed,kept,basis)=>errors.push({code,field,proposed,kept,basis});
 for(const lock of local.constraints||[]) {
  if(!lock.evidence || lock.confirmed!==true) throw Error('Unverified local constraint');
  if(!['route','delivery','width'].includes(lock.field)) throw Error('Unsupported constraint field');
  if(!same(result[lock.field],lock.value)) reject('USER_CONSTRAINT_CONFLICT',lock.field,result[lock.field],lock.value,lock.evidence);
  result[lock.field]=structuredClone(lock.value);
 }
 const marks=local.originalMarks||[];
 for(const mark of result.originalMarks||[]) {
  if(!marks.some(m=>m.text===mark.text && m.regionId===mark.regionId)) reject('UNSUPPORTED_ORIGINAL_MARK','originalMarks',mark,null,'原文证据中未登记该标记');
 }
 result.originalMarks=structuredClone(marks);
 // A visual region is not an author caption or a deliverable.
 result.regions=(result.regions||[]).map((r,i)=>({id:r.id||'region-'+(i+1),description:r.description||r.region||''}));
 if(result.delivery?.count>1 && !marks.length && !locked.has('delivery')) {
  reject('UNGROUNDED_SPLIT','delivery',result.delivery,null,'无原始子图题或本地拆分依据；内部区域数量不是交付数量');
  result.delivery=null;
 }
 if(result.delivery) {
  const outputs=result.delivery.outputs||[];
  const regionIds=new Set((local.regions||[]).map(r=>r.id));
  const covered=outputs.flatMap(o=>o.regionIds||[]);
  if(result.delivery.count!==outputs.length || !Number.isInteger(result.delivery.count) || result.delivery.count<1 || covered.length!==regionIds.size || new Set(covered).size!==covered.length || covered.some(id=>!regionIds.has(id))) {
   reject('INVALID_DELIVERY_COVERAGE','delivery',result.delivery,null,'数量、输出映射必须完整且不重复');
   result.delivery=null;
  } else for(const output of outputs) {
   if(output.originalCaption!=null && !marks.some(m=>m.text===output.originalCaption && output.regionIds.includes(m.regionId))) {
    reject('INVENTED_DELIVERY_CAPTION','delivery',output.originalCaption,null,'内部区域名称不得冒充原作者子图题');
    output.originalCaption=null;
   }
  }
 }
 const widthLock=(local.constraints||[]).find(c=>c.field==='width');
 if(widthLock) result.width={...structuredClone(widthLock.value),status:'user-required',capacityVerified:false};
 else if(local.fit?.verified===true && local.fit.evidence) result.width=structuredClone(local.fit);
 else {
  if(raw.width?.capacityVerified===true || raw.width?.status==='verified') reject('UNSUPPORTED_CAPACITY','width',raw.width,null,'没有本地fit和几何实测证据');
  result.width={value:null,status:'待实排验证',capacityVerified:false,executor:'existing-fit-and-geometry'};
 }
 if(local.source?.status!=='match') {
  reject('SOURCE_NOT_VERIFIED','source',raw.source,local.source,local.source?.evidence||'缺少本地图源证据');
  result.route='review';result.delivery=null;result.width={value:null,status:'blocked-source',capacityVerified:false};
 }
 result.source=structuredClone(local.source);
 return {raw:structuredClone(raw),result,errors,modelConflict:errors.some(e=>e.code==='USER_CONSTRAINT_CONFLICT'),publishable:false};
}
