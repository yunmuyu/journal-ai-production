import path from 'node:path';
import {existsSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {packageRoot} from './adobe.mjs';
import {readJson,writeJson,fileHash,logEvent} from './core.mjs';
import {createJob,addFigure,updateFigure} from './jobs.mjs';
export function pythonRuntime(){
 const candidates=[process.env.JFW_PYTHON,path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')].filter(Boolean);
 const found=candidates.find(existsSync);if(!found)throw Error('Set JFW_PYTHON to a verified Python 3 runtime');return found;
}
export function ingestDocx(root,source,author){
 if(!author?.trim())throw Error('Confirmed author required for document ingestion');
 root=path.resolve(root);source=path.resolve(source);if(path.extname(source).toLowerCase()!=='.docx')throw Error('Convert a source copy to DOCX before ingestion');
 createJob(root);const hash=fileHash(source),dir=path.join(root,'extractions',hash);mkdirSync(dir,{recursive:true});const report=path.join(dir,'extraction.json');
 execFileSync(pythonRuntime(),[path.join(packageRoot,'scripts/extract_docx.py'),source,path.join(dir,'media'),report],{encoding:'utf8',windowsHide:true,timeout:60000,env:{...process.env,PYTHONIOENCODING:'utf-8'}});
 const result=readJson(report);if(result.articleHash!==hash||fileHash(source)!==hash)throw Error('Article changed during extraction');
 for(const item of result.figures){
  item.figureIds=[];
  for(let i=0;i<item.members.length;i++){
   const m=item.members[i],f=addFigure(root,{source:m.source,author,number:item.number,caption:item.caption,article:source,objectKey:'paragraph:'+item.paragraph+':member:'+i,crop:m.crop,identityName:m.member});
   item.figureIds.push(f.id);
   if(item.status!=='ready')updateFigure(root,f.id,{status:'needs_layout_review',reason:'Multi-object or repeated media occurrence; inspect Word layout',extraction:path.relative(root,report)});
  }
 }
 writeJson(report,result);logEvent(root,{event:'document_extracted',source,hash,figures:result.figures.length,issues:result.issues.length});return result;
}
export function pairReferences(root,files){
 const state=readJson(path.join(root,'job.json')),pairs=[],pending=[];
 for(const file of files){const label=path.resolve(file),match=label.match(/图\s*([0-9０-９]+)/);if(!match){pending.push({file,reason:'missing_figure_number'});continue;}
  const number=match[1].replace(/[０-９]/g,c=>String(c.charCodeAt(0)-65296));const candidates=state.figures.filter(f=>f.number===number&&f.author&&label.includes(f.author));
  if(candidates.length!==1){pending.push({file,reason:'ambiguous_or_missing_author_figure',candidates:candidates.map(f=>f.id)});continue;}
  pairs.push({figureId:candidates[0].id,path:label,sha256:fileHash(label),status:'candidate_requires_visual_match'});
 }
 const result={pairs,pending};writeJson(path.join(root,'reference-pairs.json'),result);return result;
}
