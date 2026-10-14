import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

test('isolated workbench HTTP: stale approval rejected, current approval saved, withdrawal restored', {timeout:20000},async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-http-'));
 t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 fs.mkdirSync(path.join(dir,'work/october-production'),{recursive:true});
 const output=path.join(dir,'figure.pdf');fs.writeFileSync(output,'fixture-v1');
 fs.writeFileSync(path.join(dir,'inventory.json'),JSON.stringify({articles:[{id:'A',author:'测试作者',editor:'测试编辑',localWord:output}],figures:[{id:'A-F1',articleId:'A',number:'1',caption:'测试图'}]}));
 fs.writeFileSync(path.join(dir,'author-templates.json'),'{}');
 const record=path.join(dir,'production-results.json');
 fs.writeFileSync(record,JSON.stringify({articles:{},figures:{'A-F1':{status:'内部复核通过',output}}}));
 const socket=net.createServer();socket.listen(0,'127.0.0.1');await once(socket,'listening');const port=socket.address().port;await new Promise(r=>socket.close(r));
 const origin='http://127.0.0.1:'+port;
 const child=spawn(process.execPath,[fileURLToPath(new URL('./server.mjs',import.meta.url))],{cwd:dir,env:{...process.env,JFW_RECORD_ROOT:dir,JFW_REVIEW_PORT:String(port),JFW_DELIVERY_ROOT:''},stdio:'pipe',windowsHide:true});
 let log='';child.stderr.on('data',b=>log+=b);const exited=once(child,'exit');
 t.after(async()=>{child.kill();await exited;});
 let data;
 for(let i=0;i<60;i++){try{data=await (await fetch(origin+'/data')).json();break;}catch{if(child.exitCode!==null)throw Error(log);await delay(100);}}
 assert.ok(data,log);const oldToken=data.rows[0].artifactToken;assert.ok(oldToken);
 const post=body=>fetch(origin+'/feedback/A-F1',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({text:'',accepted:true,revision:0,images:[],...body})});
 fs.writeFileSync(output,'fixture-v2');
 assert.equal((await post({artifactToken:oldToken})).status,409);
 assert.equal(JSON.parse(fs.readFileSync(record)).figures['A-F1'].userAcceptance,undefined);
 const {inspectAcceptance}=await import('../collaboration/acceptance.mjs');
 const current=inspectAcceptance('A-F1',JSON.parse(fs.readFileSync(record)).figures['A-F1']).token;
 const approved=await post({artifactToken:current});assert.equal(approved.status,200);assert.equal((await approved.json()).figure.status,'终检通过');
 const withdrawn=await post({accepted:false,revision:1});assert.equal(withdrawn.status,200);assert.equal((await withdrawn.json()).figure.status,'待终检');
 assert.equal(JSON.parse(fs.readFileSync(record)).figures['A-F1'].userAcceptance.accepted,false);
});
