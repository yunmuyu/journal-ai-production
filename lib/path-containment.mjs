// Opt-in for declared plain diagrams without unsupported ancestor clipping.
export function auditPathContainment(snapshot,{tolerancePt=.05}={}) {
 const artboard=snapshot.artboard;
 if(!Array.isArray(artboard)||artboard.length!==4||artboard.some(v=>!Number.isFinite(v)))throw Error('Path containment requires measured artboard');
 const issues=[];
 function coordinateExtrema(p0,p1,p2,p3){
  const values=[p0,p3],a=-p0+3*p1-3*p2+p3,b=2*(p0-2*p1+p2),c=p1-p0;
  const roots=[];
  if(Math.abs(a)<1e-10){if(Math.abs(b)>1e-10)roots.push(-c/b);}
  else{const discriminant=b*b-4*a*c;if(discriminant>=0){const d=Math.sqrt(discriminant);roots.push((-b+d)/(2*a),(-b-d)/(2*a));}}
  for(const t of roots)if(t>0&&t<1){const u=1-t;values.push(u*u*u*p0+3*u*u*t*p1+3*u*t*t*p2+t*t*t*p3);}
  return [Math.min(...values),Math.max(...values)];
 }
 for(let index=0;index<(snapshot.pathGeometry||[]).length;index++){
  const path=snapshot.pathGeometry[index];
  if(path.guides||path.hidden||path.opacity===0||path.clipping||(!path.stroked&&!path.filled)||path.filled&&!path.stroked&&path.fillWhite===true)continue;
  const points=path.points||[];if(!points.length)continue;
  let box=[Infinity,-Infinity,-Infinity,Infinity];
  const add=(x,y)=>{box=[Math.min(box[0],x[0]),Math.max(box[1],y[1]),Math.max(box[2],x[1]),Math.min(box[3],y[0])];};
  if(points.length===1)add([points[0][0][0],points[0][0][0]],[points[0][0][1],points[0][0][1]]);
  for(let i=0;i<points.length-(path.closed?0:1);i++){
   const from=points[i],to=points[(i+1)%points.length];
   add(coordinateExtrema(from[0][0],from[1][0],to[0][2],to[0][0]),coordinateExtrema(from[0][1],from[1][1],to[0][3],to[0][1]));
  }
  const half=path.stroked?(path.strokeWidthPt??.5)/2:0;
  box=[box[0]-half,box[1]+half,box[2]+half,box[3]-half];
  if(path.effectiveClipBounds){const clip=path.effectiveClipBounds;box=[Math.max(box[0],clip[0]),Math.min(box[1],clip[1]),Math.min(box[2],clip[2]),Math.max(box[3],clip[3])];if(box[2]<box[0]||box[1]<box[3])continue;}
  if(box[0]<artboard[0]-tolerancePt||box[1]>artboard[1]+tolerancePt||box[2]>artboard[2]+tolerancePt||box[3]<artboard[3]-tolerancePt)
   issues.push({type:'visible_path_outside_artboard',pathIndex:index,pathName:path.name||'',boundsPt:box,artboardPt:artboard});
 }
 return issues;
}
