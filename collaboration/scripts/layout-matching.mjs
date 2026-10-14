import {overlap} from './layout-geometry.mjs';
// Exact polynomial fast path: equally-sized solid objects occupy every disjoint candidate slot.
// With all slots occupied, footprint is constant, so min-cost matching also minimizes the solver objective.
export function solveMatching(domains,fixed,allowed,clearance,expired){
 if(!domains.length||domains.some(d=>d.rows.some(e=>e.ownerId||e.geometry==='outline')))return null;
 const all=domains.flatMap(d=>d.rows);if(!all.length)return null;const w=all[0].widthPt,h=all[0].heightPt;
 if(all.some(e=>Math.abs(e.widthPt-w)>1e-8||Math.abs(e.heightPt-h)>1e-8))return null;
 const slots=[...new Map(all.map(e=>[e.x+','+e.y,e])).values()];if(slots.length!==domains.length)return null;
 for(let i=0;i<slots.length;i++)for(const p of slots.slice(i+1))if(overlap(slots[i],p,clearance))return null;
 const n=domains.length,INF=1e15,cost=domains.map(d=>slots.map(s=>{const e=d.rows.find(p=>p.x===s.x&&p.y===s.y);return e&&allowed(e,fixed)?e.moveCost:INF;}));
 const u=new Array(n+1).fill(0),v=new Array(n+1).fill(0),p=new Array(n+1).fill(0),way=new Array(n+1).fill(0);
 for(let i=1;i<=n;i++){
  if(expired())return {applicable:true,timedOut:true};p[0]=i;let j0=0;const min=new Array(n+1).fill(INF),used=new Array(n+1).fill(false);
  do{
   if(expired())return {applicable:true,timedOut:true};used[j0]=true;const i0=p[j0];let delta=INF,j1=0;
   for(let j=1;j<=n;j++)if(!used[j]){const cur=cost[i0-1][j-1]-u[i0]-v[j];if(cur<min[j]){min[j]=cur;way[j]=j0;}if(min[j]<delta){delta=min[j];j1=j;}}
   if(delta>=INF/2)return {applicable:true,infeasible:true};
   for(let j=0;j<=n;j++)if(used[j]){u[p[j]]+=delta;v[j]-=delta;}else min[j]-=delta;j0=j1;
  }while(p[j0]!==0);
  do{const j1=way[j0];p[j0]=p[j1];j0=j1;}while(j0);
 }
 const placed=fixed.slice();for(let j=1;j<=n;j++){if(cost[p[j]-1][j-1]>=INF/2)return {applicable:true,infeasible:true};placed.push(domains[p[j]-1].rows.find(e=>e.x===slots[j-1].x&&e.y===slots[j-1].y));}
 return {applicable:true,placements:placed,movement:placed.reduce((s,e)=>s+(e.moveCost||0),0)};
}
