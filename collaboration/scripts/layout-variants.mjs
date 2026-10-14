import {performance} from 'node:perf_hooks';import {calculateLayout} from './pre-draw-layout.mjs';
const canonical=s=>String(s).replace(/[\r\n]/g,'');
export function prepareVariants(input,{maxVariants=64}={}){
 const choices=[],walk=(n,p)=>{
  if(n.allowReflow===true&&['row','column'].includes(n.kind))choices.push({path:p,values:[n.kind,n.kind==='row'?'column':'row'],type:'direction'});
  if(n.wrapOptions?.length){for(const o of n.wrapOptions)if(canonical(o.text)!==canonical(n.text))throw Error('Wrap option changes scientific text');choices.push({path:p,values:[null,...n.wrapOptions],type:'wrap'});}
  if(n.content)walk(n.content,[...p,'content']);for(let i=0;i<(n.children||[]).length;i++)walk(n.children[i],[...p,'children',i]);
 };walk(input.tree,[]);
 if(input.fontChoices?.length)choices.push({type:'font',values:[{fontSizePt:input.fontSizePt,measurements:input.measurements},...input.fontChoices]});
 const count=choices.reduce((p,c)=>p*c.values.length,1),variants=[];
 function expand(i,current){if(variants.length>=maxVariants)return;if(i===choices.length){variants.push(current);return;}
  for(const value of choices[i].values){const next=structuredClone(current),choice=choices[i];if(choice.type==='font'){next.fontSizePt=value.fontSizePt;next.measurements=structuredClone(value.measurements);}
   else{let n=next.tree;for(const part of choice.path)n=n[part];if(choice.type==='direction')n.kind=value;else if(value){n.text=value.text;next.measurements[n.id]=structuredClone(value.measurement);}}
   expand(i+1,next);if(variants.length>=maxVariants)return;
  }
 }expand(0,structuredClone(input));return {variants,totalCombinations:count,truncated:count>variants.length};
}
export function solveTreeLayout(input,{budgetMs=50,maxVariants=64,clock=()=>performance.now()}={}){
 const start=clock(),prepared=prepareVariants(input,{maxVariants});let best=null,tested=0,timedOut=false;const rejected=[];
 for(let i=0;i<prepared.variants.length;i++){
  if(clock()-start>=budgetMs){timedOut=true;break;}
  const variant=prepared.variants[i],result=calculateLayout(variant);tested++;
  if(result.status!=='ready'){rejected.push({variant:i,status:result.status,issues:result.issues});continue;}
  const score=(8-result.finalFontSizePt)*10000+result.naturalWidthPt*result.naturalHeightPt*.001;
  if(!best||score<best.score)best={variant:i,score,result,fontSizePt:variant.fontSizePt,font:variant.font,measurements:variant.measurements};
 }
 const missing=rejected.filter(r=>r.status==='needs-measurement').length;
 const search={measurementIncomplete:missing,elapsedMs:clock()-start,budgetMs,testedVariants:tested,totalCombinations:prepared.totalCombinations,domainsTruncated:prepared.truncated,timedOut};
 if(!best)return {status:timedOut?'budget-exhausted':missing?'needs-measurement':prepared.truncated?'candidate-domain-exhausted':'infeasible',optimalWithinDomains:!timedOut&&!prepared.truncated&&!missing,search,rejected};
 const r=best.result,s=r.fit.scale,transform=p=>({x:(p.x+r.fit.translatePt[0])*s,y:(p.y+r.fit.translatePt[1])*s,widthPt:p.widthPt*s,heightPt:p.heightPt*s});
 return {status:'solved',kind:'tree',optimalWithinDomains:!timedOut&&!prepared.truncated&&!missing,search,selectedVariant:best.variant,score:best.score,violations:[],layout:r,
  execution:{kind:'draw',canvas:{widthPt:r.fit.finalWidthMm*72/25.4,heightPt:r.fit.finalHeightMm*72/25.4},font:best.font,fontSizePt:best.fontSizePt*s,
   shapes:[...r.nodes,...r.frames.map(f=>({...f,shape:'rectangle',frame:true}))].map(n=>({...n,...transform(n)})),texts:r.texts.map(t=>({...t,...transform(t),expectedInk:{widthPt:t.widthPt*s,heightPt:t.heightPt*s},styles:best.measurements[t.id]?.styles})),connections:r.edges.map(e=>({...e,points:e.points.map(([x,y])=>[(x+r.fit.translatePt[0])*s,(y+r.fit.translatePt[1])*s])})),requiresFinalPdfVerification:true}};
}
