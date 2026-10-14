import assert from 'node:assert/strict';
import fs from 'node:fs';
import {syncBuiltinESMExports} from 'node:module';
import {mock, test} from 'node:test';
import os from 'node:os';
import path from 'node:path';

function failNextNoticeUnlink(statePath) {
 const original=fs.unlinkSync;
 let fail=true;
 mock.method(fs,'unlinkSync',function(file,...args){
  if(fail&&path.resolve(file)===statePath){
   fail=false;
   throw Object.assign(new Error('sharing violation'),{code:'EBUSY'});
  }
  return original.call(this,file,...args);
 });
 syncBuiltinESMExports();
 return()=>{mock.restoreAll();syncBuiltinESMExports();};
}

let moduleSequence=0;
async function loadFreshNoticeModule(){
 return import(`../production-runtime/lib/desktop-notice.mjs?cleanup-test=${++moduleSequence}`);
}

test('notice cleanup EBUSY does not fail completed work and session resets',async()=>{
 const statePath=path.join(os.tmpdir(),`journal-figure-notice-${process.pid}.json`);
 const failurePath=statePath+'.cleanup-failed.json';
 fs.writeFileSync(statePath,'{"status":"running"}');
 fs.rmSync(failurePath,{force:true});
 const restore=failNextNoticeUnlink(path.resolve(statePath));
 let withAdobeSession;
 try{
  ({withAdobeSession}=await loadFreshNoticeModule());
  assert.equal(withAdobeSession(['Photoshop'],()=>42),42);
  assert.equal(fs.existsSync(failurePath),true,'cleanup failure must leave a diagnostic record');
  assert.equal(JSON.parse(fs.readFileSync(failurePath,'utf8')).code,'EBUSY');
 }finally{restore();}
 try{
  assert.equal(withAdobeSession(['Photoshop'],()=>43),43);
  assert.equal(fs.existsSync(statePath),false,'a later Adobe session must clean up normally');
 }finally{
  fs.rmSync(statePath,{force:true});
  fs.rmSync(failurePath,{force:true});
 }
});

test('notice cleanup EBUSY does not replace an Adobe work failure',async()=>{
 const statePath=path.join(os.tmpdir(),`journal-figure-notice-${process.pid}.json`);
 const failurePath=statePath+'.cleanup-failed.json';
 fs.writeFileSync(statePath,'{"status":"running"}');
 fs.rmSync(failurePath,{force:true});
 const restore=failNextNoticeUnlink(path.resolve(statePath));
 let withAdobeSession;
 try{
  ({withAdobeSession}=await loadFreshNoticeModule());
  assert.throws(()=>withAdobeSession(['Photoshop'],()=>{throw new Error('Adobe render failed');}),/Adobe render failed/);
  assert.equal(JSON.parse(fs.readFileSync(failurePath,'utf8')).code,'EBUSY');
 }finally{restore();}
 try{
  assert.equal(withAdobeSession(['Photoshop'],()=>44),44);
  assert.equal(fs.existsSync(statePath),false,'a subsequent session must not reuse stale session state');
 }finally{
  fs.rmSync(statePath,{force:true});
  fs.rmSync(failurePath,{force:true});
 }
});


