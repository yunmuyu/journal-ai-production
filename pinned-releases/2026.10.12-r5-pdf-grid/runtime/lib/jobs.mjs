import { existsSync, mkdirSync, copyFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { figureId,fileHash,readJson,writeJson,logEvent } from './core.mjs';
const supported=new Set(['.doc','.docx','.svg','.vsd','.vsdx','.vsdm','.ppt','.pptx','.pptm','.xls','.xlsx','.xlsm','.xlsb','.pdf','.ai','.eps','.png','.jpg','.jpeg','.psd','.tif','.tiff','.emf','.wmf']);
export function createJob(root){root=path.resolve(root);mkdirSync(root,{recursive:true});if(existsSync(path.join(root,'job.json')))return readJson(path.join(root,'job.json'));const state={version:1,createdAt:new Date().toISOString(),assets:[],figures:[]};writeJson(path.join(root,'job.json'),state);return state;}
export function addFigure(root,{source,author,number,caption='',article='',objectKey='',crop,identityName}){
 const state=createJob(root),absolute=path.resolve(source),hash=fileHash(absolute),id=figureId(article||absolute,objectKey||0,identityName||path.basename(absolute));
 const ext=path.extname(absolute).toLowerCase(),relative='sources/'+hash+ext;mkdirSync(path.join(root,'sources'),{recursive:true});const dest=path.join(root,relative);if(!existsSync(dest))copyFileSync(absolute,dest);if(fileHash(dest)!==hash)throw Error('Source copy hash mismatch');
 const previous=state.figures.find(f=>f.id===id);if(previous&&previous.sourceHash===hash&&previous.author===author&&previous.number===String(number)&&previous.caption===caption&&JSON.stringify(previous.crop)===JSON.stringify(crop||[0,0,0,0]))return previous;
 if(previous&&previous.sourceHash===hash&&previous.author===author&&previous.number===String(number)&&JSON.stringify(previous.crop)===JSON.stringify(crop||[0,0,0,0])){previous.caption=caption;previous.originalPath=absolute;writeJson(path.join(root,'job.json'),state);logEvent(root,{event:'figure_metadata_updated',id,caption});return previous;}
 const figure={id,author,number:String(number),caption,article,objectKey,source:relative,sourceHash:hash,originalPath:absolute,crop:crop||[0,0,0,0],status:'awaiting_plan',revision:previous?previous.revision+1:1};
 state.figures=state.figures.filter(f=>f.id!==id);state.figures.push(figure);writeJson(path.join(root,'job.json'),state);logEvent(root,{event:'figure_added',id,sourceHash:hash});return figure;
}
export function scanAssets(root,input){
 const state=createJob(root),base=path.resolve(input),files=[];
 function walk(dir){for(const d of readdirSync(dir,{withFileTypes:true})){if(d.name.startsWith('~$')||d.isSymbolicLink())continue;const full=path.join(dir,d.name);if(d.isDirectory())walk(full);else if(supported.has(path.extname(full).toLowerCase()))files.push(full);}}
 if(statSync(base).isDirectory())walk(base);else files.push(base);
 for(const full of files){const hash=fileHash(full),relative=statSync(base).isDirectory()?path.relative(base,full):path.basename(full);if(!state.assets.some(a=>a.path===full&&a.sha256===hash))state.assets.push({path:full,relative,sha256:hash,extension:path.extname(full).toLowerCase(),status:'discovered'});}
 writeJson(path.join(root,'job.json'),state);logEvent(root,{event:'scan',input:base,files:files.length});return state.assets;
}
export function updateFigure(root,id,patch){const state=readJson(path.join(root,'job.json')),figure=state.figures.find(f=>f.id===id);if(!figure)throw Error('Unknown figure '+id);Object.assign(figure,patch);writeJson(path.join(root,'job.json'),state);return figure;}
