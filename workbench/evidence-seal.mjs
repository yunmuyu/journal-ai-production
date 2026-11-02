// Accidental-edit protection, not a security boundary against the same OS user.
import fs from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';

export const evidenceRef=p=>({path:path.resolve(p),sha256:createHash('sha256').update(fs.readFileSync(p)).digest('hex')});
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
function inside(root,p){
 const relative=path.relative(fs.realpathSync(root),fs.realpathSync(p));
 if(!relative||relative.startsWith('..')||path.isAbsolute(relative))throw Error('封存只能保护当前attempt内部文件');
}
export function checkEvidence(row){
 if(!row||evidenceRef(row.path).sha256!==row.sha256)throw Error('封存证据已变化，需要新attempt: '+row?.path);
 return row;
}
export function writeSealedJson(p,value){
 fs.writeFileSync(p,JSON.stringify(value,null,2)+'\n',{encoding:'utf8',flag:'wx'});
 fs.chmodSync(p,0o444);return evidenceRef(p);
}
export function snapshotEvidence(directory,name,source){
 const row=typeof source==='string'?evidenceRef(source):checkEvidence(source),target=path.join(directory,name);
 fs.copyFileSync(row.path,target,fs.constants.COPYFILE_EXCL);
 if(evidenceRef(target).sha256!==row.sha256)throw Error('证据快照字节不一致');
 fs.chmodSync(target,0o444);return evidenceRef(target);
}
function files(root){return fs.readdirSync(root,{withFileTypes:true}).flatMap(e=>{
 const p=path.join(root,e.name);
 if(e.isSymbolicLink())throw Error('封存目录不能包含链接');
 return e.isDirectory()?files(p):[p];
});}
export function sealEvidence(attempt,runDir,workspace,externalRefs=[]){
 const paths=[...files(runDir),...files(workspace)];
 for(const p of paths){inside(attempt,p);fs.chmodSync(p,0o444);}
 const manifest={version:1,files:paths.map(evidenceRef),external:externalRefs.map(checkEvidence),
  limitation:'只读与哈希防误改；同一系统用户仍可主动解除只读。不代表视觉通过。'};
 return writeSealedJson(path.join(runDir,'seal.json'),manifest);
}
export function verifyEvidenceSeal(runDir){
 const seal=path.join(runDir,'seal.json');
 if(!fs.existsSync(seal))throw Error('本次运行未完整封存，需要新attempt；不得覆盖或补写旧记录');
 const manifest=read(seal);
 if(manifest.version!==1||!Array.isArray(manifest.files)||!manifest.files.length||!Array.isArray(manifest.external))throw Error('封存清单无效，需要新attempt');
 for(const row of [...manifest.files,...manifest.external])checkEvidence(row);
 return evidenceRef(seal);
}
export function appendSelfCheck(attempt,note){
 const runDir=path.join(attempt,'raster-job'),seal=verifyEvidenceSeal(runDir);
 const observations=note?.observations;
 if(!observations||['source_content','readability','grayscale_semantics'].some(k=>typeof observations[k]!=='string'||!observations[k].trim()))throw Error('补看图笔记需要source_content/readability/grayscale_semantics三项实际observations');
 const directory=path.join(attempt,'self-checks');
 fs.mkdirSync(directory,{recursive:true});inside(attempt,directory);
 const result=read(path.join(runDir,'result.json')),contract=read(result.quality.contract.path);
 const candidatePath=path.join(contract.workspace,'.task-quality','candidate.json'),candidate=read(candidatePath),id=randomUUID();
 const selfCheck=writeSealedJson(path.join(directory,id+'.json'),{producer:contract.producer,
  candidate_sha256:evidenceRef(candidatePath).sha256,observations,
  evidence:[...new Set([contract.source.sha256,...result.outputs.map(o=>o.sha256),...candidate.previews.map(p=>p.sha256)])]});
 const submission=writeSealedJson(path.join(directory,id+'.result.json'),{...result,selfCheck});
 return {selfCheck,result:submission,seal,status:'producer_self_check_recorded',
  limitation:'补充制作人看图记录，不修改已封存audit，不等于独立审阅或用户终审。'};
}
