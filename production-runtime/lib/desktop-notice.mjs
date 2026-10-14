import{spawn}from'node:child_process';
import{existsSync,unlinkSync}from'node:fs';
import path from'node:path';
import{tmpdir}from'node:os';
import{fileURLToPath}from'node:url';
import{writeJson}from'./core.mjs';
let session=null;
function recordCleanupFailure(active,error){
 const detail={state:active.state,code:error?.code||null,message:error?.message||String(error),time:new Date().toISOString()};
 const record=active.state+'.cleanup-failed.json';
 try{writeJson(record,{status:'cleanup_failed',...detail});}
 catch(recordError){process.emitWarning(`Failed to record Adobe notice cleanup error for ${active.state}: ${recordError?.message||String(recordError)}`,{code:'JFW_NOTICE_CLEANUP_RECORD_FAILED'});}
 process.emitWarning(`Failed to remove Adobe notice state ${active.state}: ${detail.message}`,{code:'JFW_NOTICE_CLEANUP_FAILED'});
}
export function withAdobeSession(applications,work){
 if(session)return work();
 const state=path.join(tmpdir(),'journal-figure-notice-'+process.pid+'.json');
 session={state,applications,uncertain:false,started:false};
 try{return work();}finally{
  const active=session;
  try{if(!active.uncertain&&existsSync(active.state))unlinkSync(active.state);}
  catch(error){recordCleanupFailure(active,error);}
  finally{session=null;}
 }
}
export function markAdobeUncertain(){if(session){session.uncertain=true;writeJson(session.state,{application:session.applications.join('、'),status:'uncertain'});}}

export function ensureAdobeNotice(){
 if(!session||session.started)return;session.started=true;const {state,applications}=session;
writeJson(state,{application:applications.join('、'),status:'running'});
 const ps=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../adobe/desktop-notice.ps1');
 const child=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',ps,'-StatePath',state],{windowsHide:true,stdio:'ignore'});child.on('error',()=>{});child.unref();

}
