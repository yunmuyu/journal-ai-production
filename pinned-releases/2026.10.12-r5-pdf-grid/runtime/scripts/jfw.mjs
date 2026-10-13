import {adobeHealth} from '../lib/adobe-health.mjs';
import {fit} from '../lib/fit.mjs';
import path from 'node:path';
import { mkdirSync,openSync,closeSync,unlinkSync,writeFileSync } from 'node:fs';
import { recoverJob } from '../lib/recovery.mjs';
import { createJob,addFigure,scanAssets } from '../lib/jobs.mjs';
import { readJson } from '../lib/core.mjs';
import { render,inspect } from '../lib/render.mjs';
import { suggestRoutes } from '../lib/typesafe.mjs';
import { convertSvg } from '../lib/svg.mjs';
import { convertOffice } from '../lib/convert.mjs';
import { ingestDocx,pairReferences } from '../lib/ingest.mjs';
import { recordReview,deliver } from '../lib/review.mjs';
const [command,jobArg,...args]=process.argv.slice(2);
if(!command||!jobArg){console.log('jfw init|scan|add|ingest|pair|convert|suggest|status|doctor|recover|inspect|fit|render|review|deliver JOB [arguments]\nadd JOB metadata.json; render JOB plan.json; review JOB ID pass|review|fail evidence');process.exit(0);}
const job=path.resolve(jobArg);mkdirSync(job,{recursive:true});let fd;
if(command==='doctor'){const report=adobeHealth(job,{restartEmpty:args.includes('--restart-empty')});console.log(JSON.stringify(report,null,2));process.exit(report.status==='healthy'?0:2);}
if(command==='status'){console.log(JSON.stringify(readJson(path.join(job,'job.json')),null,2));process.exit(0);}
if(command==='recover'){try{console.log(JSON.stringify(recoverJob(job,{verifiedIdle:args.includes('--verified-idle')}),null,2));}catch(e){console.error(e.message);process.exitCode=1;}process.exit();}
try{
 fd=openSync(path.join(job,'.lock'),'wx');writeFileSync(fd,JSON.stringify({pid:process.pid,command,startedAt:new Date().toISOString()}));let result;
 switch(command){
 case 'suggest':result=suggestRoutes(job,readJson(args[0]));break;
 case 'convert':result=path.extname(args[0]).toLowerCase()==='.svg'?convertSvg(job,args[0]):convertOffice(job,args[0]);break;
 case 'ingest':result=ingestDocx(job,args[0],args[1]);break;
 case 'pair':result=pairReferences(job,readJson(args[0]));break;
 case 'init':result=createJob(job);break;
 case 'scan':result=scanAssets(job,args[0]);break;
 case 'add':result=addFigure(job,readJson(args[0]));break;
 case 'status':result=readJson(path.join(job,'job.json'));break;
 case 'inspect':result=inspect(job,args[0]);break;
 case 'fit':result=fit(job,args[0]);break;
 case 'render':result=render(job,args[0]);break;
 case 'review':result=recordReview(job,args[0],args[1],args.slice(2).join(' '));break;
 case 'deliver':result=deliver(job,{draft:args.includes('--draft')});break;
 default:throw Error('Unknown command '+command);
 }
 console.log(JSON.stringify(result,null,2));
}catch(error){console.error(error.message);process.exitCode=1;}finally{if(fd!==undefined){closeSync(fd);unlinkSync(path.join(job,'.lock'));}}
