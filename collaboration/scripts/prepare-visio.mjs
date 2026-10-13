import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {convertOffice} from '../../lib/convert.mjs';
import {parseArgs,readMachine,readRelease,verifyFiles,repoRoot,sha256} from './common.mjs';

// Explicit candidate preparation only; never publishes a plan or alters production records.
const {configFile,rest}=parseArgs(process.argv.slice(2));
const [jobArg,sourceArg,pageArg]=rest;
if(rest.length!==3||!/^\d+$/.test(pageArg)||Number(pageArg)<1)throw Error('Usage: prepare-visio.mjs --config machine.json JOB SOURCE PAGE');
const machine=readMachine(configFile);verifyFiles(machine.runtimePath,readRelease().release.files);
const job=path.resolve(machine.workRoot||machine.workspaceRoot,jobArg),source=path.resolve(machine.workspaceRoot,sourceArg);
const start=performance.now(),converted=convertOffice(job,source,{visioSvg:{page:Number(pageArg)}});
const script=path.join(repoRoot,'scripts/prepare_visio_svg.py'),input=converted.outputs[0].path;
const key=sha256(readFileSync(input))+ '-' +sha256(readFileSync(script)).slice(0,16);
const dir=path.join(job,'svg-preparation',key);mkdirSync(dir,{recursive:true});
const output=path.join(dir,'candidate.svg'),report=path.join(dir,'report.json');
let cached=false;
if(existsSync(report)&&existsSync(output)){
 const old=JSON.parse(readFileSync(report,'utf8'));
 cached=old.sourceHash===sha256(readFileSync(input))&&old.outputHash===sha256(readFileSync(output));
}
if(!cached)execFileSync(machine.python,['-X','utf8',script,input,output,report],{windowsHide:true,stdio:'pipe'});
const result={...JSON.parse(readFileSync(report,'utf8')),sourceDocument:source,page:Number(pageArg),conversionCached:converted.cached===true,preparationCached:cached,durationMs:performance.now()-start,nextStep:'Inspect imported text and graphics on a copy; candidate is not publication approval.'};
writeFileSync(path.join(job,'visio-preparation.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify(result,null,2));
