import {execFileSync} from 'node:child_process';
import {existsSync,mkdirSync,openSync,closeSync,unlinkSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readJson,writeJson} from './core.mjs';
import {processAlive} from './recovery.mjs';
import {withAdobeSession,ensureAdobeNotice,markAdobeUncertain} from './desktop-notice.mjs';
export function adobeHealth(root,{restartEmpty=false}={}){
 root=path.resolve(root);const directory=path.join(root,'diagnostics');mkdirSync(directory,{recursive:true});
 const lock=path.join(tmpdir(),'journal-figure-adobe.lock');let fd,report;
 const save=value=>{const file=path.join(directory,'adobe-health-'+Date.now()+'.json');writeJson(file,value);return {...value,report:file};};
 if(existsSync(lock)){
  let lease;try{lease=readJson(lock);}catch{return save({status:'busy',reason:'Unrecognized Adobe lease; inspect it without deleting'});}
  if(processAlive(lease.pid)||restartEmpty)return save({status:'busy',reason:processAlive(lease.pid)?'Adobe lease owner is live':'Recover the stale lease before restarting',lease});
 }
 try{
  if(restartEmpty){fd=openSync(lock,'wx');writeFileSync(fd,JSON.stringify({pid:process.pid,application:'illustrator',request:path.join(directory,'restart-empty'),startedAt:new Date().toISOString()}));}
  const work=()=>{
   if(restartEmpty)ensureAdobeNotice();
   const script=fileURLToPath(new URL('../adobe/health.ps1',import.meta.url));
   const args=['-NoProfile','-ExecutionPolicy','Bypass','-File',script];if(restartEmpty)args.push('-RestartEmpty');
   try{
    const stdout=execFileSync('powershell.exe',args,{encoding:'utf8',windowsHide:true,timeout:restartEmpty?45000:15000});
    const value=JSON.parse(stdout.replace(/^﻿/,''));
    if(restartEmpty&&!['healthy','restart_refused','not_running','busy','script_fault'].includes(value.status))markAdobeUncertain();
    return value;
   }catch(error){if(restartEmpty)markAdobeUncertain();throw error;}
  };
  report=restartEmpty?withAdobeSession(['Illustrator'],work):work();
 }catch(error){report={status:error.code==='ETIMEDOUT'?'probe_timeout':'diagnostic_error',message:error.message};}
 finally{if(fd!==undefined){closeSync(fd);if(['healthy','restart_refused','not_running','busy','script_fault'].includes(report?.status))unlinkSync(lock);}}
 return save(report);
}
