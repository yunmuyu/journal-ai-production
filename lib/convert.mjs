import path from 'node:path';
import {mkdirSync,copyFileSync,existsSync,openSync,closeSync,unlinkSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {packageRoot} from './adobe.mjs';
import {fileHash,sha256,readJson,writeJson,logEvent} from './core.mjs';
import {createJob} from './jobs.mjs';
import {validatePptxPlan} from './pptx-plan.mjs';
export function convertOffice(root,source,options={}){
 root=path.resolve(root);source=path.resolve(source);
 const ext=path.extname(source).toLowerCase();if(!/^\.(docx?|ppt[xm]?|vsd[xm]?|xls[xmb]?|emf|wmf)$/.test(ext))throw Error('Unsupported Office source');
 const selection=options.cellSelection,visioSvg=options.visioSvg;
 if(visioSvg!==undefined&&(!/^.vsd[xm]?$/.test(ext)||!visioSvg||!Number.isInteger(visioSvg.page)||visioSvg.page<1))throw Error("Invalid explicit Visio SVG page");
 if(selection&&(!/^\.xls[xmb]?$/.test(ext)||!Number.isInteger(selection.sheet)||selection.sheet<1||!/^[A-Z]+[1-9]\d*:[A-Z]+[1-9]\d*$/.test(selection.range)))throw Error('Invalid explicit Excel cell selection');
 const hash=fileHash(source),pptxPlan=options.pptxPlan;
 if(pptxPlan)validatePptxPlan(pptxPlan,{path:source,sha256:hash},options.python);
 if(options.grayscale&&(!pptxPlan||!options.python))throw Error('pptx_gray_plan_required');
 createJob(root);
 const driver=path.join(packageRoot,'scripts/convert-office.js'),verify=path.join(packageRoot,'scripts/verify_pptx_geometry.py');
 if(pptxPlan)execFileSync(options.python,[verify,source,source],{encoding:'utf8',windowsHide:true,timeout:30000});
 const grayScript=path.join(packageRoot,'scripts/prepare_pdf_vector_gray.py');
 const key=sha256(hash+fileHash(driver)+(selection?JSON.stringify(selection):'')+(visioSvg?JSON.stringify(visioSvg):'')+(pptxPlan?JSON.stringify(pptxPlan)+fileHash(verify):'')+(options.grayscale?fileHash(grayScript):''));const dir=path.join(root,'conversions',key),result=path.join(dir,'result.json');mkdirSync(dir,{recursive:true});
 if(existsSync(result)){const old=readJson(result);if(old.ok&&[...old.outputs,...(old.intermediates??[])].every(o=>o.sha256&&existsSync(o.path)&&fileHash(o.path)===o.sha256))return {cached:true,...old};}
 const lock=path.join(dir,'.lock');let fd;try{fd=openSync(lock,'wx');}catch{throw Error('Conversion is active or needs recovery: '+lock);}
 let uncertain=false;
 try{
  const input=path.join(dir,'input'+ext);copyFileSync(source,input);writeJson(path.join(dir,'request.json'),{input,directory:dir,result,cellSelection:selection,visioSvg,pptxPlan});
  try{execFileSync('cscript.exe',['//nologo','//E:JScript',driver,path.join(dir,'request.json')],{encoding:'utf8',windowsHide:true,timeout:180000});}
  catch(error){
   if(error.code!=='ETIMEDOUT'&&existsSync(result)){const failed=readJson(result);if(failed.ok===false)throw Error(failed.error);}
   throw error;
  }
  const r=readJson(result);if(!r.ok)throw Error(r.error);
  if(pptxPlan)r.geometry=JSON.parse(execFileSync(options.python,[verify,source,input],{encoding:'utf8',windowsHide:true,timeout:30000}));
  for(const o of r.outputs)o.sha256=fileHash(o.path);
  if(options.grayscale){
   const original=r.outputs.find(o=>o.kind==='pdf');if(!original)throw Error('pptx_gray_pdf_missing');
   const output=path.join(dir,'prepared-gray.pdf');if(existsSync(output))throw Error('pptx_gray_incomplete_previous_attempt');
   execFileSync(options.python,[grayScript,original.path,output,original.sha256],{encoding:'utf8',windowsHide:true,timeout:30000});
   r.intermediates=r.outputs;r.outputs=[{path:output,kind:'pdf',scope:'gray-intermediate',sha256:fileHash(output)}];
  }
  if(fileHash(source)!==hash)throw Error('Original changed during conversion');Object.assign(r,{source,sourceHash:hash,driverHash:fileHash(driver)});writeJson(result,r);logEvent(root,{event:'converted',source,result,durationMs:r.durationMs});return r;
 }catch(e){uncertain=e.code==='ETIMEDOUT';logEvent(root,{event:'conversion_failed',source,error:e.message,uncertain});throw e;}finally{closeSync(fd);if(!uncertain)unlinkSync(lock);}
}
