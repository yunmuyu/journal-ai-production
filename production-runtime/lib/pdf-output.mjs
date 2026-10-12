import {existsSync,readFileSync} from 'node:fs';

export function waitForCompletePdf(file,{timeoutMs=30000,intervalMs=100}={}){
 const deadline=Date.now()+timeoutMs,signal=new Int32Array(new SharedArrayBuffer(4));
 let previous=null;
 while(Date.now()<deadline){
  if(existsSync(file)){
   const data=readFileSync(file);
   const complete=data.subarray(0,5).toString()==='%PDF-'&&/%%EOF\s*$/.test(data.subarray(-1024).toString());
   if(complete&&previous?.equals(data))return;
   previous=complete?data:null;
  }
  Atomics.wait(signal,0,0,intervalMs);
 }
 throw Error('Timed out waiting for complete PDF: '+file);
}
