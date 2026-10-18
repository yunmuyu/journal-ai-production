import {auditPathContainment} from './path-containment.mjs';
export function auditDiagram(snapshot,{expectedNodeIds=[],checkPathContainment=false,owners=[]}={}) {
 const ownerChecked=new Set();
 const issues=checkPathContainment?auditPathContainment(snapshot):[],paths=snapshot.pathGeometry||[];
 if((snapshot.texts||[]).length&&!paths.length)issues.push({type:"missing_diagram_paths"});
 for(const id of expectedNodeIds)if(!paths.some(p=>p.name==="AI_FLOW_NODE_"+id)||(snapshot.texts||[]).every(t=>t.name!=="AI_FLOW_TEXT_"+id))issues.push({type:"missing_node_mapping",nodeId:id});
 function crosses(a,b,rect){
  let low=0,high=1;const delta=[b[0]-a[0],b[1]-a[1]];
  for(let axis=0;axis<2;axis++){
   const min=axis?rect[3]:rect[0],max=axis?rect[1]:rect[2];
   if(Math.abs(delta[axis])<1e-9){if(a[axis]<=min||a[axis]>=max)return false;continue;}
   const x=(min-a[axis])/delta[axis],y=(max-a[axis])/delta[axis];
   low=Math.max(low,Math.min(x,y));high=Math.min(high,Math.max(x,y));if(low>=high)return false;
  }
  return high>0&&low<1;
 }
 function segments(path){
  const points=path.points||[],result=[];
  for(let i=0;i<points.length-(path.closed?0:1);i++){
   const a=points[i],b=points[(i+1)%points.length],p=a[0].slice(0,2),q=b[0].slice(0,2),c=a[1],d=b[0].slice(2,4);
   const straight=p.every((v,j)=>Math.abs(v-c[j])<0.001)&&q.every((v,j)=>Math.abs(v-d[j])<0.001);
   let previous=p;for(let step=1;step<=(straight?1:32);step++){
    const t=step/(straight?1:32),u=1-t,next=p.map((v,j)=>u*u*u*v+3*u*u*t*c[j]+3*u*t*t*d[j]+t*t*t*q[j]);
    result.push([previous,next]);previous=next;
   }
  }
  return result;
 }
 for(const text of snapshot.texts||[]){
  const ink=text.inkBounds;if(!ink)throw Error('Diagram audit requires measured text inkBounds');
  if(/^JFW_DIAGRAM_SIDE_(LEFT|RIGHT)$/.test(text.note||'')){
   const left=text.note.endsWith('LEFT'),boundaries=paths.filter(p=>/^AI_FLOW_/.test(p.name||'')&&!p.clipping&&!p.guides&&!p.hidden&&p.opacity!==0).flatMap(p=>p.points.map(point=>point[0][0]+(left?-1:1)*(p.stroked?p.strokeWidthPt/2:0)));
   if(!boundaries.length)throw Error('No diagram boundary for side label audit');
   const distance=left?Math.min(...boundaries)-ink[2]:ink[0]-Math.max(...boundaries);
   if(distance<3*(text.size||8)/8-.15)issues.push({type:'side_label_clearance',textIndex:text.index,text:text.text,distancePt:distance});
  }
  for(let index=0;index<paths.length;index++){
   const p=paths[index];if(!p.stroked||p.clipping||p.guides||p.hidden||p.opacity===0)continue;
   const half=(p.strokeWidthPt??0.5)/2,protectedInk=[ink[0]-half,ink[1]+half,ink[2]+half,ink[3]-half];
   if(!owners.some(o=>o.textIndex===text.index&&o.verifiedBeforeExport===true)&&segments(p).some(([a,b])=>crosses(a,b,protectedInk)))issues.push({type:'text_path_collision',textIndex:text.index,pathIndex:index,text:text.text});
   const textFirst=String(text.name||'').startsWith('JFW_BOX_TEXT_');
   const ownerName=textFirst?'JFW_BOX_FRAME_'+text.name.slice('JFW_BOX_TEXT_'.length):'AI_FLOW_NODE_'+String(text.name||'').replace('AI_FLOW_TEXT_','');
   const explicit=owners.find(o=>o.textIndex===text.index&&o.pathIndex===index);
   if((p.name===ownerName||explicit?.placement==='inside')&&p.closed){
    ownerChecked.add(text.index);
    const anchors=p.points.map(point=>point[0]),box=[Math.min(...anchors.map(a=>a[0])),Math.max(...anchors.map(a=>a[1])),Math.max(...anchors.map(a=>a[0])),Math.min(...anchors.map(a=>a[1]))];
    const padding=[ink[0]-box[0],box[1]-ink[1],box[2]-ink[2],ink[3]-box[3]],scale=textFirst?(text.layoutScale??1):(text.size||8)/8;
    if(padding.some((v,i)=>v<(i%2?2.7:4.5)*scale-0.15))issues.push({type:'node_text_padding',textIndex:text.index,pathIndex:index,text:text.text,paddingPt:padding});
   }
  }
 }
 const unmapped=(snapshot.texts||[]).filter(t=>!ownerChecked.has(t.index)&&!owners.some(o=>o.textIndex===t.index&&o.placement!=='inside')).map(t=>t.index);
 return {ok:issues.length===0,issues,coverage:{textPath:'checked',ownerPadding:unmapped.length?'incomplete':'checked',unmappedTextIndices:unmapped,occlusion:owners.some(o=>o.verifiedBeforeExport)?'native_placement_for_managed_labels_only':'not_checked',formulaPathSemantics:'not_checked'},requiresTopologyAndPdfReview:true};
}
