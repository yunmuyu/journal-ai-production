const EPS=1e-7;
export const rect=e=>({x:e.x,y:e.y,widthPt:e.widthPt,heightPt:e.heightPt});
export function overlap(a,b,gap=0){return a.x<b.x+b.widthPt+gap-EPS&&a.x+a.widthPt+gap>b.x+EPS&&a.y<b.y+b.heightPt+gap-EPS&&a.y+a.heightPt+gap>b.y+EPS;}
export function inside(a,b,padX=0,padY=padX){return a.x>=b.x+padX-EPS&&a.y>=b.y+padY-EPS&&a.x+a.widthPt<=b.x+b.widthPt-padX+EPS&&a.y+a.heightPt<=b.y+b.heightPt-padY+EPS;}
export function segmentHits(a,b,r,gap=0){
 let lo=0,hi=1;const mins=[r.x-gap,r.y-gap],maxs=[r.x+r.widthPt+gap,r.y+r.heightPt+gap];
 for(let i=0;i<2;i++){const d=b[i]-a[i];if(Math.abs(d)<EPS){if(a[i]<=mins[i]+EPS||a[i]>=maxs[i]-EPS)return false;}else{const p=(mins[i]-a[i])/d,q=(maxs[i]-a[i])/d;lo=Math.max(lo,Math.min(p,q));hi=Math.min(hi,Math.max(p,q));if(lo>=hi-EPS)return false;}}
 return hi>EPS&&lo<1-EPS;
}
export function solidCollision(element,other,gap=0){
 if(other.geometry==='outline')return outline(other).slice(1).some((p,i)=>segmentHits(outline(other)[i],p,element,gap));
 return overlap(element,other,gap);
}
export const outline=r=>[[r.x,r.y],[r.x+r.widthPt,r.y],[r.x+r.widthPt,r.y+r.heightPt],[r.x,r.y+r.heightPt],[r.x,r.y]];
export function hitsObstacle(e,o,gap){
 if(o.points)return o.points.slice(1).some((p,i)=>segmentHits(o.points[i],p,e,gap+(o.strokeWidthPt??.5)/2));
 return solidCollision(e,o,gap);
}
export function constraintsHold(constraints,placed){
 const map=new Map(placed.map(e=>[e.id,e]));
 for(const c of constraints||[]){const rows=c.ids.map(id=>map.get(id));if(rows.some(e=>!e))continue;
  const fields={'align-left':e=>e.x,'align-top':e=>e.y,'align-center-x':e=>e.x+e.widthPt/2,'align-center-y':e=>e.y+e.heightPt/2};
  if(fields[c.type]){const f=fields[c.type];if(rows.some(e=>Math.abs(f(e)-f(rows[0]))>EPS))return false;}
  else if(c.type==='before-x'){if(rows.length!==2||rows[0].x+rows[0].widthPt+(c.gapPt??0)>rows[1].x+EPS)return false;}
  else if(c.type==='before-y'){if(rows.length!==2||rows[0].y+rows[0].heightPt+(c.gapPt??0)>rows[1].y+EPS)return false;}
  else throw Error('Unsupported hard constraint: '+c.type);
 }
 return true;
}
const directions={right:[1,0],left:[-1,0],top:[0,-1],bottom:[0,1]};
function port(n,side){switch(side){case 'right':return[n.x+n.widthPt,n.y+n.heightPt/2];case 'left':return[n.x,n.y+n.heightPt/2];case 'top':return[n.x+n.widthPt/2,n.y];case 'bottom':return[n.x+n.widthPt/2,n.y+n.heightPt];default:throw Error('Explicit connection port required');}}
export function routeConnection(edge,placed,canvas,clearance,expired,arrow){
 const map=new Map(placed.map(n=>[n.id,n])),from=map.get(edge.from),to=map.get(edge.to);if(!from||!to)throw Error('Unknown connection endpoint');
 const a=port(from,edge.fromPort),b=port(to,edge.toPort),da=directions[edge.fromPort],db=directions[edge.toPort];
 const xs=new Set([a[0],b[0]]),ys=new Set([a[1],b[1]]);
 for(const n of placed){xs.add(n.x-clearance);xs.add(n.x+n.widthPt+clearance);ys.add(n.y-clearance);ys.add(n.y+n.heightPt+clearance);}
  const stub=Math.max(3*72/25.4,edge.both?2*arrow.depth+clearance:arrow.depth+clearance);
 const qa=a.map((v,i)=>v+da[i]*stub),qb=b.map((v,i)=>v+db[i]*stub);
 const outward=[[qa,qb],[qa,[qa[0],qb[1]],qb],[qa,[qb[0],qa[1]],qb]];
 for(const x of xs)outward.push([qa,[x,qa[1]],[x,qb[1]],qb]);
 for(const y of ys)outward.push([qa,[qa[0],y],[qb[0],y],qb]);
 const raw=outward.map(p=>[a,...p,b]);raw.push([a,b],[a,[a[0],b[1]],b],[a,[b[0],a[1]],b]);
 for(const x of xs)raw.push([a,[x,a[1]],[x,b[1]],b]);for(const y of ys)raw.push([a,[a[0],y],[b[0],y],b]);
 // Four-bend channels provide outward runs from both ports even if a protected block occupies the direct corridor.
 for(const x of xs)for(const y of ys){if(expired())return null;raw.push([a,[x,a[1]],[x,y],[b[0],y],b]);raw.push([a,[a[0],y],[x,y],[x,b[1]],b]);}
 let best=null;
 for(const route of raw){if(expired())return null;
  const points=route.filter((p,i)=>!i||p[0]!==route[i-1][0]||p[1]!==route[i-1][1]);if(points.length<2)continue;
  if(points.some(p=>p[0]<0||p[1]<0||p[0]>canvas.widthPt||p[1]>canvas.heightPt))continue;
  const first=points[1].map((v,i)=>v-a[i]),last=points.at(-2).map((v,i)=>v-b[i]);
  if(first[0]*da[0]+first[1]*da[1]<=0||last[0]*db[0]+last[1]*db[1]<=0)continue;
  const firstLength=Math.hypot(...first),lastLength=Math.hypot(...last);if(lastLength<arrow.depth||edge.both&&firstLength<2*arrow.depth)continue;
  let valid=true,lengthPt=0;
  for(let i=1;i<points.length;i++){
   const p=points[i-1],q=points[i];lengthPt+=Math.hypot(q[0]-p[0],q[1]-p[1]);
   if(placed.some(n=>n.geometry!=='outline'&&segmentHits(p,q,n,n.id===edge.from||n.id===edge.to?0:clearance)))valid=false;
   if((edge.protectedPaths||[]).some(o=>hitsObstacle({x:Math.min(p[0],q[0]),y:Math.min(p[1],q[1]),widthPt:Math.abs(q[0]-p[0])+EPS,heightPt:Math.abs(q[1]-p[1])+EPS},o,clearance)))valid=false;
  }
    const heads=[[b,points.at(-2),edge.to]];if(edge.both)heads.push([a,points[1],edge.from]);
  for(const [tip,previous,targetId] of heads){
   const dx=tip[0]-previous[0],dy=tip[1]-previous[1],length=Math.hypot(dx,dy),ux=dx/length,uy=dy/length;
   const vertices=[tip,[tip[0]-ux*arrow.depth+uy*arrow.width/2,tip[1]-uy*arrow.depth-ux*arrow.width/2],[tip[0]-ux*arrow.depth-uy*arrow.width/2,tip[1]-uy*arrow.depth+ux*arrow.width/2]];
   const xs=vertices.map(p=>p[0]),ys=vertices.map(p=>p[1]),head={x:Math.min(...xs),y:Math.min(...ys),widthPt:Math.max(...xs)-Math.min(...xs),heightPt:Math.max(...ys)-Math.min(...ys)};
   if(!inside(head,{x:0,y:0,...canvas})||placed.some(n=>n.geometry!=='outline'&&overlap(head,n,n.id===targetId?0:clearance))||edge.protectedPaths?.some(o=>hitsObstacle(head,o,clearance)))valid=false;
  }
  if(!valid)continue;const cost=lengthPt+(points.length-2)*4;
  if(!best||cost<best.cost)best={id:edge.id,points,lengthPt,cost,both:!!edge.both};
 }
 return best;
}
