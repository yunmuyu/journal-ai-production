import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {repoRoot,sha256,verifyFiles} from './common.mjs';
import {execFileSync} from 'node:child_process';
function collectFiles(root,{excludeDirectories=[],excludeFiles=[],tracked}={}){
 const files=[];
 function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){if(entry.name.startsWith('.')||excludeDirectories.includes(entry.name)||entry.name==='node_modules'||entry.name==='__pycache__'||entry.name.endsWith('.pyc'))continue;const file=path.join(dir,entry.name);if(entry.isSymbolicLink())throw Error('Release symlinks forbidden');if(entry.isDirectory())walk(file);else if(!excludeFiles.includes(entry.name)){const relative=path.relative(root,file).split(path.sep).join('/');if(tracked&&!tracked.has(relative))continue;const bytes=fs.readFileSync(file);files.push({path:relative,sha256:sha256(bytes),bytes:bytes.length});}}}
 walk(root);files.sort((a,b)=>a.path.localeCompare(b.path));return files;
}
export function sealRelease({id,status='release-candidate',validation,root=repoRoot}){
 if(!/^[0-9]{4}[.][0-9]{2}[.][0-9]{2}-[a-z0-9-]+$/.test(id)||!validation||typeof validation!=='object')throw Error('Explicit release id and validation evidence required');
 const previous=JSON.parse(fs.readFileSync(path.join(root,'RELEASE.json'))),runtime=path.join(root,'production-runtime'),portable=path.join(root,'portable-production');
 const files=collectFiles(runtime,{excludeDirectories:['examples']});
 const tracked=new Set(execFileSync('git',['-C',portable,'ls-files','-z','--','.'],{encoding:'utf8'}).split('\0').filter(Boolean));
 const portableFiles=collectFiles(portable,{excludeDirectories:['.pytest_cache'],excludeFiles:['config.local.json','fonts.local.json'],tracked});
 if(!portableFiles.length)throw Error('No tracked portable files; stage public release inputs first');
 const manifest={...previous,id,status,supersedes:previous.id===id?previous.supersedes:previous.id,createdAt:new Date().toISOString(),validation,files,portableFiles,skillSha256:sha256(fs.readFileSync(path.join(root,'skill/SKILL.md')))};verifyFiles(runtime,files);verifyFiles(portable,portableFiles);
 const file=path.join(root,'RELEASE.json'),tmp=file+'.stage';fs.writeFileSync(tmp,JSON.stringify(manifest,null,2)+'\n');fs.renameSync(tmp,file);return manifest;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){try{const [id,evidenceFile,status]=process.argv.slice(2);console.log(JSON.stringify(sealRelease({id,validation:JSON.parse(fs.readFileSync(evidenceFile)),...(status?{status}:{})}),null,2));}catch(error){console.error(error.message);process.exitCode=1;}}
