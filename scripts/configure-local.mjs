// Bind a freshly installed runtime. Does not start production or grant acceptance.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash,randomBytes} from 'node:crypto';
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const repo=fileURLToPath(new URL('../',import.meta.url));
export function configureLocal({python,fontProfile,workbenchRoot,output,refresh=false}){
 const prior=fs.existsSync(output)?JSON.parse(fs.readFileSync(output,'utf8').replace(/^\uFEFF/,'')):null;
 if(prior&&!refresh)throw Error('local_config_exists; use explicit --refresh to rebind this installation');
 if(prior&&path.resolve(prior.workbenchRoot)!==path.resolve(workbenchRoot))throw Error('refresh_cannot_change_workspace');
 for(const p of [python,fontProfile])if(!fs.existsSync(p))throw Error('runtime_file_missing: '+p);
 const profile=JSON.parse(fs.readFileSync(fontProfile,'utf8').replace(/^\uFEFF/,''));
 for(const face of Object.values(profile.faces||{}))if(!fs.existsSync(face.path))throw Error('font_missing: '+face.path);
 const env={...process.env,PYTHONPATH:path.join(repo,'portable-production','direct-pdf'),PYTHONUTF8:'1'};
 const probe=JSON.parse(execFileSync(python,['-c',
  'import sys,json; assert sys.version_info >= (3,12), "Python >=3.12 required"; import pypdf,pymupdf,pypdfium2,PIL,numpy,cairosvg,shapely; from journal_pdf.fonts import FontRegistry; from journal_pdf.editorial import engine_signature; FontRegistry(sys.argv[1]); print(json.dumps({"signature":engine_signature(),"version":sys.version}))',fontProfile],{env,encoding:'utf8',windowsHide:true,timeout:60000}));
 const credentialsFile=path.join(workbenchRoot,'workbuddy.config.json');
 const rootsFile=path.join(workbenchRoot,'workspace-roots.json');
 let wordRoot=fs.existsSync(rootsFile)?JSON.parse(fs.readFileSync(rootsFile,'utf8')).wordRoot:undefined;
 if(!wordRoot&&fs.existsSync(path.join(workbenchRoot,'server.mjs'))){
  wordRoot=fs.readFileSync(path.join(workbenchRoot,'server.mjs'),'utf8').match(/const wordRoot=.*?\|\|'([^']+)';/)?.[1];
 }
 if(!wordRoot||!fs.existsSync(wordRoot))throw Error('word_root_required: set workspace-roots.json wordRoot');
 const config={...prior,origin:prior?.origin??'http://127.0.0.1:18741',workbenchRoot,wordRoot,credentialsFile,python,fontProfile,
  knownFaultsFile:path.join(workbenchRoot,'production-known-faults.json'),receiptRoot:path.join(workbenchRoot,'production-receipts'),
  caseIndexPath:path.join(workbenchRoot,'figure-cases.json'),runtimeLock:{python:{path:python,sha256:hash(python)},fontProfile:{path:fontProfile,sha256:hash(fontProfile)},engineSignature:probe.signature}};
 if(fs.existsSync(credentialsFile)){
  const local=JSON.parse(fs.readFileSync(credentialsFile,'utf8'));
  local.workerToken||=randomBytes(32).toString('hex');local.reviewerToken||=randomBytes(32).toString('hex');local.qualityPython=python;
  fs.writeFileSync(credentialsFile,JSON.stringify(local,null,2)+'\n');
 }
 fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output+'.tmp',JSON.stringify(config,null,2)+'\n',{flag:'wx'});fs.renameSync(output+'.tmp',output);
 return {config:output,engineSignature:probe.signature,python:probe.version,workbenchConfigured:fs.existsSync(credentialsFile)};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const [python,fontProfile,workbenchRoot,output]=process.argv.slice(2);if(!output)throw Error('Usage: configure-local.mjs PYTHON FONT_PROFILE WORKBENCH_ROOT OUTPUT');console.log(JSON.stringify(configureLocal({python,fontProfile,workbenchRoot,output})));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
