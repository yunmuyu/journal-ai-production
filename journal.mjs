#!/usr/bin/env node
// One user-facing entry. Existing production-runner remains the sole executor.
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {configureLocal} from './scripts/configure-local.mjs';
import {fixedProductionRuntime} from './workbench/fixed-production-runtime.mjs';
import {packageCurrentDelivery} from './scripts/package-current-delivery.mjs';

const root=fileURLToPath(new URL('.',import.meta.url));
const [command,...args]=process.argv.slice(2);
const option=name=>{const index=args.indexOf('--'+name);return index<0?undefined:args[index+1];};
const required=name=>{const value=option(name);if(!value||value.startsWith('--'))throw Error('missing --'+name);return path.resolve(value);};
async function run(script,parameters=[],env={}){
 const child=spawn(process.execPath,[path.join(root,script),...parameters],{stdio:'inherit',windowsHide:true,env:{...process.env,...env}});
 await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',(code,signal)=>{if(signal)reject(Error('child terminated: '+signal));else{process.exitCode=code??1;resolve();}});});
}
try{
 if(command==='help'||!command){
  console.log('journal configure --python EXE --fonts PROFILE --data DIRECTORY --config FILE\njournal start --config FILE\njournal produce --config FILE --request JSON\njournal status --config FILE\njournal doctor --config FILE\njournal package --config FILE --request JSON (optional current-delivery snapshot)\njournal capacity --config FILE --spec JSON --source-root DIRECTORY');
 }else if(command==='configure'){
  console.log(JSON.stringify(configureLocal({python:required('python'),fontProfile:required('fonts'),workbenchRoot:required('data'),output:required('config'),refresh:args.includes('--refresh')})));
 }else{
  const configPath=required('config'),config=JSON.parse(fs.readFileSync(configPath,'utf8').replace(/^\uFEFF/,''));
  process.env.JFW_PYTHON=config.python;
  if(command==='package'){
   const request=JSON.parse(fs.readFileSync(required('request'),'utf8').replace(/^\uFEFF/,''));
   console.log(JSON.stringify(packageCurrentDelivery({...request,python:config.python})));
  }else if(command==='status'){
   const response=await fetch(new URL('/data',config.origin),{signal:AbortSignal.timeout(30000)});
   if(!response.ok)throw Error('workbench_http_'+response.status);
   const data=await response.json();console.log(JSON.stringify({articles:data.articles.length,figures:data.rows.length,statuses:data.rows.reduce((counts,row)=>{counts[row.status]=(counts[row.status]??0)+1;return counts;},{})}));
  }else{
   const runtime=await fixedProductionRuntime(config);
   if(command==='doctor')console.log(JSON.stringify({status:'ready',engine:runtime,workbenchRoot:config.workbenchRoot,wordRoot:config.wordRoot}));
   else if(command==='start'){process.env.JFW_MACHINE_CONFIG=configPath;await import('./workbench/server.mjs');}
   else if(command==='capacity')await run('workbench/run-public-pdf.mjs',[config.python,'capacity',required('spec'),'--profile',config.fontProfile,'--source-root',required('source-root'),...(config.cacheRoot?['--cache',config.cacheRoot]:[])]);
   else if(command==='produce')await run('workbench/production-runner.mjs',[configPath,required('request')]);
   else throw Error('unknown command: '+command);
  }
 }
}catch(error){console.error(error.message);process.exitCode=1;}
