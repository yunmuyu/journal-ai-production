// Bind a freshly installed runtime. Does not start production or grant acceptance.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash,randomBytes} from 'node:crypto';
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const repo=fileURLToPath(new URL('../',import.meta.url));
export function configureLocal({python,fontProfile,workbenchRoot,output}){
 if(fs.existsSync(output))throw Error('local_config_exists; choose a new output file');
 for(const p of [python,fontProfile])if(!fs.existsSync(p))throw Error('runtime_file_missing: '+p);
 const profile=JSON.parse(fs.readFileSync(fontProfile,'utf8').replace(/^\uFEFF/,''));
 for(const face of Object.values(profile.faces||{}))if(!fs.existsSync(face.path))throw Error('font_missing: '+face.path);
 const env={...process.env,PYTHONPATH:path.join(repo,'portable-production','direct-pdf'),PYTHONUTF8:'1'};
 const probe=JSON.parse(execFileSync(python,['-c',
  'import sys,json; assert sys.version_info >= (3,12), "Python >=3.12 required"; import pypdf,pymupdf,PIL,numpy,cairosvg; from journal_pdf.fonts import FontRegistry; from journal_pdf.editorial import engine_signature; FontRegistry(sys.argv[1]); print(json.dumps({"signature":engine_signature(),"version":sys.version}))',fontProfile],{env,encoding:'utf8',windowsHide:true,timeout:60000}));
 const credentialsFile=path.join(workbenchRoot,'workbuddy.config.json');
 const config={origin:'http://127.0.0.1:18741',workbenchRoot,credentialsFile,python,fontProfile,
  knownFaultsFile:path.join(workbenchRoot,'production-known-faults.json'),receiptRoot:path.join(workbenchRoot,'production-receipts'),
  caseIndexPath:path.join(workbenchRoot,'figure-cases.json'),runtimeLock:{python:{path:python,sha256:hash(python)},fontProfile:{path:fontProfile,sha256:hash(fontProfile)},engineSignature:probe.signature}};
 if(fs.existsSync(credentialsFile)){
  const local=JSON.parse(fs.readFileSync(credentialsFile,'utf8'));
  local.workerToken||=randomBytes(32).toString('hex');local.reviewerToken||=randomBytes(32).toString('hex');local.qualityPython=python;
  fs.writeFileSync(credentialsFile,JSON.stringify(local,null,2)+'\n');
 }
 fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(config,null,2)+'\n',{flag:'wx'});
 return {config:output,engineSignature:probe.signature,python:probe.version,workbenchConfigured:fs.existsSync(credentialsFile)};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const [python,fontProfile,workbenchRoot,output]=process.argv.slice(2);if(!output)throw Error('Usage: configure-local.mjs PYTHON FONT_PROFILE WORKBENCH_ROOT OUTPUT');console.log(JSON.stringify(configureLocal({python,fontProfile,workbenchRoot,output})));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
