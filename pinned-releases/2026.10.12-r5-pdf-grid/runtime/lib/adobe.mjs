import{executionUncertain}from'./adobe-state.mjs';
import{withAdobeSession,markAdobeUncertain,ensureAdobeNotice}from'./desktop-notice.mjs';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, openSync, closeSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { readJson, writeJson } from './core.mjs';
export const packageRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export function adobe(application,request,directory){if(application==='illustrator'&&process.env.JFW_KEEP_ILLUSTRATOR_DOCUMENTS==='1')request={...request,keepDocumentOpen:true};return withAdobeSession([application],()=>invokeAdobe(application,request,directory));}
function invokeAdobe(application,request,directory){
 let timeoutMs=request.mode==='aggregate'?360000:180000;const configuredTimeout=process.env.JFW_ADOBE_TIMEOUT_MS;if(configuredTimeout!==undefined){const parsedTimeout=Number(configuredTimeout);if(!/^[1-9]\d*$/.test(configuredTimeout)||!Number.isSafeInteger(parsedTimeout))throw Error("JFW_ADOBE_TIMEOUT_MS must be a finite positive integer");timeoutMs=parsedTimeout;}
 mkdirSync(directory,{recursive:true});const lock=path.join(tmpdir(),'journal-figure-adobe.lock');let fd;
 try{fd=openSync(lock,'wx');}catch(error){if(error.code==='EEXIST')throw Error('Adobe is busy or previous run needs recovery: '+lock);throw error;}
 ensureAdobeNotice();
 const req=path.join(directory,'request.json'),result=path.join(directory,'result.json');writeJson(req,request);writeFileSync(fd,JSON.stringify({pid:process.pid,application,request:req,result,startedAt:new Date().toISOString()}));let uncertain=false;
 try{
  if(existsSync(result))unlinkSync(result);
  execFileSync('cscript.exe',['//nologo','//E:JScript',path.join(packageRoot,'adobe/invoke.js'),application,path.join(packageRoot,'adobe',application+'.jsx'),req,result],{encoding:'utf8',timeout:timeoutMs,windowsHide:true,stdio:'pipe'});
  const value=readJson(result);if(!value.ok)throw Error(value.error);return value;
 }catch(error){let bridge;try{bridge=readJson(result+'.bridge.json');}catch{}uncertain=executionUncertain(error,bridge,existsSync(result));if(existsSync(result)){const failure=readJson(result);if(!failure.ok)throw Error(failure.error);}throw error;}finally{closeSync(fd);if(!uncertain)unlinkSync(lock);else markAdobeUncertain();}
}
