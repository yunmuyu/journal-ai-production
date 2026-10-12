import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {persistFeedback} from './feedback.mjs';
function fixture(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-feedback-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const output=path.join(dir,'figure.pdf');fs.writeFileSync(output,'test');const store={recordsPath:path.join(dir,'records.json'),attachmentRoot:path.join(dir,'images')};fs.writeFileSync(store.recordsPath,JSON.stringify({figures:{one:{status:'内部复核通过',output},two:{status:'用户最终验收通过',output}},articles:{keep:true}}));return store;}
const body={text:'调整图例',accepted:false,revision:0,images:[]};
test('逐图保存反馈并保留同作者其他图与权威字段',t=>{const store=fixture(t);const result=persistFeedback('one',body,new Set(['one']),store);const records=JSON.parse(fs.readFileSync(store.recordsPath));assert.equal(records.figures.one.status,'待修订');assert.equal(records.figures.one.userFeedback.text,'调整图例');assert.equal(records.figures.two.status,'用户最终验收通过');assert.equal(records.articles.keep,true);assert.equal(result.revision,1);assert.throws(()=>persistFeedback('one',body,new Set(['one']),store),{status:409});assert.equal(JSON.parse(fs.readFileSync(store.recordsPath)).figures.one.userFeedback.revision,1);});
test('附件路径必须属于本图，未知图和无交付验收明确失败',t=>{const store=fixture(t),ids=new Set(['one','new']);assert.throws(()=>persistFeedback('unknown',body,ids,store),{status:404});assert.throws(()=>persistFeedback('one',{...body,images:[{path:'C:/arbitrary.png'}]},ids,store),{status:400});assert.throws(()=>persistFeedback('new',{...body,accepted:true},ids,store),{status:400});assert.throws(()=>persistFeedback('one',{...body,images:[{data:'ZmFrZQ=='}]},ids,store),{status:400});assert.equal(JSON.parse(fs.readFileSync(store.recordsPath)).figures.one.status,'内部复核通过');});
test('勾选和取消验收分别持久化，取消后恢复待终检',t=>{const store=fixture(t),ids=new Set(['one']);persistFeedback('one',{...body,text:'',accepted:true},ids,store);assert.equal(JSON.parse(fs.readFileSync(store.recordsPath)).figures.one.status,'用户最终验收通过');persistFeedback('one',{...body,text:'',revision:1},ids,store);assert.equal(JSON.parse(fs.readFileSync(store.recordsPath)).figures.one.status,'内部复核通过');});
test('原生产发布器持锁时拒绝反馈，释放后保留发布器的其他图更新',async t=>{
 const store=fixture(t),{spawn}=await import('node:child_process');
 const python='C:/Users/xdxxk/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
 const moduleDir=path.resolve('work/october-production/lixiumei');
 const source='import sys,json\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom registry_lock import production_registry_lock\np=Path(sys.argv[2])\nwith production_registry_lock(p):\n print("LOCKED",flush=True)\n sys.stdin.readline()\n state=json.loads(p.read_text(encoding="utf-8"))\n state["figures"]["two"]["review"]="publisher-update"\n tmp=p.with_name(p.name+".tmp")\n tmp.write_text(json.dumps(state),encoding="utf-8")\n tmp.replace(p)\n';
 const child=spawn(python,['-c',source,moduleDir,store.recordsPath],{stdio:['pipe','pipe','pipe'],windowsHide:true});
 let stderr='';child.stderr.on('data',chunk=>stderr+=chunk);const done=new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error(stderr)));});
 await new Promise((resolve,reject)=>{child.stdout.once('data',()=>resolve());child.once('error',reject);});
 assert.throws(()=>persistFeedback('one',body,new Set(['one']),store),{status:409});child.stdin.end('\n');await done;
 persistFeedback('one',body,new Set(['one']),store);const state=JSON.parse(fs.readFileSync(store.recordsPath));assert.equal(state.figures.one.userFeedback.text,'调整图例');assert.equal(state.figures.two.review,'publisher-update');assert.equal(fs.existsSync(store.recordsPath+'.feedback.lock'),false);
});
