import {solveMatching} from './layout-matching.mjs';
import {solveTreeLayout} from './layout-variants.mjs';
import {performance} from 'node:perf_hooks';import {createHash} from 'node:crypto';import fs from 'node:fs';
import {inside,solidCollision,hitsObstacle,constraintsHold,routeConnection} from './layout-geometry.mjs';
const codeFiles=['constraint-layout.mjs','layout-geometry.mjs','layout-matching.mjs','layout-variants.mjs','pre-draw-layout.mjs'];
const solverCodeHash=createHash('sha256').update(Buffer.concat(codeFiles.map(p=>fs.readFileSync(new URL(p,import.meta.url))))).digest('hex');
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const arrowCode=fs.readFileSync(new URL('../../production-runtime/adobe/editorial-connectors.jsx',import.meta.url),'utf8');
const arrowWidth=Number(arrowCode.match(/width:(\d+(?:\.\d+)?)/)?.[1]);
const depth=Number(arrowCode.match(/depth:(\d+(?:\.\d+)?)/)?.[1]);if(!Number.isFinite(depth)||!Number.isFinite(arrowWidth))throw Error('Arrow geometry contract missing');
function parse(input){
 if(input.version!==1||input.units!=='pt'||!input.canvas||![input.canvas.widthPt,input.canvas.heightPt].every(v=>Number.isFinite(v)&&v>0)||(!Array.isArray(input.elements)||!input.elements.length))throw Error('Scene needs point units, finite canvas and measured elements');
 const ids=new Set(),issues=[];
 for(const e of input.elements){
  if(!e.id||ids.has(e.id))throw Error('Duplicate or missing element ID');ids.add(e.id);
  if(!['text','shape','image','group','plot'].includes(e.kind))throw Error('Unsupported element kind');
  if(![e.x,e.y,e.widthPt,e.heightPt].every(Number.isFinite)||e.widthPt<=0||e.heightPt<=0)issues.push({type:'missing_geometry',id:e.id});
  if(e.kind==='text'&&(!Number.isFinite(e.fontSizePt)||e.fontSizePt<6-.00001||e.fontSizePt>8+.00001))issues.push({type:'invalid_measured_font',id:e.id});
  if(e.candidates&&(!Array.isArray(e.candidates)||e.candidates.some(p=>![p.x,p.y].every(Number.isFinite)||p.widthPt!==undefined&&p.widthPt!==e.widthPt||p.heightPt!==undefined&&p.heightPt!==e.heightPt)))throw Error('Invalid placement candidates');
 }
 for(const e of input.elements)if(e.ownerId&&!ids.has(e.ownerId))throw Error('Unknown element owner');
 for(const c of input.constraints||[])if(!Array.isArray(c.ids)||c.ids.some(id=>!ids.has(id))||!['align-left','align-top','align-center-x','align-center-y','before-x','before-y'].includes(c.type))throw Error('Unknown hard constraint');
 for(const o of input.obstacles||[]){if(o.points){if(o.points.length<2||o.points.some(p=>p.length!==2||!p.every(Number.isFinite)))throw Error('Invalid protected polyline');}else if(![o.x,o.y,o.widthPt,o.heightPt].every(Number.isFinite)||o.widthPt<=0||o.heightPt<=0)throw Error('Invalid protected rectangle');}
 const edgeIds=new Set();for(const e of input.connections||[]){if(!e.id||edgeIds.has(e.id)||!ids.has(e.from)||!ids.has(e.to)||!['left','right','top','bottom'].includes(e.fromPort)||!['left','right','top','bottom'].includes(e.toPort))throw Error('Connection identity or port invalid');edgeIds.add(e.id);if(e.fixed||e.fixedPoints)throw Error('Locked source routes must remain protected geometry; do not request automatic rerouting');}
 return issues;
}
export function solveLayout(input,{budgetMs=50,maxCandidates=32,clock=()=>performance.now()}={}){
 if(!Number.isFinite(budgetMs)||budgetMs<=0)throw Error('Invalid solver budget');
 if(input.tree)return {...solveTreeLayout(input,{budgetMs,clock}),solverCodeHash,inputHash:hash(input)};
 const start=clock();if(!Number.isFinite(budgetMs)||budgetMs<=0||!Number.isInteger(maxCandidates)||maxCandidates<1)throw Error('Invalid solver budget');
 const expired=()=>clock()-start>=budgetMs;
 const base={version:1,inputHash:hash(input),solverCodeHash,scope:'finite candidate domains and bounded orthogonal channels',requiresFinalPdfVerification:true};
 if(input.route==='image')return {...base,status:'exempt'};
 const issues=parse(input);if(issues.length)return {...base,status:'needs-measurement',issues,optimalWithinDomains:false};
 const clearance=input.clearancePt??.5;if(!Number.isFinite(clearance)||clearance<0)throw Error('Invalid clearance');
 const canvas={x:0,y:0,...input.canvas},obstacles=input.obstacles||[],fixed=input.elements.filter(e=>e.fixed),variables=input.elements.filter(e=>!e.fixed);
 let truncated=false,visited=0,tested=0,failedRoutes=0,best=null,timedOut=false;
 const related=(a,b)=>a.ownerId===b.id||b.ownerId===a.id;
 function allowed(e,placed){
  if(!inside(e,canvas)||e.region&&!inside(e,e.region))return false;
  const owner=placed.find(p=>p.id===e.ownerId);if(owner&&!inside(e,owner,e.paddingXPt??4.5,e.paddingYPt??2.7))return false;
  if(obstacles.some(o=>o.ownerId!==e.id&&hitsObstacle(e,o,clearance)))return false;
  if(placed.some(p=>!related(e,p)&&solidCollision(e,p,clearance)&&solidCollision(p,e,clearance)))return false;
  return constraintsHold(input.constraints,[...placed,e]);
 }
 for(let i=0;i<fixed.length;i++)if(!allowed(fixed[i],fixed.slice(0,i)))return {...base,status:'infeasible',issues:[{type:'fixed_geometry_conflict',id:fixed[i].id}],optimalWithinDomains:true};
 const domains=variables.map(e=>{
  let positions=e.candidates;if(!positions){
   const xs=new Set([e.x,clearance,canvas.widthPt-e.widthPt-clearance]),ys=new Set([e.y,clearance,canvas.heightPt-e.heightPt-clearance]);
   for(const o of [...fixed,...obstacles.filter(o=>!o.points)]){xs.add(o.x-e.widthPt-clearance);xs.add(o.x+o.widthPt+clearance);ys.add(o.y-e.heightPt-clearance);ys.add(o.y+o.heightPt+clearance);}
   positions=[...xs].flatMap(x=>[...ys].map(y=>({x,y})));
  }
  const seen=new Set();const rows=positions.filter(p=>{const k=p.x+','+p.y;if(seen.has(k))return false;seen.add(k);return true;}).map(p=>({...e,x:p.x,y:p.y,moveCost:Math.abs(p.x-e.x)+Math.abs(p.y-e.y)})).filter(p=>inside(p,canvas)&&(!p.region||inside(p,p.region))).sort((a,b)=>a.moveCost-b.moveCost||a.y-b.y||a.x-b.x);
  if(rows.length>maxCandidates){truncated=true;rows.length=maxCandidates;}
  return {id:e.id,rows};
 }).sort((a,b)=>a.rows.length-b.rows.length||a.id.localeCompare(b.id));
 const suffix=new Array(domains.length+1).fill(0);for(let i=domains.length-1;i>=0;i--)suffix[i]=suffix[i+1]+(domains[i].rows[0]?.moveCost??Infinity);
 function visit(index,placed,movement){
  if(expired()){timedOut=true;return;}visited++;
  if(best&&movement+suffix[index]>best.score)return;
  if(index===domains.length){
   tested++;if(!constraintsHold(input.constraints,placed))return;
   for(const e of placed)if(e.ownerId){const owner=placed.find(p=>p.id===e.ownerId);if(!owner||!inside(e,owner,e.paddingXPt??4.5,e.paddingYPt??2.7))return;}
   const routes=[];
   for(const e of input.connections||[]){const route=routeConnection({...e,protectedPaths:obstacles},placed,canvas,clearance,expired,{depth,width:arrowWidth});if(!route){failedRoutes++;if(expired())timedOut=true;return;}routes.push(route);}
   const minX=Math.min(...placed.map(p=>p.x),0),minY=Math.min(...placed.map(p=>p.y),0),maxX=Math.max(...placed.map(p=>p.x+p.widthPt),0),maxY=Math.max(...placed.map(p=>p.y+p.heightPt),0);
   const score=movement+(maxX-minX)*(maxY-minY)*.0001+routes.reduce((s,r)=>s+r.cost,0)*.01;
   if(!best||score<best.score)best={score,placements:placed.map(p=>({...p})),routes};return;
  }
  for(const e of domains[index].rows){if(expired()){timedOut=true;return;}if(allowed(e,placed))visit(index+1,[...placed,e],movement+e.moveCost);}
 }
 const matching=!(input.constraints?.length||input.connections?.length)?solveMatching(domains,fixed,allowed,clearance,expired):null;
 if(matching?.placements){const placed=matching.placements;const maxX=Math.max(...placed.map(p=>p.x+p.widthPt),0),maxY=Math.max(...placed.map(p=>p.y+p.heightPt),0);best={score:matching.movement+maxX*maxY*.0001,placements:placed,routes:[]};tested=1;}
 else if(matching?.timedOut)timedOut=true;
 else if(!matching?.infeasible)visit(0,fixed,0);
 const elapsedMs=clock()-start,search={algorithm:matching?.applicable?'min-cost matching':'bounded branch-and-bound',elapsedMs,budgetMs,visited,completeAssignments:tested,failedRoutes,candidateCounts:domains.map(d=>({id:d.id,count:d.rows.length})),domainsTruncated:truncated,timedOut};
 if(!best)return {...base,status:timedOut?'budget-exhausted':truncated?'candidate-domain-exhausted':'infeasible',issues:[{type:timedOut?'search_budget_exhausted':'no_feasible_candidate_assignment'}],optimalWithinDomains:!timedOut&&!truncated,search};
 const placements=input.elements.map(e=>{const p=best.placements.find(p=>p.id===e.id);return {id:e.id,kind:e.kind,x:p.x,y:p.y,widthPt:p.widthPt,heightPt:p.heightPt,fixed:!!e.fixed,dx:p.x-e.x,dy:p.y-e.y};});
 return {...base,status:'solved',violations:[],score:best.score,placements,routes:best.routes,optimalWithinDomains:!timedOut&&!truncated,search,
  execution:{coordinateSystem:'pt, x right, y down',sourceBinding:input.sourceBinding??null,moves:placements.filter(p=>p.dx||p.dy).map(p=>({id:p.id,dx:p.dx,dy:p.dy})),expectedBounds:placements.map(p=>({id:p.id,x:p.x,y:p.y,widthPt:p.widthPt,heightPt:p.heightPt})),mustValidateSourceBeforeMoving:true}};
}

export function solveBatch(input,{budgetMs=500,perFigureBudgetMs=50,clock=()=>performance.now()}={}){
 if(!Array.isArray(input.figures)||!input.figures.length||!Number.isFinite(budgetMs)||budgetMs<=0||!Number.isFinite(perFigureBudgetMs)||perFigureBudgetMs<=0)throw Error('Prepared figure batch and positive budgets required');
 const start=clock(),ids=new Set(),results=[];
 for(const figure of input.figures){
  if(!figure.id||ids.has(figure.id))throw Error('Duplicate or missing figure identity');ids.add(figure.id);
  const remaining=budgetMs-(clock()-start);
  if(remaining<=0){results.push({id:figure.id,status:'budget-exhausted',notStarted:true});continue;}
  try{results.push({id:figure.id,...solveLayout(figure.scene,{budgetMs:Math.min(remaining,perFigureBudgetMs),clock})});}
  catch(error){results.push({id:figure.id,status:'invalid-input',failureOrigin:'upstream-input',error:error.message});}
 }
 return {status:results.every(r=>['solved','exempt'].includes(r.status))?'solved':'partial',results,elapsedMs:clock()-start,budgetMs,perFigureBudgetMs,scope:'Prepared geometry only; measurement and native execution not included'};
}
