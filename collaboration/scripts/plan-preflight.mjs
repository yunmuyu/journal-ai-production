import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
const {validateTechnical}=createRequire(import.meta.url)('../../production-runtime/flowchart/scripts/technical-schema.cjs');

const PT_PER_MM=72/25.4;

// The installed generator is an external dependency. Refuse to guess its capacity if this contract moves.
function generatorContract(file){
  if(!file)throw Error('Generator file required for rebuild preflight');
  const code=readFileSync(file,'utf8');
  const margin=code.match(/\bMARGIN:\s*(\d+(?:\.\d+)?)/);
  const single=code.match(/\bSINGLE_COLUMN_WIDTH:\s*(\d+(?:\.\d+)?)\s*\*\s*PT_PER_MM/);
  const pt=code.match(/\bPT_PER_MM\s*=\s*(\d+(?:\.\d+)?)/);
  if(!margin||!single||!pt||Math.abs(Number(pt[1])-PT_PER_MM)>0.001||
     !/availableW\s*=\s*ab\[2\]\s*-\s*ab\[0\]\s*-\s*CFG\.MARGIN\s*\*\s*2/.test(code)||
     !/maxW\s*=\s*data\.widthClass\s*===\s*["']double["']\s*\?\s*availableW\s*:\s*Math\.min\(CFG\.SINGLE_COLUMN_WIDTH,\s*availableW\)/.test(code)||
     !/root\.fontSize\s*!==\s*8\s*&&\s*root\.fontSize\s*!==\s*7\s*&&\s*root\.fontSize\s*!==\s*6/.test(code)||
     !/root\.fontSize\s*!==\s*8/.test(code))throw Error('Generator contract changed; inspect its font and width rules before Adobe');
  return {marginPt:Number(margin[1]),singleWidthPt:Number(single[1])*PT_PER_MM};
}

export function preflightPlan(plan,{generatorFile}={}){
  for(const [index,group] of (plan?.textGroups||[]).entries()){
    if(group.rotation!==undefined&&![-90,0,90].includes(group.rotation))throw Error(`textGroups[${index}].rotation must be -90, 0, or 90`);
  }
  if(plan?.route!=='rebuild'||plan.nativeLayout==='parallel-chains')return null;
  const {marginPt,singleWidthPt}=generatorContract(generatorFile);
  if(!plan.graph||typeof plan.graph!=='object'||Array.isArray(plan.graph))throw Error('Rebuild plan requires graph');
  if(![6,7,8].includes(plan.fontSize))throw Error('Generator supports only 6, 7, or 8 pt');
  if(plan.graph.fontSize!==plan.fontSize)throw Error('graph.fontSize must equal plan.fontSize');
  if(plan.graph.kind==='technical'){validateTechnical(plan.graph);if(!Number.isFinite(plan.widthMm)||plan.widthMm<=0)throw Error('widthMm required');return {fontSizePt:plan.fontSize,widthPt:plan.widthMm*PT_PER_MM,marginPt:0.25,contentWidthPt:plan.widthMm*PT_PER_MM-0.5,contentWidthMm:plan.widthMm-0.5/PT_PER_MM};}
  if(plan.graph.treeLayout==='module'&&plan.fontSize!==8)throw Error('module-tree requires fixed 8 pt');
  if(!Array.isArray(plan.graph.nodes)||plan.graph.nodes.length===0){
    if(plan.fontSize!==8)throw Error('Freeform generator uses fixed 8 pt when nodes are empty');
  }
  if(!Number.isFinite(plan.widthMm)||plan.widthMm<=0)throw Error('widthMm must be positive and finite');
  const widthPt=plan.widthMm*PT_PER_MM;
  const availablePt=widthPt-2*marginPt;
  const contentWidthPt=plan.graph.widthClass==='double'?availablePt:Math.min(singleWidthPt,availablePt);
  if(contentWidthPt<=0)throw Error('Generator margins leave no content width');
  return {fontSizePt:plan.fontSize,widthPt,marginPt,contentWidthPt,contentWidthMm:contentWidthPt/PT_PER_MM};
}
