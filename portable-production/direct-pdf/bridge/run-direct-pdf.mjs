// Thin Node adapter: preserves the existing Node workbench, delegates only the
// candidate renderer. No Adobe, no RELEASE.json or production ledger mutations.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
export function runDirectPdf(args,{python='python',moduleRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),onOutput=()=>{}}={}) {
  if(!Array.isArray(args)||args.some(x=>typeof x!=='string')) throw new TypeError('args must be string[]');
  return new Promise((resolve,reject)=>{
    const child=spawn(python,['-m','journal_pdf',...args],{cwd:moduleRoot,shell:false,windowsHide:true,env:{...process.env,PYTHONUTF8:'1'}});
    let stdout='',stderr='';
    child.stdout.on('data',b=>{stdout+=b;onOutput(b.toString(),'stdout');});
    child.stderr.on('data',b=>{stderr+=b;onOutput(b.toString(),'stderr');});
    child.on('error',reject);
    child.on('close',code=>resolve({ok:code===0,code,stdout,stderr,backend:'direct-pdf',productionMutation:false}));
  });
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const result=await runDirectPdf(process.argv.slice(2),{python:process.env.JFW_PYTHON||'python',onOutput:(text,stream)=>process[stream].write(text)});
  process.exitCode=result.code??1;
}
