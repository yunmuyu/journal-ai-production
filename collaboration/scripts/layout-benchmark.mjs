import fs from 'node:fs';import {solveLayout,solveBatch} from './constraint-layout.mjs';
export function chartScene(count=24){
 const canvas={widthPt:260,heightPt:190},elements=[{id:'plot',kind:'plot',geometry:'outline',x:2,y:2,widthPt:254,heightPt:184,fixed:true}];
 for(let i=0;i<count;i++){const col=i%4,row=Math.floor(i/4),x=10+col*55,y=5+row*24;elements.push({id:'label'+i,kind:'text',x,y,widthPt:30,heightPt:8,fontSizePt:8,candidates:[{x,y},{x,y:y+12}]});}
 return {version:1,units:'pt',canvas,elements,obstacles:Array.from({length:Math.ceil(count/4)},(_,row)=>({id:'series'+row,ownerId:'plot',strokeWidthPt:.5,points:[[5,9+row*24],[250,9+row*24]]}))};
}
export function coupledScene(count=10){return {version:1,units:'pt',canvas:{widthPt:220,heightPt:100},elements:Array.from({length:count},(_,i)=>({id:'label'+i,kind:'text',x:0,y:0,widthPt:18,heightPt:8,fontSizePt:8,candidates:Array.from({length:count},(_,j)=>({x:j*21,y:10}))}))};}
const percentile=(values,q)=>values.slice().sort((a,b)=>a-b)[Math.min(values.length-1,Math.floor(values.length*q))];
export function benchmark(){const results=[];for(const [name,scene]of [['24 chart labels',chartScene()],['10 mutually exclusive labels',coupledScene()],['irregular widths in extra slots',{...coupledScene(10),canvas:{widthPt:440,heightPt:100},elements:coupledScene(10).elements.map((e,i)=>({...e,widthPt:18+i%3*5,candidates:Array.from({length:24},(_,j)=>({x:j*17,y:10}))}))}]]){
 solveLayout(scene);const runs=Array.from({length:30},()=>solveLayout(scene,{budgetMs:50}));const times=runs.map(r=>r.search.elapsedMs);results.push({name,runs:runs.length,medianMs:percentile(times,.5),p95Ms:percentile(times,.95),maxMs:Math.max(...times),solved:runs.filter(r=>r.status==='solved').length,fullySearched:runs.filter(r=>r.optimalWithinDomains).length});}
 const batch=solveBatch({figures:Array.from({length:10},(_,i)=>({id:'synthetic-'+i,scene:chartScene()}))});return {fixtures:'Synthetic measured geometry; no real-font or native-output claim',measurementTimeIncluded:false,nativeTimeIncluded:false,results,batch:{status:batch.status,figures:batch.results.length,elapsedMs:batch.elapsedMs}};
}
if(process.argv[1]?.endsWith('layout-benchmark.mjs')){const report=benchmark();if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));}
