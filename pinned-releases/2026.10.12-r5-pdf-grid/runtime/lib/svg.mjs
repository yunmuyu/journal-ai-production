import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {existsSync,mkdirSync,copyFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {waitForCompletePdf} from './pdf-output.mjs';
import {fileHash,sha256,readJson,writeJson,logEvent} from './core.mjs';
import {packageRoot} from './adobe.mjs';
import {pythonRuntime} from './ingest.mjs';
import {createJob} from './jobs.mjs';
export function convertSvg(root,source){
 root=path.resolve(root);source=path.resolve(source);createJob(root);
 const edge=[process.env.JFW_EDGE,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].filter(Boolean).find(existsSync);if(!edge)throw Error('Verified Edge executable not found');
 const driver=path.join(packageRoot,'scripts/svg_page.py'),sourceHash=fileHash(source),key=sha256(sourceHash+fileHash(driver)+fileHash(path.join(packageRoot,'lib/svg.mjs'))+fileHash(path.join(packageRoot,'lib/pdf-output.mjs'))),dir=path.join(root,'conversions',key),result=path.join(dir,'result.json');mkdirSync(dir,{recursive:true});
 if(existsSync(result)){const r=readJson(result);if(r.ok&&r.outputs.every(o=>existsSync(o.path)&&fileHash(o.path)===o.sha256))return {cached:true,...r};}
 const start=Date.now(),input=path.join(dir,'input.svg'),html=path.join(dir,'page.html'),pdf=path.join(dir,'figure-'+randomUUID()+'.pdf');copyFileSync(source,input);
 execFileSync(pythonRuntime(),[driver,input,html],{encoding:'utf8',windowsHide:true,timeout:30000});
 execFileSync(edge,['--headless','--disable-gpu','--no-first-run','--no-pdf-header-footer','--user-data-dir='+path.join(dir,'edge-profile'),'--print-to-pdf='+pdf,pathToFileURL(html).href],{encoding:'utf8',windowsHide:true,timeout:60000,stdio:'pipe'});
 waitForCompletePdf(pdf);
 if(!existsSync(pdf)||fileHash(source)!==sourceHash)throw Error('SVG conversion missing or original changed');const r={ok:true,source,sourceHash,outputs:[{path:pdf,sha256:fileHash(pdf),kind:'pdf',scope:'svg_viewport'}],dimensions:readJson(path.join(dir,'page.json')),durationMs:Date.now()-start};writeJson(result,r);logEvent(root,{event:'svg_converted',source,result,durationMs:r.durationMs});return r;
}
