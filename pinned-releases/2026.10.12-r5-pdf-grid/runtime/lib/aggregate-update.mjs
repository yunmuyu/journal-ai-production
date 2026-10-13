import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {adobe} from './adobe.mjs';
import {fileHash,writeJson} from './core.mjs';
import {pythonRuntime} from './ingest.mjs';

export function updateAggregate(directory,base,changes,{invoke=adobe}={}){
 if(fileHash(base.ai)!==base.aiHash||fileHash(base.pdf)!==base.pdfHash)throw Error('Base revision changed; preserve manual edits and rebase explicitly');
 if(!changes.length)throw Error('Changes required');
 const identities=new Set();
 for(const change of changes){
  if(identities.has(change.name)||base.placements.filter(p=>p.name===change.name).length!==1)throw Error('Invalid figure identity');
  if(fileHash(change.ai)!==change.sha256)throw Error('Replacement revision changed');
  identities.add(change.name);
 }
 const selected=base.placements.filter(p=>identities.has(p.name));
 const affectedPages=[...new Set(selected.map(p=>p.page))].sort((a,b)=>a-b);
 const affectedArtboards=[...new Set(selected.map(p=>p.artboardIndex+1))].sort((a,b)=>a-b);
 const root=path.resolve(directory);fs.mkdirSync(root,{recursive:true});
 const attempt=fs.mkdtempSync(root+'/update-');
 const input=attempt+'/input.ai',ai=attempt+'/author.ai',partial=attempt+'/affected-pages.pdf',pdf=attempt+'/summary.pdf',preview=attempt+'/native.png';
 fs.copyFileSync(base.ai,input);
 const privateChanges=changes.map((change,index)=>{const copy=attempt+'/replacement-'+index+'.ai';fs.copyFileSync(change.ai,copy);if(fileHash(copy)!==change.sha256)throw Error('Replacement revision changed during copy');return {...change,ai:copy};});
 writeJson(attempt+'/manifest.json',{status:'started',base,changes,affectedPages,affectedArtboards});
 const started=performance.now();
 try{
  const result=invoke('illustrator',{mode:'aggregate-update',input,ai,pdf:partial,preview,placements:base.placements,changes:privateChanges,affectedArtboards},attempt+'/adobe');
  if(!result.ok||!result.untouchedPreserved||JSON.stringify(result.changedGroups)!==JSON.stringify(changes.map(c=>c.name)))throw Error('Incomplete incremental update');
  if(fileHash(base.ai)!==base.aiHash||fileHash(base.pdf)!==base.pdfHash||changes.some(c=>fileHash(c.ai)!==c.sha256))throw Error('Input revision changed during update');
  const merge="import sys,json;from pypdf import PdfReader,PdfWriter;old=PdfReader(sys.argv[1]);new=PdfReader(sys.argv[2]);pages=json.loads(sys.argv[4]);assert len(new.pages)==len(pages);assert len(old.pages)==int(sys.argv[5]);w=PdfWriter();lookup={p-1:i for i,p in enumerate(pages)};[w.add_page(new.pages[lookup[i]] if i in lookup else p) for i,p in enumerate(old.pages)];w.write(sys.argv[3]);print(json.dumps({'oldPages':len(old.pages),'partialPages':len(new.pages),'mergedPages':len(w.pages)}))";
  const merged=JSON.parse(execFileSync(pythonRuntime(),['-X','utf8','-c',merge,base.pdf,partial,pdf,JSON.stringify(affectedPages),String(base.pages)],{encoding:'utf8',windowsHide:true,timeout:30000}));
  const entry={ok:true,ai,pdf,partialPdf:partial,preview,aiHash:fileHash(ai),pdfHash:fileHash(pdf),partialPdfHash:fileHash(partial),placements:base.placements,pages:base.pages,affectedPages,affectedArtboards,result,merge:merged,wallSeconds:(performance.now()-started)/1000,attempt};
  writeJson(attempt+'/manifest.json',{status:'completed',base,changes,result:entry});
  return entry;
 }catch(error){writeJson(attempt+'/manifest.json',{status:'failed',base,changes,error:String(error.message||error)});throw error;}
}
