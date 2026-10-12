import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {loadModel} from './model.mjs';
import {persistFeedback} from './feedback.mjs';
import {createClassificationStore,createClassificationHandler} from './classification-store.mjs';
import {fileURLToPath} from 'node:url';
import {recordRoot} from './paths.mjs';
import {createDecisionHandler} from './decision-http.mjs';
const port=Number(process.env.JFW_REVIEW_PORT||18741),origin='http://127.0.0.1:'+port;
const decisions=createDecisionHandler({recordRoot,origin});
const classificationStore=createClassificationStore(path.join(recordRoot,'figure-classification.json'));
const handleClassification=createClassificationHandler({store:classificationStore,origin,assetsDirectory:fileURLToPath(new URL('.',import.meta.url))});
let model=loadModel(),modelError=null;
setInterval(()=>{try{model=loadModel();modelError=null;}catch(e){modelError=e.message;console.error(new Date().toISOString(),e.message);}},5000).unref();
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.pdf':'application/pdf','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'};
function openRegistered(file,mode,res){
 execFile('powershell.exe',['-NoProfile','-NonInteractive','-Command',fs.readFileSync(new URL('open-file.ps1',import.meta.url),'utf8')],{windowsHide:true,timeout:18000,env:{...process.env,JFW_OPEN_FILE:file,JFW_OPEN_MODE:mode}},(error,stdout,stderr)=>{
  let receipt;try{receipt=JSON.parse(stdout.trim());}catch{}
  const ok=!error&&receipt?.foreground===true;
  if(!ok)console.error(new Date().toISOString(),'File foreground verification failed',stderr||error?.message||stdout);
  res.setHeader('Content-Type','application/json; charset=utf-8');res.writeHead(ok?200:500).end(JSON.stringify(ok?{ok:true,path:file,foreground:true}:{ok:false,error:'已请求打开，但未能确认目标窗口在前台；请查看应用是否有提示。'}));
 });
}
http.createServer((req,res)=>{
 const url=new URL(req.url,origin);
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
 if(req.headers.host!=='127.0.0.1:'+port){res.writeHead(403).end();return;}
 if(decisions.handle(req,res,url))return;
 if((url.pathname==='/classification'||url.pathname==='/classification/')&&url.searchParams.get('embedded')!=='1'){res.writeHead(302,{Location:'/#classification'}).end();return;}
 if(url.pathname==='/classification'||url.pathname==='/classification/'){res.setHeader('Content-Type','text/html; charset=utf-8');fs.createReadStream(new URL('decision-review.html',import.meta.url)).pipe(res);return;}
 if(handleClassification(req,res,url))return;
 if(url.pathname.startsWith('/feedback/')){
  if(req.method!=='POST'||req.headers.origin!==origin){res.writeHead(403).end();return;}
  const id=url.pathname.slice(10);const chunks=[];let length=0,tooLarge=false;
  req.on('data',chunk=>{length+=chunk.length;if(length>64*1024*1024)tooLarge=true;else chunks.push(chunk);});
  req.on('end',()=>{
   res.setHeader('Content-Type','application/json; charset=utf-8');
   try{if(tooLarge)throw Object.assign(Error('图片总量过大，本次未保存'),{status:413});const input=JSON.parse(Buffer.concat(chunks).toString('utf8'));persistFeedback(id,input,new Set(model.data.rows.map(r=>r.id)));model=loadModel();res.end(JSON.stringify({ok:true,figure:model.data.rows.find(r=>r.id===id)}));}
   catch(error){res.writeHead(error.status||500).end(JSON.stringify({ok:false,error:error.message}));}
  });return;
 }
 if(url.pathname==='/data'){if(modelError){res.writeHead(503,{'Content-Type':'application/json'}).end(JSON.stringify({error:'生产记录读取失败，当前未同步'}));return;}res.setHeader('Content-Type','application/json; charset=utf-8');res.end(JSON.stringify(model.data));return;}
 if(url.pathname.startsWith('/file/')||url.pathname.startsWith('/locate/')||url.pathname.startsWith('/open/')){
  const token=url.pathname.split('/')[2],file=model.files.get(token)||decisions.files.get(token);
  if(!file||!fs.existsSync(file)){res.writeHead(404).end('File not found');return;}
  if(url.pathname.startsWith('/open/')){
   if(req.method!=='POST'||req.headers.origin!==origin){res.writeHead(403).end();return;}
   if(!['.doc','.docx','.ai','.pdf'].includes(path.extname(file).toLowerCase())||!fs.statSync(file).isFile()){res.writeHead(400).end('Unsupported application file');return;}
   openRegistered(file,'open',res);return;
  }
  if(url.pathname.startsWith('/locate/')){
   if(req.method!=='POST'||req.headers.origin!==origin){res.writeHead(403).end();return;}
   openRegistered(file,'locate',res);return;
  }
  if(fs.statSync(file).isDirectory()){res.writeHead(400).end();return;}
  const type=types[path.extname(file).toLowerCase()]||'application/octet-stream';res.setHeader('Content-Type',type);
  if(type==='application/octet-stream')res.setHeader('Content-Disposition',"attachment; filename*=UTF-8''"+encodeURIComponent(path.basename(file)));
  fs.createReadStream(file).pipe(res);return;
 }
 if(url.pathname.startsWith('/view/')){const file=model.files.get(url.pathname.split('/')[2]);if(!file||path.extname(file).toLowerCase()!=='.pdf'){res.writeHead(404).end();return;}res.setHeader('Content-Type','text/html; charset=utf-8');fs.createReadStream(new URL('viewer.html',import.meta.url)).pipe(res);return;}
 if(url.pathname.startsWith('/pdfjs/')){const name=url.pathname.slice(7);const files={'pdf.mjs':'build/pdf.mjs','pdf.worker.mjs':'build/pdf.worker.mjs'};const relative=files[name]||(name.startsWith('fonts/')&&/^[a-zA-Z0-9_.-]+$/.test(name.slice(6))?'standard_fonts/'+name.slice(6):null);if(!relative){res.writeHead(404).end();return;}const p='C:/Users/xdxxk/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pdfjs-dist/'+relative;if(!fs.existsSync(p)){res.writeHead(404).end();return;}res.setHeader('Content-Type',name.endsWith('.mjs')?'text/javascript':'application/octet-stream');fs.createReadStream(p).pipe(res);return;}
 if(url.pathname==='/vendor/tabler.min.css'){res.setHeader('Content-Type','text/css; charset=utf-8');fs.createReadStream(new URL('vendor/package/dist/css/tabler.min.css',import.meta.url)).pipe(res);return;}
 const asset={'/':'index.html','/style.css':'style.css','/app.js':'app.js','/viewer.js':'viewer.js','/decision-panel.js':'decision-panel.js','/decision-panel.css':'decision-panel.css','/decision-review.js':'decision-review.js','/decision-review.css':'decision-review.css'}[url.pathname];
 if(!asset){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',types[path.extname(asset)]);fs.createReadStream(new URL(asset,import.meta.url)).pipe(res);
}).listen(port,'127.0.0.1',()=>console.log(JSON.stringify({url:origin,rows:model.data.rows.length,pid:process.pid})));

