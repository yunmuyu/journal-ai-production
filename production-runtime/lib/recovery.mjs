import path from 'node:path';
import {tmpdir} from 'node:os';
import {existsSync,readFileSync,unlinkSync} from 'node:fs';
import {readJson,writeJson,logEvent} from './core.mjs';
export function processAlive(pid){if(!Number.isInteger(pid)||pid<=0)return false;try{process.kill(pid,0);return true;}catch(e){return e.code!=='ESRCH';}}
export function recoverJob(root,{verifiedIdle=false,adobeLock=path.join(tmpdir(),'journal-figure-adobe.lock')}={}){
 root=path.resolve(root);if(!verifiedIdle)throw Error('Inspect Adobe/Office processes and current documents first; then use --verified-idle. Observation timeout alone is not evidence.');
 const locks=[path.join(root,'.lock')],adobe=adobeLock;if(existsSync(adobe)){let lease;try{lease=readJson(adobe);}catch{throw Error('Unidentified global Adobe lease: inspect manually');}if(lease.request?.startsWith(root+path.sep))locks.push(adobe);else throw Error('Another job owns the Adobe lease');}
 const removed=[];for(const lock of locks){if(!existsSync(lock))continue;const text=readFileSync(lock,'utf8').trim();let lease={};if(text){try{lease=JSON.parse(text);}catch{throw Error('Unrecognized lock format');}}if(processAlive(lease.pid))throw Error('Task process is still live: '+lease.pid);unlinkSync(lock);removed.push(lock);}
 const file=path.join(root,'job.json');if(existsSync(file)){const state=readJson(file);for(const f of state.figures)if(f.status==='rendering')Object.assign(f,{status:'interrupted',reason:'Execution was interrupted; resume with the same source and plan after inspecting artifacts'});writeJson(file,state);}
 logEvent(root,{event:'recovery',removed,verifiedIdle:true});return {removed,sourceFilesDeleted:false};
}
