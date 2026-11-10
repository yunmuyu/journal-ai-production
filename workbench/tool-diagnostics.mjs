// Preserve structured tool failures through the existing runner boundary.
function jsonObjects(value){
 const rows=[];let start=-1,depth=0,quoted=false,escaped=false;
 for(let i=0;i<value.length;i++){
  const ch=value[i];
  if(start<0){if(ch==='{'){start=i;depth=1;}continue;}
  if(quoted){if(escaped)escaped=false;else if(ch==='\\')escaped=true;else if(ch==='"')quoted=false;continue;}
  if(ch==='"')quoted=true;
  else if(ch==='{')depth++;
  else if(ch==='}'&&!--depth){
   try{rows.push(JSON.parse(value.slice(start,i+1)));}catch{/* Non-JSON process output remains in failure.log. */}
   start=-1;
  }
 }
 return rows;
}

export function extractToolDiagnostic(error){
 const rows=[...jsonObjects(String(error.stderr??'')),...jsonObjects(String(error.stdout??''))];
 const report=rows.findLast(row=>typeof row.error?.code==='string'||row.status==='blocked'&&typeof row.code==='string');
 if(!report)return null;
 const detail=report.error??report,issues=[];
 const visit=value=>{
  if(Array.isArray(value)){for(const item of value)visit(item);}
  else if(value&&typeof value==='object')for(const [key,item] of Object.entries(value)){
   if(key==='issues'&&Array.isArray(item))issues.push(...item);else visit(item);
  }
 };
 visit(detail);
 // Capacity comes from the measured public layout engine, never image dimensions
 // or a suggested replacement for a figure-specific user decision.
 const capacity=detail.capacity;
 const measured=capacity?.version===1&&typeof capacity.figure_id==='string'&&
  typeof capacity.spec_hash==='string'&&/^[a-f\d]{64}$/.test(capacity.spec_hash)&&
  Number.isFinite(capacity.column_mm)&&Number.isFinite(capacity.proposed_font_size_pt)&&
  typeof capacity.summary==='string';
 return {version:1,code:detail.code,message:detail.message??(typeof detail.detail==='string'?detail.detail:''),issues,detail,
  ...(measured?{summary:capacity.summary,capacity}: {})};
}
