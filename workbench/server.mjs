import {assertRouteEditableState} from './route-editability.mjs';
import {createRouteConfirmations} from './route-confirmations.mjs';
import {activateRelatedCandidates} from './related-candidates.mjs';
import {createReviewTriage} from './review-triage.mjs';
import {createWorkBuddyHandler} from './workbuddy-http.mjs';
import {activateWorkBuddy,registerInventoryFigures,directPublicationState,restoreAcceptedDirectWorkBuddy} from './workbuddy-candidates.mjs';
import {createArchiveIntake} from './archive-intake.mjs';
import {registerArchiveArticles,syncRelatedReviews} from './archive-articles.mjs';
import http from 'node:http';
import {createRevisionHandler} from './revision-http.mjs';
import {activateRevision} from './revision-candidates.mjs';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {page,app} from './review/presentation.mjs';
import {createFeedbackStore} from './review/feedback-store.mjs';
import {createReviewStore,reviewVersion,reviewState} from './review/review-store.mjs';
const machinePath=process.env.JFW_MACHINE_CONFIG;
if(!machinePath)throw Error('Start through node journal.mjs start --config machine.local.json');
const machine=JSON.parse(fs.readFileSync(machinePath,'utf8').replace(/^\uFEFF/,''));
const base=machine.workbenchRoot,source=fileURLToPath(new URL('.',import.meta.url));
if(!base||!machine.wordRoot)throw Error('workspace_roots_required: configure workbenchRoot and wordRoot first');
const context={window:{}};vm.runInNewContext(fs.readFileSync(path.join(base,'november-data.js'),'utf8'),context);
const editor=JSON.parse(fs.readFileSync(path.join(base,'editor.json'),'utf8').replace(/^\uFEFF/,'')).editor;
const previewMap=JSON.parse(fs.readFileSync(path.join(base,'preview-map.json'),'utf8'));
const metadata=JSON.parse(fs.readFileSync(path.join(base,'figure-metadata.json'),'utf8'));
const pending=JSON.parse(fs.readFileSync(path.join(base,'pending-revisions.json'),'utf8'));
const wordRoot=machine.wordRoot;
const wordNames=fs.readdirSync(wordRoot).filter(n=>!n.startsWith('~$')&&/\.docx?$/i.test(n));
const files=new Map(),wordTokens=new Set();
function link(uri){const file=fileURLToPath(uri);if(!fs.existsSync(file))return null;const token=createHash('sha256').update(file).digest('hex').slice(0,24);files.set(token,file);return {token,name:path.basename(file),path:file,meta:metadata[file]||null};}
const articles=context.window.NOVEMBER_DATA.authors.map((a,index)=>{
 const matches=wordNames.filter(n=>n.includes(a.author));if(matches.length!==1)throw Error('Word配对不唯一：'+a.author);
 const word=link(pathToFileURL(path.join(wordRoot,matches[0])));wordTokens.add(word.token);
 const id='NOV-'+(index+1);return {id,word,author:a.author,label:a.author,editor,state:'全部通过',notices:[],figures:Array.from({length:a.main},(_,i)=>({id:id+'-F'+(i+1),articleId:id,author:a.author,number:String(i+1),editor,type:'待分类',status:'终检通过',outputs:a.files.filter(f=>f.number.split('.')[0]===String(i+1)).map(f=>({number:f.number,file:link(f.url)})),notices:[],feedback:null,reason:''}))};
});
for(const article of articles){
 for(const figure of article.figures){
  const revision=pending[article.author+'-'+figure.number];if(!revision)continue;
  if(!figure.previousOutputs?.length)figure.previousOutputs=figure.outputs;
 figure.revisionHistory=[...(figure.revisionHistory||[]),...figure.outputs];
  figure.outputs=(revision.outputs||[{number:figure.number,path:revision.path}]).map(output=>({number:output.number,file:link(pathToFileURL(output.path))}));
  figure.status='待终检';figure.notices=[{text:revision.note}];
 }
 if(article.figures.some(f=>f.status==='待终检'))article.state='待核验';
}
const rows=articles.flatMap(a=>a.figures),data={articles,rows,workspace:{},productionControl:null};
const feedbackStore=createFeedbackStore(path.join(base,'feedback.json'));
const reviewStore=createReviewStore(path.join(base,'acceptance.json'));
const routeConfirmations=createRouteConfirmations(path.join(base,'confirmed-production-routes.json'));
const productionRoutes=fs.existsSync(path.join(base,'production-routes.json'))?JSON.parse(fs.readFileSync(path.join(base,'production-routes.json'),'utf8')):{};
let revisionService,reviewTriage;
function updateFeedbackStates(){
 for(const figure of rows){
  if(productionRoutes[figure.id])figure.productionRoute=productionRoutes[figure.id];
  figure.feedback=feedbackStore.get(figure.id);
  figure.reviewVersion=reviewVersion(figure);
  figure.decision=routeConfirmations.get(figure);
  figure.previewCurrent=figure.outputs.length>0&&figure.outputs.every(o=>o.file&&fs.existsSync(o.file.path)&&createHash('sha256').update(fs.readFileSync(o.file.path)).digest('hex')===o.file.meta?.sha256);
  figure.status=figure.batchCandidate&&!figure.outputs.length?'待制作':reviewState(figure,pending[figure.id]||pending[figure.author+'-'+figure.number]||(figure.batchCandidate?{addressedFeedbackRevision:0}:null),reviewStore.get(figure.id));
 }
 for(const article of articles){
  if(article.archiveHash){if(article.figures.length)article.state=article.figures.some(f=>f.status==='异常')?'待修订':article.figures.some(f=>!f.outputs.length)?'制作中':article.figures.every(f=>f.status==='终检通过')?'全部通过':'待核验';continue;}
  article.state=article.figures.some(f=>f.status==='异常')?'待修订':article.figures.every(f=>f.status==='终检通过')?'全部通过':'待核验';
 }
}
updateFeedbackStates();
const mime={'.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.pdf':'application/pdf','.jpg':'image/jpeg','.png':'image/png'};
const assets={'/style.css':'style.css','/decision-panel.css':'decision-panel.css','/decision-board.css':'decision-board.css','/figure-panzoom.js':'figure-panzoom.js','/vendor/tabler.min.css':'vendor/package/dist/css/tabler.min.css'};
const port=Number(new URL(machine.origin).port||18741),origin=`http://127.0.0.1:${port}`;
const intakeConfigPath=path.join(base,'archive-intake.config.json');
const intakeConfig=fs.existsSync(intakeConfigPath)?JSON.parse(fs.readFileSync(intakeConfigPath,'utf8')):null;
const intakeService=intakeConfig?createArchiveIntake({config:intakeConfig,root:path.join(base,'archive-intake'),origin,register:batch=>registerArchiveArticles({articles,link,wordTokens},batch)}):null;
const relatedManifestPath=path.join(base,'related-candidates.manifest.json');
if(fs.existsSync(relatedManifestPath)){
 const receiptPath=path.join(base,'related-candidates.receipt.json');
 const receipt=fs.existsSync(receiptPath)?JSON.parse(fs.readFileSync(receiptPath,'utf8')):undefined;
 const readRecords=name=>fs.existsSync(path.join(base,name))?JSON.parse(fs.readFileSync(path.join(base,name),'utf8')):{};
 const merged=activateRelatedCandidates({articles,rows,metadata,link,feedbackRecords:readRecords('feedback.json'),acceptanceRecords:readRecords('acceptance.json')},JSON.parse(fs.readFileSync(relatedManifestPath,'utf8')),{receipt});
 if(!receipt){fs.writeFileSync(receiptPath+'.tmp',JSON.stringify(merged.receipt,null,2));fs.renameSync(receiptPath+'.tmp',receiptPath);}
}
const wbConfigPath=path.join(base,'workbuddy.config.json');
const wbContext={articles,rows,metadata,link};
const workbuddyService=fs.existsSync(wbConfigPath)?createWorkBuddyHandler({root:path.join(base,'workbuddy-jobs'),origin,assertRoutineEligible:(job,route)=>{
 const article=articles.find(a=>a.id===job.articleId);
 if(!article)throw Error('稿件未登记');
 const figure=rows.find(f=>f.articleId===job.articleId&&f.number===job.figureNumber);
 const feedback=figure&&feedbackStore.get(figure.id),acceptance=figure&&reviewStore.get(figure.id);
 if(figure?.outputs?.length||figure?.status==='终检通过'||acceptance?.accepted||feedback?.revision>0)throw Error('已有成稿、批注或验收，不能作为普通新图试跑');
 const word=job.sources.find(s=>path.resolve(s.path)===path.resolve(article.word?.path||''));
 const archive=job.sources.find(s=>/\.(zip|rar)$/i.test(s.path));
 if(!word||!archive)throw Error('缺少原任务绑定的Word或压缩包');
 if(route){
  const roots=[base,path.dirname(word.path),path.dirname(archive.path)].map(p=>fs.realpathSync(p));
  for(const source of [route.sourceReview.inventory,...route.sourceReview.candidates]){
   const actual=fs.realpathSync(source.path);
   if(!roots.some(root=>{const rel=path.relative(root,actual);return rel&&!rel.startsWith('..')&&!path.isAbsolute(rel);}))throw Error('候选来源不在当前稿件或工作台来源空间');
  }
 }
 return {archive,word};
},assertRouteEditable:(job)=>{
 updateFeedbackStates();
 const figure=rows.find(f=>f.articleId===job.articleId&&f.number===job.figureNumber);
 assertRouteEditableState(job,figure,articles);
},prepareFigures:jobs=>registerInventoryFigures(wbContext,jobs),figures:()=>{registerInventoryFigures(wbContext,workbuddyService.queue.list());updateFeedbackStates();return rows.map(f=>({articleId:f.articleId,number:f.number,pendingReview:f.status==='待终检'&&f.outputs.length>0,needsUserDecision:f.needsUserDecision===true}));},getDirectPublicationState:job=>{updateFeedbackStates();return directPublicationState({articles,metadata,feedbackStore,reviewStore,pending},job);},restoreAccepted:(job,result)=>{restoreAcceptedDirectWorkBuddy({articles,rows,metadata,link,feedbackStore,reviewStore,pending},job,result);updateFeedbackStates();},config:JSON.parse(fs.readFileSync(wbConfigPath,'utf8')),publish:(job,result)=>{
 if(job.kind==='revision')return reviewTriage.publish(job,result);
 if(job.correction){updateFeedbackStates();const f=rows.find(f=>f.articleId===job.articleId&&f.number===job.figureNumber);
  if(!f||f.status==='终检通过'||(f.feedback?.revision||0)!==job.correction.feedbackRevision||f.outputs.length!==job.correction.expectedOutputs.length||f.outputs.some(o=>!job.correction.expectedOutputs.some(p=>p.number===o.number&&p.sha256===o.file?.meta?.sha256)))throw Error('纠错期间图稿、批注或批准状态发生变化，保留候选不覆盖');
 }
 return activateWorkBuddy(wbContext,job,result);
},restore:(job,result)=>{activateWorkBuddy(wbContext,job,result);updateFeedbackStates();}}):null;
const workerConfig=path.join(base,'revision-worker.config.json');
if(fs.existsSync(workerConfig))revisionService=createRevisionHandler({enabled:false,root:path.join(base,'revision-jobs'),config:JSON.parse(fs.readFileSync(workerConfig,'utf8')),origin,rows,articles,refresh:updateFeedbackStates,activate(record){
 activateRevision({rows,metadata,pending,link},record);
}});

if(workbuddyService)reviewTriage=createReviewTriage({root:path.join(base,'review-triage'),origin,token:JSON.parse(fs.readFileSync(wbConfigPath,'utf8')).reviewerToken,queue:workbuddyService.queue,rows,articles,refresh:updateFeedbackStates,legacyJobs:()=>revisionService?.queue.list()||[],activate:record=>activateRevision({rows,metadata,pending,link},record),candidateManifest:JSON.parse(fs.readFileSync(wbConfigPath,'utf8')).feedbackCandidateManifest,candidateManifestsByFigureId:JSON.parse(fs.readFileSync(wbConfigPath,'utf8')).feedbackCandidateManifestsByFigureId||{},qualityPython:JSON.parse(fs.readFileSync(wbConfigPath,'utf8')).qualityPython,getAcceptance:id=>reviewStore.get(id)});
http.createServer(async(req,res)=>{
 if(req.headers.host!==`127.0.0.1:${port}`){res.writeHead(403).end();return;}
 const url=new URL(req.url,origin);res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
 if(reviewTriage?.handle(req,res,url))return;
 if(workbuddyService?.handle(req,res,url))return;
 if(intakeService?.handle(req,res,url))return;
 if(revisionService?.handle(req,res,url))return;
 if(url.pathname.startsWith('/route-decisions/')&&req.method==='POST'){
  const figure=rows.find(f=>f.id===url.pathname.slice(17));
  const token=fs.existsSync(wbConfigPath)?JSON.parse(fs.readFileSync(wbConfigPath,'utf8')).reviewerToken:null;
  if(req.headers.origin!==origin||!token||req.headers.authorization!=='Bearer '+token||!figure){res.writeHead(403).end();return;}
  let size=0,chunks=[];req.on('data',c=>{size+=c.length;if(size<=8192)chunks.push(c);});
  req.on('end',()=>{try{
   if(size>8192)throw Error('制作决定请求过大');
   updateFeedbackStates();routeConfirmations.save(figure,JSON.parse(Buffer.concat(chunks).toString('utf8')));
   updateFeedbackStates();res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({figure}));
  }catch(error){res.writeHead(409,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({error:error.message}));}});return;
 }
 if(url.pathname.startsWith('/accept/')&&req.method==='POST'){
  const figure=rows.find(f=>f.id===url.pathname.slice(8));
  if(req.headers.origin!==origin||!figure){res.writeHead(403).end();return;}
  let size=0,chunks=[];req.on('data',c=>{size+=c.length;if(size<=4096)chunks.push(c);});
  req.on('end',()=>{try{
   if(size>4096)throw Error('确认请求过大');
   updateFeedbackStates();
   if(!figure.outputs.length||figure.outputs.some(o=>!o.file||!fs.existsSync(o.file.path)||createHash('sha256').update(fs.readFileSync(o.file.path)).digest('hex')!==o.file.meta?.sha256))throw Error('图稿已变更或预览未更新，不能确认');
   reviewStore.save(figure.id,JSON.parse(Buffer.concat(chunks).toString('utf8')),figure.reviewVersion);
   updateFeedbackStates();res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({figure}));
  }catch(error){res.writeHead(409,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({error:error.message}));}});return;
 }
 if(url.pathname.startsWith('/feedback/')&&req.method==='POST'){
  const figure=rows.find(f=>f.id===url.pathname.slice(10));
  if(req.headers.origin!==origin||!figure){res.writeHead(403).end();return;}
  let size=0,chunks=[];
  req.on('data',chunk=>{size+=chunk.length;if(size<=20*1024*1024)chunks.push(chunk);});
  req.on('end',()=>{
   try{
    if(size>20*1024*1024)throw Error('截图总量超过20MB，请减少图片');
    figure.feedback=feedbackStore.save(figure.id,JSON.parse(Buffer.concat(chunks).toString('utf8')));
    updateFeedbackStates();
    res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({figure}));
   }catch(error){res.writeHead(400,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({error:error.message}));}
  });return;
 }
 if(url.pathname.startsWith('/open/')&&req.method==='POST'){
  const token=url.pathname.slice(6);if(req.headers.origin!==origin||!wordTokens.has(token)){res.writeHead(403).end();return;}
  if(!fs.existsSync(files.get(token))){res.writeHead(404,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({error:'原 Word 文件已移动或删除，链接需要重新核对。'}));return;}
  execFile('powershell.exe',['-NoProfile','-NonInteractive','-Command','[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding;\n'+fs.readFileSync(path.join(source,'open-file.ps1'),'utf8')],{windowsHide:true,timeout:18000,env:{...process.env,JFW_OPEN_FILE:files.get(token),JFW_OPEN_MODE:'open'}},(error,stdout,stderr)=>{
   let receipt;try{receipt=JSON.parse(stdout.trim());}catch{}
   fs.writeFileSync(path.join(base,'word-open-last.json'),JSON.stringify({time:new Date().toISOString(),file:files.get(token),receipt,error:error?.message,stderr},null,2));
   const ok=!error&&receipt?.foreground===true;res.writeHead(ok?200:500,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify(ok?{ok:true}:{error:'已请求打开 Word，但未确认窗口在前台，请查看 Word 窗口。'}));
  });return;
 }
 if(req.method!=='GET'){res.writeHead(403,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({error:'正式终检写回尚未接入。'}));return;}
 if(url.pathname==='/data'){if(workbuddyService)registerInventoryFigures(wbContext,workbuddyService.queue.list());await syncRelatedReviews(articles,intakeConfig?.relatedReviews,intakeConfig?path.join(base,'archive-intake','related-cache.json'):undefined);updateFeedbackStates();revisionService?.decorate();reviewTriage?.decorate();data.productionControl={revisionJobs:!!revisionService};res.setHeader('Content-Type','application/json; charset=utf-8');res.end(JSON.stringify(data));return;}
 if(url.pathname.startsWith('/pdfjs/')){const name=url.pathname.slice(7);const files={'pdf.mjs':'build/pdf.mjs','pdf.worker.mjs':'build/pdf.worker.mjs'};const relative=files[name]||(name.startsWith('fonts/')&&/^[a-zA-Z0-9_.-]+$/.test(name.slice(6))?'standard_fonts/'+name.slice(6):null);if(!relative){res.writeHead(404).end();return;}const p=path.join(process.env.JFW_PDFJS_ROOT||machine.pdfjsRoot||path.join(source,'vendor','pdfjs'),relative);if(!fs.existsSync(p)){res.writeHead(404).end();return;}res.setHeader('Content-Type',name.endsWith('.mjs')?'text/javascript':'application/octet-stream');fs.createReadStream(p).pipe(res);return;}
 if(url.pathname==='/figure-viewer.css'){res.setHeader('Content-Type','text/css; charset=utf-8');res.end(fs.readFileSync(path.join(source,'review','figure-viewer.css')));return;}
 if(url.pathname==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(page(source));return;}
 if(url.pathname==='/app.js'){res.setHeader('Content-Type','text/javascript; charset=utf-8');res.end(app(source));return;}
 if(url.pathname==='/zoom-controls.js'){res.setHeader('Content-Type','text/javascript; charset=utf-8');res.end(fs.readFileSync(path.join(source,'review','zoom-controls.js')));return;}
 if(url.pathname.startsWith('/preview/')){const file=files.get(url.pathname.slice(9)),info=metadata[file];if(!info){res.writeHead(404).end();return;}if(createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==info.sha256){res.writeHead(409).end('Source changed; regenerate preview');return;}res.setHeader('Content-Type','image/png');fs.createReadStream(info.previewPath||path.join(base,'previews',info.preview)).pipe(res);return;}
 if(url.pathname.startsWith('/file/')){const file=files.get(url.pathname.slice(6));if(!file||!fs.existsSync(file)){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(file).toLowerCase()]||'application/octet-stream');fs.createReadStream(file).pipe(res);return;}
 if(['/archive-intake.css','/archive-intake-ui.js','/workbuddy-ui.js'].includes(url.pathname)){res.setHeader('Content-Type',mime[path.extname(url.pathname)]);res.end(fs.readFileSync(path.join(source,url.pathname.slice(1))));return;}
 const relative=assets[url.pathname];if(!relative){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',mime[path.extname(relative)]);fs.createReadStream(path.join(source,relative)).pipe(res);
}).listen(port,'127.0.0.1',()=>console.log(JSON.stringify({url:origin,authors:articles.length,figures:rows.length,files:files.size,words:wordTokens.size})));

