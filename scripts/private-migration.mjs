// Private data transport only. Production still uses workbench/production-runner.mjs.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const absolute=p=>process.platform==='win32'?/^[a-z]:[/\\]/i.test(p):path.isAbsolute(p);
const secretKey=key=>/^(reviewerToken|workerToken|token|apiKey|api_key|clientSecret|password|authorization)$/i.test(key);
function stripSecrets(value){
 if(Array.isArray(value))return value.map(stripSecrets);
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,secretKey(k)?null:stripSecrets(v)]));
 return value;
}
function references(value,found=[]){
 if(typeof value==='string')found.push(value);
 else if(Array.isArray(value))for(const v of value)references(v,found);
 else if(value&&typeof value==='object')for(const [k,v] of Object.entries(value)){found.push(k);references(v,found);}
 return found;
}
function walk(root){
 const result=[];
 for(const entry of fs.readdirSync(root,{withFileTypes:true})){
  if(entry.isSymbolicLink())continue;
  const p=path.join(root,entry.name);
  if(entry.isDirectory())result.push(...walk(p));else result.push(p);
 }
 return result;
}
export function exportPrivate(plan,output){
 if(fs.existsSync(output))throw Error('migration_output_exists');
 const queue=[...plan.seeds],excluded=[],missing=[],records=[],seen=new Set(),blobs=new Set();
 // Output files alone cannot restore the current revision. The review registry
 // decides which candidate is current and must travel with feedback/acceptance.
 const acceptanceSeed=plan.seeds.find(p=>path.basename(p)==='acceptance.json');
 const stateRoot=plan.workbenchRoot??(acceptanceSeed?path.dirname(acceptanceSeed):undefined);
 if(stateRoot&&fs.existsSync(path.join(stateRoot,'feedback.json'))){
  for(const name of ['review-triage/reviews.json','archive-intake/batches.json','archive-intake/related-cache.json','workbuddy-jobs/routine-trials.json']){
   const registry=path.join(stateRoot,name);if(fs.existsSync(registry))queue.push(registry);
  }
  for(const name of ['review-triage','revision-jobs','workbuddy-jobs']){
   const directory=path.join(stateRoot,name);
   if(fs.existsSync(directory))queue.push(...walk(directory).filter(p=>path.basename(p)==='published.json'));
  }
 }
 const skip=p=>(plan.excludePrefixes||[]).some(prefix=>{
  const relative=path.relative(path.resolve(prefix),path.resolve(p));return relative===''||(!relative.startsWith('..')&&!path.isAbsolute(relative));
 });
 for(const root of plan.trees||[])queue.push(...walk(root));
 fs.mkdirSync(path.join(output,'blobs'),{recursive:true});
 for(let i=0;i<queue.length;i++){
  const p=path.resolve(queue[i]);if(seen.has(p))continue;seen.add(p);
  if(skip(p)||/\.(ttf|ttc|otf|exe|dll|pyc)$/i.test(p)){excluded.push(p);continue;}
  if(!fs.existsSync(p)){missing.push(p);continue;}
  if(!fs.statSync(p).isFile())continue;
  let bytes=fs.readFileSync(p),kind='original';
  if(/(?:config|machine)\.json$/i.test(p)){
   bytes=Buffer.from(JSON.stringify(stripSecrets(JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/,''))),null,2)+'\n');kind='local-config';
  }
  const sha256=digest(bytes);
  if(!blobs.has(sha256)){fs.writeFileSync(path.join(output,'blobs',sha256),bytes,{flag:'wx'});blobs.add(sha256);}
  const originalPath=plan.pathOverrides?.[p]??p;
  if(!absolute(originalPath))throw Error('migration_override_must_be_absolute');
  records.push({originalPath,sha256,bytes:bytes.length,kind});
  if(/\.(json|js|mjs|html)$/i.test(p)&&bytes.length<32*1024*1024){
   let refs=[];
   if(p.endsWith('.json'))refs=references(JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/,'')));
   else refs=[...bytes.toString('utf8').matchAll(/["'`]((?:file:\/\/\/|[a-z]:[/\\])[^"'`\r\n]+)["'`]/gi)].map(m=>m[1]);
   for(let ref of refs){
    if(ref.startsWith('file:///')){try{ref=fileURLToPath(ref);}catch{continue;}}
    if(absolute(ref))queue.push(ref);
    else if(/[./\\]/.test(ref)&&ref.length<1024){const local=path.resolve(path.dirname(p),ref);if(fs.existsSync(local)&&fs.statSync(local).isFile())queue.push(local);}
   }
  }
 }
 const manifest={version:1,createdAt:new Date().toISOString(),files:records,excluded,missing,
  notice:'PRIVATE: manuscripts, review notes and current artwork. Never upload this folder to public GitHub.',
  originalPathsRequired:true};
 fs.writeFileSync(path.join(output,'MIGRATION-MANIFEST.json'),JSON.stringify(manifest,null,2)+'\n');
 return {files:records.length,uniqueBlobs:blobs.size,bytes:[...blobs].reduce((n,h)=>n+fs.statSync(path.join(output,'blobs',h)).size,0),excluded:excluded.length,missing:missing.length};
}
export function verifyPrivate(root){
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'MIGRATION-MANIFEST.json'),'utf8'));
 if(manifest.version!==1||!Array.isArray(manifest.files))throw Error('migration_manifest_invalid');
 const paths=new Set();
 for(const item of manifest.files){
  if(!/^[a-f0-9]{64}$/.test(item.sha256)||!absolute(item.originalPath)||paths.has(path.resolve(item.originalPath)))throw Error('migration_record_invalid');
  paths.add(path.resolve(item.originalPath));
  const bytes=fs.readFileSync(path.join(root,'blobs',item.sha256));
  if(bytes.length!==item.bytes||digest(bytes)!==item.sha256)throw Error('migration_hash_mismatch: '+item.originalPath);
 }
 return manifest;
}
export function restorePrivate(root){
 const manifest=verifyPrivate(root);
 // Preflight every destination before any write. Never overwrite a different file.
 for(const item of manifest.files){
  if(fs.existsSync(item.originalPath)&&digest(fs.readFileSync(item.originalPath))!==item.sha256)throw Error('migration_destination_conflict: '+item.originalPath);
 }
 let restored=0;
 for(const item of manifest.files){
  if(fs.existsSync(item.originalPath))continue;
  fs.mkdirSync(path.dirname(item.originalPath),{recursive:true});
  fs.copyFileSync(path.join(root,'blobs',item.sha256),item.originalPath,fs.constants.COPYFILE_EXCL);restored++;
 }
 return {restored,verified:manifest.files.length,credentials:'Local tokens removed; configure fresh tokens before starting workbench.'};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  const [command,input,output]=process.argv.slice(2);
  if(command==='export')console.log(JSON.stringify(exportPrivate(JSON.parse(fs.readFileSync(input,'utf8').replace(/^\uFEFF/,'')),output)));
  else if(command==='verify'){const m=verifyPrivate(input);console.log(JSON.stringify({verified:m.files.length,missingReferences:m.missing.length}));}
  else if(command==='restore-original-paths')console.log(JSON.stringify(restorePrivate(input)));
  else throw Error('Usage: private-migration.mjs export PLAN OUTPUT | verify FOLDER | restore-original-paths FOLDER');
 }catch(error){console.error(error.message);process.exitCode=1;}
}
