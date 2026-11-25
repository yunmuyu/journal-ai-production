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
  console.log('journal configure --python EXE --fonts PROFILE --data DIRECTORY --config FILE\njournal start --config FILE\njournal produce --input DIR [--output DIR] [--job job.json]\njournal produce --config FILE --request JSON\njournal inventory --input DIR --expected JSON\njournal status --config FILE\njournal doctor [--config FILE]\njournal package --config FILE --request JSON (optional current-delivery snapshot)\njournal capacity --config FILE --spec JSON --source-root DIRECTORY');
 }else if(command==='inventory'){
  const {inspectFigureInventory}=await import('./scripts/figure-inventory.mjs');
  const articles=JSON.parse(fs.readFileSync(required('expected'),'utf8').replace(/^\uFEFF/,''));
  const report=inspectFigureInventory(required('input'),articles);
  console.log(JSON.stringify(report,null,2));
  if(!report.complete)process.exitCode=1;
 }else if(command==='produce'&&args.includes('--input')){
  const codexPython=process.env.USERPROFILE?path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'):undefined;
  const python=process.env.JFW_PYTHON||(codexPython&&fs.existsSync(codexPython)?codexPython:'python3');
  const parameters=['-m','headless','--input',required('input')];
  if(option('output'))parameters.push('--output',required('output'));
  if(option('job'))parameters.push('--job',required('job'));
  const child=spawn(python,parameters,{stdio:'inherit',windowsHide:true,cwd:path.join(root,'portable-production'),env:{...process.env,PYTHONPATH:path.join(root,'portable-production'),PYTHONUTF8:'1'}});
  await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',code=>{process.exitCode=code??1;resolve();});});
 }else if(command==='doctor'&&!args.includes('--config')){
  const {loadJournalRules}=await import('./lib/journal-rules.mjs');
  const rules=loadJournalRules();
  console.log(JSON.stringify({status:'rules-ready',workbenchRequired:false,margin_pt:rules.normative.margin_pt,scale_floor_pt:rules.normative.scale_floor_pt,font_roles:rules.normative.font_roles,routes:['raster-only','screenshot-chart','vector-diagram']}));
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
   if(command==='doctor'){
    const {loadJournalRules}=await import('./lib/journal-rules.mjs');
    const rules=loadJournalRules();
    const fontFile=config.fontProfile||config.fonts;
    console.log(JSON.stringify({status:'ready',engine:runtime,workbenchRoot:config.workbenchRoot,wordRoot:config.wordRoot,workbenchRequired:false,rules:{margin_pt:rules.normative.margin_pt,scale_floor_pt:rules.normative.scale_floor_pt,font_roles:rules.normative.font_roles},fontProfile:fontFile&&fs.existsSync(fontFile)? 'present':'missing',routes:['raster-only','screenshot-chart','vector-diagram','adobe-merge']}));
   }
   else if(command==='start'){process.env.JFW_MACHINE_CONFIG=configPath;await import('./workbench/server.mjs');}
   else if(command==='capacity')await run('workbench/run-public-pdf.mjs',[config.python,'capacity',required('spec'),'--profile',config.fontProfile,'--source-root',required('source-root'),...(config.cacheRoot?['--cache',config.cacheRoot]:[])]);
   else if(command==='produce')await run('workbench/production-runner.mjs',[configPath,required('request')]);
   else throw Error('unknown command: '+command);
  }
 }
}catch(error){console.error(error.message);process.exitCode=1;}
