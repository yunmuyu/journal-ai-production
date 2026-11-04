// Prepare a local folder and hand it to the existing archive intake endpoint.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

export async function intakeFolder({folder,origin,editor,month,count,python},send=fetch){
 const url=new URL(origin);
 if(!['localhost','127.0.0.1','[::1]'].includes(url.hostname)||!['http:','https:'].includes(url.protocol)||url.pathname!=='/'||url.search||url.hash)
  throw Error('folder_intake_local_workbench_required');
 if(!editor||!Number.isInteger(month)||month<1||month>12||!Number.isInteger(count)||count<1||!python)
  throw Error('folder_intake_explicit_fields_required');
 const stage=fs.mkdtempSync(path.join(os.tmpdir(),'journal-folder-intake-'));
 const archive=path.join(stage,'generated-source.zip');
 const packer=fileURLToPath(new URL('../scripts/package-manuscript-folder.py',import.meta.url));
 const report=JSON.parse(execFileSync(python,[packer,path.resolve(folder),archive],{encoding:'utf8',windowsHide:true,timeout:60000,env:{...process.env,PYTHONUTF8:'1'}}));
 fs.writeFileSync(path.join(stage,'source-manifest.json'),JSON.stringify(report,null,2));
 const endpoint=new URL('/archive-intake',url);
 for(const [key,value] of Object.entries({filename:'generated-source.zip',editor,month,count}))endpoint.searchParams.set(key,String(value));
 const response=await send(endpoint,{method:'POST',headers:{Origin:url.origin,'Content-Type':'application/zip'},body:fs.readFileSync(archive),signal:AbortSignal.timeout(180000)});
 const result=await response.json();
 if(!response.ok)throw Error('folder_intake_rejected: '+(result.error??response.status));
 return {status:'registered',generatedSourceArchive:true,sourceManifest:path.join(stage,'source-manifest.json'),archiveSha256:report.sha256,result};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const args=JSON.parse(process.argv[2]);console.log(JSON.stringify(await intakeFolder(args)));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
