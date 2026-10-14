import fs from 'node:fs';
import {createHash} from 'node:crypto';
const digest=value=>createHash('sha256').update(value).digest('hex');

// Bind approval to the active output set, including numbering and file content.
// Legacy approvals remain readable until explicitly reviewed again.
export function inspectAcceptance(id,figure,{resolve=p=>p,hash=file=>digest(fs.readFileSync(file))}={}){
 const parts=figure?.subfigures?.length?figure.subfigures:[figure];
 const outputs=[];
 for(const [index,part] of parts.entries()){
  const file=typeof part?.output==='string'?resolve(part.output):null;
  try{
   if(!file||!fs.statSync(file).isFile())return {token:null,error:'当前交付文件不完整，不能验收通过'};
   const sha256=hash(file);
   if(part.outputHash&&part.outputHash.toLowerCase()!==sha256)return {token:null,error:'成品已发生变化，请重新核对后验收'};
   outputs.push({number:String(part.number??index+1),path:part.output.split(String.fromCharCode(92)).join('/'),sha256});
  }catch{return {token:null,error:'当前交付文件不可读取，不能验收通过'};}
 }
 return {token:digest(JSON.stringify({version:1,id,outputs})),outputs};
}
export function acceptanceMatches(figure,snapshot){
 return !figure?.userAcceptance?.artifactToken||figure.userAcceptance.artifactToken===snapshot.token;
}
