import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {auditDiagram} from '../../lib/diagram-audit.mjs';

const PT_PER_MM=72/25.4;
// Read the shared layout metric contract. Prefer the formal production-runtime file when
// present; otherwise fall back to the vendored copy so the solver stays self-contained on an
// experimental branch that must not modify the production runtime.
const prodMetricFile=new URL('../../production-runtime/adobe/editorial-layout.jsx',import.meta.url);
const vendoredMetricFile=new URL('./editorial-layout-metrics.jsx',import.meta.url);
function sharedMetrics(){
let metricCode;
try{ metricCode=fs.readFileSync(prodMetricFile,'utf8'); }
catch{ metricCode=fs.readFileSync(vendoredMetricFile,'utf8'); }
const names=['padX','padY','compactGap','framePad','minFontSize'];
const metrics=Object.fromEntries(names.map(name=>{
 const match=metricCode.match(new RegExp(String.raw`\b${name}:(\d+(?:\.\d+)?)`));
 if(!match)throw Error('Shared layout metric unavailable: '+name);
 return [name,Number(match[1])];
}));
if(!metricCode.includes('arrowLength:3*72/25.4'))throw Error('Arrow contract changed');
metrics.arrowLength=3*PT_PER_MM;
const arrowCode=fs.readFileSync(new URL('../../production-runtime/adobe/editorial-connectors.jsx',import.meta.url),'utf8');
const arrowDepth=Number(arrowCode.match(/depth:(\d+(?:\.\d+)?)/)?.[1]);if(!Number.isFinite(arrowDepth))throw Error('Shared Arrow 5 contract missing');
metrics.arrowDepth=arrowDepth;metrics.bidirectionalArrowLength=Math.max(metrics.arrowLength,2*arrowDepth+4);
return {metrics,metricCode};
}
const hash=value=>createHash('sha256').update(typeof value==='string'?value:JSON.stringify(value)).digest('hex');
const intersects=(a,b)=>a.x<b.x+b.widthPt-1e-8&&a.x+a.widthPt>b.x+1e-8&&a.y<b.y+b.heightPt-1e-8&&a.y+a.heightPt>b.y+1e-8;
const inkBounds=(x,y,w,h)=>[x,-y,x+w,-y-h];
const pointPath=points=>points.map(([x,y])=>[[x,-y,x,-y],[x,-y]]);

export function calculateLayout(input){
 if(input.route==='image')return {status:'exempt',reason:'PS image route'};
 const {metrics,metricCode}=sharedMetrics();
 const base={version:1,inputHash:hash(input),rulesHash:hash(metricCode),order:['text','boxes','groups','frames','connections','fit','collision-check']};
 if(!input.tree)return {...base,status:'needs-measurement',issues:[{type:'missing_layout_input'}]};
 if(input.version!==1||!Number.isFinite(input.widthMm)||input.widthMm*PT_PER_MM<=.5||!Number.isFinite(input.fontSizePt)||input.fontSizePt<6||input.fontSizePt>8||!input.font)throw Error('Invalid layout dimensions or font identity');
 const tree=structuredClone(input.tree),measures=input.measurements||{},issues=[],ids=new Set(),labels=[],leaves=[];
 const widthGroups=new Map(),heightGroups=new Map();
 function label(id,text){
  if(!id||ids.has(id))throw Error('Duplicate or missing layout ID: '+id);ids.add(id);
  const m=measures[id];
  if(!m||m.text!==text||m.font!==input.font||m.fontSizePt!==input.fontSizePt||m.styleFingerprint!==(input.styleFingerprint)||![m.widthPt,m.heightPt].every(v=>Number.isFinite(v)&&v>0)){
   issues.push({type:'missing_or_stale_measurement',id,text});return {widthPt:0,heightPt:0};
  }
  labels.push({id,text,measurement:m});return m;
 }
 function prepare(n){
  if(n.kind==='box'){
   n.ink=label(n.id,n.text);n.widthPt=n.ink.widthPt+2*metrics.padX;n.heightPt=n.ink.heightPt+2*metrics.padY;
   if(n.shape==='diamond'){n.widthPt*=2;n.heightPt*=2;}
   else if(n.shape==='ellipse'){n.widthPt*=Math.SQRT2;n.heightPt*=Math.SQRT2;}
   else if(n.shape!==undefined&&n.shape!=='rectangle')throw Error('Unsupported measured shape: '+n.shape);
   leaves.push(n);
  }else if(n.kind==='frame'){n.ink=label(n.id,n.title);prepare(n.content);}
  else if(n.kind==='row'||n.kind==='column'){
   if(!Array.isArray(n.children)||!n.children.length)throw Error('Empty group');
   if(n.gapPt!==undefined&&(!Number.isFinite(n.gapPt)||n.gapPt<0))throw Error('Invalid gap');
   n.children.forEach(prepare);
  }else throw Error('Unsupported layout kind: '+n.kind);
 }
  prepare(tree);
 for(const e of input.edges||[])if(e.label)label('edge:'+e.id,e.label.text);
 function groupGap(n){
  if(n.gapPt!==undefined)return n.gapPt;
  const ids=n.children.map(c=>c.id);
  const linked=(input.edges||[]).some(e=>ids.includes(e.from)&&Math.abs(ids.indexOf(e.from)-ids.indexOf(e.to))===1&&ids.includes(e.to));
  return linked?((input.edges||[]).some(e=>e.both&&ids.includes(e.from)&&ids.includes(e.to))?metrics.bidirectionalArrowLength:metrics.arrowLength):metrics.compactGap;
 }
 if(issues.length)return {...base,status:'needs-measurement',issues};
 const equalize=(n,key,groups,dimension)=>{
  if(n[key]){const v=Math.max(n[dimension],groups.get(n[key])||0);groups.set(n[key],v);n[dimension]=v;}
 };
 function measure(n){
  if(n.kind==='frame'){
   measure(n.content);n.widthPt=Math.max(n.content.widthPt,n.ink.widthPt)+2*metrics.framePad;
   n.heightPt=n.content.heightPt+n.ink.heightPt+metrics.compactGap+2*metrics.framePad;
  }else if(n.kind==='row'||n.kind==='column'){
   n.children.forEach(measure);const row=n.kind==='row',gap=groupGap(n);
   n.widthPt=row?n.children.reduce((s,c)=>s+c.widthPt,0)+gap*(n.children.length-1):Math.max(...n.children.map(c=>c.widthPt));
   n.heightPt=row?Math.max(...n.children.map(c=>c.heightPt)):n.children.reduce((s,c)=>s+c.heightPt,0)+gap*(n.children.length-1);
  }
  equalize(n,'widthGroup',widthGroups,'widthPt');equalize(n,'heightGroup',heightGroups,'heightPt');
 }
  let settled=false;
 for(let i=0;i<=ids.size+1;i++){
  const before=JSON.stringify([...widthGroups,...heightGroups]);measure(tree);
  if(before===JSON.stringify([...widthGroups,...heightGroups])){settled=true;break;}
 }
 if(!settled)throw Error('Equal-size group dependency did not converge; check ancestor/child grouping');
 const nodes=[],texts=[],frames=[];
 function putText(n,x,y,w,h,text){const m=n.ink;texts.push({id:n.id,text,x:x+(w-m.widthPt)/2,y:y+(h-m.heightPt)/2,widthPt:m.widthPt,heightPt:m.heightPt});}
 function place(n,x,y){
  if(n.kind==='box'){nodes.push({id:n.id,shape:n.shape||'rectangle',x,y,widthPt:n.widthPt,heightPt:n.heightPt});putText(n,x,y,n.widthPt,n.heightPt,n.text);}
  else if(n.kind==='frame'){
   frames.push({id:n.id,x,y,widthPt:n.widthPt,heightPt:n.heightPt});putText(n,x+metrics.framePad,y+metrics.framePad,n.widthPt-2*metrics.framePad,n.ink.heightPt,n.title);
   place(n.content,x+metrics.framePad+(n.widthPt-2*metrics.framePad-n.content.widthPt)/2,y+metrics.framePad+n.ink.heightPt+metrics.compactGap);
  }else{
   let cursor=0;const row=n.kind==='row';
   for(const c of n.children){place(c,x+(row?cursor:(n.widthPt-c.widthPt)/2),y+(row?(n.heightPt-c.heightPt)/2:cursor));cursor+=(row?c.widthPt:c.heightPt)+groupGap(n);}
  }
 }
 place(tree,0,0);
 const all=new Map([...nodes,...frames].map(n=>[n.id,n]));
 function port(id,side){const n=all.get(id);if(!n)throw Error('Unknown edge endpoint: '+id);switch(side){case 'top':return[n.x+n.widthPt/2,n.y];case 'bottom':return[n.x+n.widthPt/2,n.y+n.heightPt];case 'left':return[n.x,n.y+n.heightPt/2];case 'right':return[n.x+n.widthPt,n.y+n.heightPt/2];default:throw Error('Explicit cardinal edge port required');}}
 const edgeIds=new Set();
 const edges=(input.edges||[]).map(e=>{
  if(!e.id||edgeIds.has(e.id))throw Error('Duplicate or missing edge ID');edgeIds.add(e.id);
  const a=port(e.from,e.fromPort),b=port(e.to,e.toPort),via=e.via||[];
  if(!Array.isArray(via)||via.some(p=>!Array.isArray(p)||p.length!==2||p.some(v=>!Number.isFinite(v))))throw Error('Invalid edge route');
  const points=[a,...via,b];if(!via.length&&a[0]!==b[0]&&a[1]!==b[1])points.splice(1,0,[a[0],b[1]]);
    if(points.slice(1).some((p,i)=>p[0]!==points[i][0]&&p[1]!==points[i][1]))throw Error('Only orthogonal routes are supported; provide measured via points');
  if(e.label){
   const segment=e.label.segment??0,p=points[segment],q=points[segment+1],m=labels.find(t=>t.id==='edge:'+e.id).measurement;
   if(!p||!q)throw Error('Arrow label segment missing');
   const gap=e.label.gapPt??metrics.framePad;if(!Number.isFinite(gap)||gap<0)throw Error('Invalid label gap');
   let x,y;
   if(p[0]===q[0]){if(!['left','right'].includes(e.label.side))throw Error('Vertical label side required');x=e.label.side==='right'?p[0]+gap:p[0]-gap-m.widthPt;y=(p[1]+q[1]-m.heightPt)/2;}
   else{if(!['top','bottom'].includes(e.label.side))throw Error('Horizontal label side required');x=(p[0]+q[0]-m.widthPt)/2;y=e.label.side==='bottom'?p[1]+gap:p[1]-gap-m.heightPt;}
   texts.push({id:'edge:'+e.id,text:e.label.text,x,y,widthPt:m.widthPt,heightPt:m.heightPt});
  }
  const lengthPt=points.slice(1).reduce((s,p,i)=>s+Math.hypot(p[0]-points[i][0],p[1]-points[i][1]),0);
  if(lengthPt<metrics.arrowLength-1e-8)issues.push({type:'short_arrow',edgeId:e.id,lengthPt,requiredPt:metrics.arrowLength});
  return {...e,points,lengthPt};
 });
 // The same geometric auditor checks actual output and predicted text/path intersections.
 const paths=edges.map(e=>({name:e.id,stroked:true,strokeWidthPt:.5,points:pointPath(e.points)}));
  const boxPaths=[...nodes,...frames].map(n=>{
  const l=n.x,r=l+n.widthPt,t=n.y,b=t+n.heightPt,cx=(l+r)/2,cy=(t+b)/2;
  const vertices=n.shape==='diamond'?[[cx,t],[r,cy],[cx,b],[l,cy]]:[[l,t],[r,t],[r,b],[l,b]];
  return {name:'JFW_BOX_FRAME_'+n.id,stroked:true,closed:true,strokeWidthPt:.5,points:pointPath(vertices)};
 });
 const audit=auditDiagram({texts:texts.map((t,i)=>({index:i,text:t.text,name:nodes.some(n=>n.id===t.id)?'JFW_BOX_TEXT_'+t.id:'FRAME_TITLE_'+t.id,inkBounds:inkBounds(t.x,t.y,t.widthPt,t.heightPt)})),pathGeometry:[...paths,...boxPaths]});
  issues.push(...audit.issues);
 for(let i=0;i<texts.length;i++)for(const t of texts.slice(i+1))if(intersects(texts[i],t))issues.push({type:'text_overlap',ids:[texts[i].id,t.id]});
 for(const e of edges)for(const n of nodes)if(n.id!==e.from&&n.id!==e.to){
  const check=auditDiagram({texts:[{text:n.id,inkBounds:inkBounds(n.x,n.y,n.widthPt,n.heightPt)}],pathGeometry:[paths.find(p=>p.name===e.id)]});
  if(check.issues.length)issues.push({type:'edge_node_collision',edgeId:e.id,nodeId:n.id});
 }
 for(let i=0;i<nodes.length;i++)for(const other of nodes.slice(i+1))if(intersects(nodes[i],other))issues.push({type:'node_overlap',ids:[nodes[i].id,other.id]});
 const points=[...edges.flatMap(e=>e.points),...texts.flatMap(t=>[[t.x,t.y],[t.x+t.widthPt,t.y+t.heightPt]])],left=Math.min(0,...points.map(p=>p[0])),top=Math.min(0,...points.map(p=>p[1]));
 const naturalWidthPt=Math.max(tree.widthPt,...points.map(p=>p[0]))-left;
 const naturalHeightPt=Math.max(tree.heightPt,...points.map(p=>p[1]))-top;
 const scale=Math.min(1,(input.widthMm*PT_PER_MM-.5)/naturalWidthPt),finalFontSizePt=input.fontSizePt*scale;
 for(const edge of edges){const p=edge.points,first=Math.hypot(p[1][0]-p[0][0],p[1][1]-p[0][1])*scale,last=Math.hypot(p.at(-1)[0]-p.at(-2)[0],p.at(-1)[1]-p.at(-2)[1])*scale;if(last<metrics.arrowDepth/2||edge.both&&first<2*metrics.arrowDepth)issues.push({type:'arrow_head_segment_too_short',edgeId:edge.id,firstPt:first,lastPt:last});}
 const status=finalFontSizePt<metrics.minFontSize-1e-6?'needs-reflow':issues.length?'conflict':'ready';
 return {...base,status,issues,targetWidthMm:input.widthMm,naturalWidthPt,naturalHeightPt,scale,finalFontSizePt,nodes,texts,frames,edges,
  coordinateSystem:'points, x right, y down; coordinates before whole-artwork fit',fit:{translatePt:[-left,-top],scale,finalWidthMm:(naturalWidthPt*scale+.5)/PT_PER_MM,finalHeightMm:(naturalHeightPt*scale+.5)/PT_PER_MM},requiresFinalPdfVerification:true};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const [src,out]=process.argv.slice(2);if(!src||!out)throw Error('Usage: pre-draw-layout.mjs INPUT.json REPORT.json');const r=calculateLayout(JSON.parse(fs.readFileSync(src,'utf8').replace(/^\uFEFF/,'')));fs.writeFileSync(out,JSON.stringify(r,null,2));console.log(JSON.stringify({status:r.status,report:out}));if(!['ready','exempt'].includes(r.status))process.exitCode=2;}catch(e){console.error(e.message);process.exitCode=1;}
}