import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';

test('run enforces UTF-8 Python stdout and logs for Chinese artifact paths',async t=>{
 const python=process.env.JFW_TEST_PYTHON||(process.platform==='win32'?'python':'python3');
 try{await promisify(execFile)(python,['--version'],{windowsHide:true,timeout:5000});}
 catch{return t.skip('Set JFW_TEST_PYTHON to an available Python executable for real CLI encoding verification');}
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'执行器中文-')),events=[];
 const server=http.createServer((req,res)=>{let body='';req.setEncoding('utf8');req.on('data',c=>body+=c);req.on('end',()=>{events.push(JSON.parse(body));res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'}).end(JSON.stringify({ok:true,pauseRequested:false}));});});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 t.after(async()=>{await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true});});
 const config=path.join(root,'config.json'),lease=path.join(root,'lease.json'),artifact=path.join(root,'图件-灰度.jpg.txt');
 fs.writeFileSync(config,JSON.stringify({origin:'http://127.0.0.1:'+server.address().port,workerToken:'test-only'}));
 fs.writeFileSync(lease,JSON.stringify({id:'fixture',lease:'test-only'}));
 const cli=fileURLToPath(new URL('./workbuddy-cli.mjs',import.meta.url));
 const script="import sys,pathlib; p=pathlib.Path(sys.argv[1]); p.write_text('\u7070\u5ea6\u56fe\u4ef6',encoding='utf-8'); print(sys.stdout.encoding); print(str(p)); print('\u4e2d\u6587\u6210\u56fe\u56de\u4f20')";
 const result=await promisify(execFile)(process.execPath,[cli,config,'run',lease,python,'-c',script,artifact],{windowsHide:true,encoding:'utf8',env:{...process.env,PYTHONUTF8:'0',PYTHONIOENCODING:'gbk'}});
 assert.match(result.stdout,/utf-8/i);assert.ok(result.stdout.includes(artifact));assert.match(result.stdout,/中文成图回传/);
 assert.equal(fs.readFileSync(artifact,'utf8'),'灰度图件');
 const final=events.findLast(e=>e.action==='progress'&&e.message.startsWith('工具结束'));
 assert.ok(final.message.includes(artifact));assert.match(final.message,/中文成图回传/);assert.doesNotMatch(final.message,/�/);
});
