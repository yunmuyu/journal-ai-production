// Transport/lifecycle fixtures only; real artifact inspection is tested by task_quality.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
export const testRef=p=>({path:p,sha256:createHash('sha256').update(fs.readFileSync(p)).digest('hex')});
export function routeFixture(root,{raster=false}={}){
 const file=path.join(root,'route-source');if(!fs.existsSync(file))fs.writeFileSync(file,'source fixture');
 const ref=testRef(file);
 return {version:1,method:raster?'raster-preserve':'editable-pdf',sourceReview:{archive:ref,word:ref,inventory:ref,selected:ref,candidates:[{...ref,kind:raster?'raster':'vector',decision:'selected',reason:'Synthetic source pairing'}],basis:'Synthetic source content reviewed',rasterReason:'Synthetic screenshot content'},requirements:{format:raster?'jpg':'pdf',fontCheck:raster?'none':'editable',widthMm:80}};
}
export function transportQuality(job,result){
 if(result.quality?.contract?.sha256!=='transport-only')throw Error('Missing transport verification fixture');
 return {status:'verified',scope:'transport test double, not artwork verification'};
}
