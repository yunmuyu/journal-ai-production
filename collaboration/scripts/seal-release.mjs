import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {repoRoot,sha256,verifyFiles} from './common.mjs';
export function sealRelease({id,status='release-candidate',validation,root=repoRoot}){
 if(!/^[0-9]{4}[.][0-9]{2}[.][0-9]{2}-[a-z0-9-]+$/.test(id)||!validation||typeof validation!=='object')throw Error('Explicit release id and validation evidence required');
 const previous=JSON.parse(fs.readFileSync(path.join(root,'RELEASE.json'))),runtime=path.join(root,'production-runtime'),files=[];
 function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){if(entry.name.startsWith('.')||['examples','node_modules','__pycache__'].includes(entry.name)||entry.name.endsWith('.pyc'))continue;const file=path.join(dir,entry.name);if(entry.isSymbolicLink())throw Error('Release symlinks forbidden');if(entry.isDirectory())walk(file);else{const bytes=fs.readFileSync(file);files.push({path:path.relative(runtime,file).split(path.sep).join('/'),sha256:sha256(bytes),bytes:bytes.length});}}}walk(runtime);files.sort((a,b)=>a.path.localeCompare(b.path));
 const manifest={...previous,id,status,supersedes:previous.id===id?previous.supersedes:previous.id,createdAt:new Date().toISOString(),validation,files,skillSha256:sha256(fs.readFileSync(path.join(root,'skill/SKILL.md')))};verifyFiles(runtime,files);
 const file=path.join(root,'RELEASE.json'),tmp=file+'.stage';fs.writeFileSync(tmp,JSON.stringify(manifest,null,2)+'\n');fs.renameSync(tmp,file);return manifest;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){try{const [id,evidenceFile,status]=process.argv.slice(2);console.log(JSON.stringify(sealRelease({id,validation:JSON.parse(fs.readFileSync(evidenceFile)),...(status?{status}:{})}),null,2));}catch(error){console.error(error.message);process.exitCode=1;}}
