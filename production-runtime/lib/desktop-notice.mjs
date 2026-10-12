import{spawn}from'node:child_process';
import{existsSync,unlinkSync}from'node:fs';
import path from'node:path';
import{tmpdir}from'node:os';
import{fileURLToPath}from'node:url';
import{writeJson}from'./core.mjs';
let session=null;
export function withAdobeSession(applications,work){
 if(session)return work();
 const state=path.join(tmpdir(),'journal-figure-notice-'+process.pid+'.json');
 session={state,applications,uncertain:false,started:false};
 try{return work();}finally{if(!session.uncertain&&existsSync(state))unlinkSync(state);session=null;}
}
export function markAdobeUncertain(){if(session){session.uncertain=true;writeJson(session.state,{application:session.applications.join('、'),status:'uncertain'});}}

export function ensureAdobeNotice(){
 if(!session||session.started)return;session.started=true;const {state,applications}=session;
writeJson(state,{application:applications.join('、'),status:'running'});
 const ps=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../adobe/desktop-notice.ps1');
 const child=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',ps,'-StatePath',state],{windowsHide:true,stdio:'ignore'});child.on('error',()=>{});child.unref();

}
