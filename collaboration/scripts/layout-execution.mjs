import fs from 'node:fs';
import {createHash} from 'node:crypto';
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
export function buildMoveRequest(input,solution){
 if(solution.status!=='solved'||solution.inputHash!==hash(input))throw Error('Solution does not bind to this exact input');
 const binding=input.sourceBinding;
 if(!binding?.sourcePath||!(/^[a-f0-9]{64}$/.test(binding.sourceSha256||''))||!Array.isArray(binding.items)||!Array.isArray(binding.canvasOrigin)||binding.canvasOrigin.length!==2||!binding.canvasOrigin.every(Number.isFinite))throw Error('Verified source binding required');
 const actualHash=createHash('sha256').update(fs.readFileSync(binding.sourcePath)).digest('hex');if(actualHash!==binding.sourceSha256)throw Error('Source file fingerprint changed');
 function identity(b){if(b.name)return 'name:'+b.name;if(['textFrames','pathItems','groupItems','rasterItems','placedItems'].includes(b.collection)&&Number.isInteger(b.index)&&b.index>=0&&Number.isInteger(binding.collectionCounts?.[b.collection])&&binding.collectionCounts[b.collection]>b.index)return b.collection+':'+b.index;throw Error('Unique source name or indexed collection with verified count required');}
 const names=new Set(),mapped=new Map();
 for(const b of binding.items){const key=identity(b);if(!b.id||mapped.has(b.id)||names.has(key)||!Array.isArray(b.bounds)||b.bounds.length!==4||!b.bounds.every(Number.isFinite))throw Error('Unique source object and measured bounds required');names.add(key);mapped.set(b.id,b);}
 const items=solution.placements.map(p=>{
  const b=mapped.get(p.id);if(!b)throw Error('Missing source object binding: '+p.id);
  if(b.inkBounds&&(!Array.isArray(b.inkBounds)||b.inkBounds.length!==4||!b.inkBounds.every(Number.isFinite)))throw Error('Measured ink binding invalid');
  const original=input.elements.find(e=>e.id===p.id);if(original.kind==='text'&&(!b.fontName||!Number.isFinite(b.fontSizePt)||Math.abs(b.fontSizePt-original.fontSizePt)>.00001||original.fontName&&original.fontName!==b.fontName))throw Error('Source font does not match measured scene: '+p.id);const reference=b.inkBounds||b.bounds;
  const expected={x:reference[0]-binding.canvasOrigin[0],y:binding.canvasOrigin[1]-reference[1],widthPt:reference[2]-reference[0],heightPt:reference[1]-reference[3]};
  if(Object.keys(expected).some(k=>Math.abs(expected[k]-original[k])>.03))throw Error('Measured scene does not match source object: '+p.id);
  return {...b,dx:p.dx,dy:p.dy,expectedFinalBounds:b.bounds.map((v,i)=>v+(i%2?-p.dy:p.dx))};
 });
 const connections=(solution.routes||[]).map(route=>{
  const b=binding.connections?.find(x=>x.id===route.id);if(!b?.parts?.length)throw Error('Connection source bindings required for rerouting: '+route.id);
  for(const p of b.parts)if(names.has(identity(p))||!p.bounds?.every(Number.isFinite)||p.bounds.length!==4)throw Error('Connection object binding invalid');else names.add(identity(p));
  return {id:route.id,parts:b.parts,both:route.both,points:route.points.map(([x,y])=>[binding.canvasOrigin[0]+x,binding.canvasOrigin[1]-y])};
 });
 return {version:1,kind:'move',verifiedSourceSha256:actualHash,sourcePath:binding.sourcePath,sourceSha256:binding.sourceSha256,solutionInputHash:solution.inputHash,items,connections,dependencies:binding.dependencies||[],collectionCounts:binding.collectionCounts||{},expectedCanvas:{widthPt:input.canvas.widthPt,heightPt:input.canvas.heightPt},mustValidateBeforeMutation:true};
}
