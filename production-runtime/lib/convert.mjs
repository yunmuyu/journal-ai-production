import path from 'node:path';
import {mkdirSync,copyFileSync,existsSync,openSync,closeSync,unlinkSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {packageRoot} from './adobe.mjs';
import {fileHash,sha256,readJson,writeJson,logEvent} from './core.mjs';
import {createJob} from './jobs.mjs';
export function convertOffice(root,source){
 root=path.resolve(root);source=path.resolve(source);createJob(root);
 const ext=path.extname(source).toLowerCase();if(!/^\.(docx?|ppt[xm]?|vsd[xm]?|xls[xmb]?|emf|wmf)$/.test(ext))throw Error('Unsupported Office source');
 const hash=fileHash(source),driver=path.join(packageRoot,'scripts/convert-office.js'),key=sha256(hash+fileHash(driver));const dir=path.join(root,'conversions',key),result=path.join(dir,'result.json');mkdirSync(dir,{recursive:true});
 if(existsSync(result)){const old=readJson(result);if(old.ok&&old.outputs.every(o=>o.sha256&&existsSync(o.path)&&fileHash(o.path)===o.sha256))return {cached:true,...old};}
 const lock=path.join(dir,'.lock');let fd;try{fd=openSync(lock,'wx');}catch{throw Error('Conversion is active or needs recovery: '+lock);}
 let uncertain=false;
 try{
  const input=path.join(dir,'input'+ext);copyFileSync(source,input);writeJson(path.join(dir,'request.json'),{input,directory:dir,result});
  execFileSync('cscript.exe',['//nologo','//E:JScript',driver,path.join(dir,'request.json')],{encoding:'utf8',windowsHide:true,timeout:180000});
  const r=readJson(result);if(!r.ok)throw Error(r.error);for(const o of r.outputs)o.sha256=fileHash(o.path);if(fileHash(source)!==hash)throw Error('Original changed during conversion');Object.assign(r,{source,sourceHash:hash,driverHash:fileHash(driver)});writeJson(result,r);logEvent(root,{event:'converted',source,result,durationMs:r.durationMs});return r;
 }catch(e){uncertain=e.code==='ETIMEDOUT';logEvent(root,{event:'conversion_failed',source,error:e.message,uncertain});throw e;}finally{closeSync(fd);if(!uncertain)unlinkSync(lock);}
}
