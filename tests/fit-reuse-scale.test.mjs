import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import test from 'node:test';
import {fileURLToPath} from 'node:url';
const repo=fileURLToPath(new URL('..',import.meta.url));
function harness(width){
 const original={version:1,figureId:'fexample',sourceHash:'a'.repeat(64),route:'rebuild',widthMm:80,fontSize:8,graph:{fontSize:8,widthClass:'single',nodes:[]}};
 const files=new Map([['original.json',original]]),cache=new Map(),calls=[];
 function render(root,file){const p=files.get(file),key=JSON.stringify(p);if(cache.has(key))return {...cache.get(key),cached:true};calls.push(p.uniformScaleFrom?'scale':p.fontSize);const actual=p.uniformScaleFrom?width*p.uniformScaleFrom.factor:width*(p.fontSize/8);const result={ok:true,planHash:key,planFile:file,ai:'first.ai',aiHash:'b'.repeat(64),recordFile:'first-render.json',adobe:{snapshot:{artboard:[0,300,actual*72/25.4,0],texts:[{size:p.fontSize}]},mechanicalIssues:[]}};cache.set(key,result);return result;}
 render('job','original.json');calls.length=0;
 let source=fs.readFileSync(repo+'/production-runtime/lib/fit.mjs','utf8').replace(/^import.*;\r?\n/gm,'').replace('export function fit','function fit');
 const fit=Function('path','readJson','writeJson','logEvent','render','withAdobeSession',source+';return fit;')(path,f=>structuredClone(files.get(f)),(f,p)=>files.set(f,p),()=>{},render,(_,fn)=>fn());
 return {fit:()=>fit('job','original.json'),calls,files,original};
}
test('existing 8pt is reused; oversize uses one uniform scale and repeat uses cache',()=>{const h=harness(86.6125),first=h.fit();assert.deepEqual(h.calls,['scale']);assert.ok(first.decision.fontSize>7&&first.decision.fontSize<8);assert.equal(first.decision.widthMm,80);h.fit();assert.deepEqual(h.calls,['scale']);});
test('existing 8pt fitting column needs no native operation',()=>{const h=harness(79);h.fit();assert.deepEqual(h.calls,[]);});
test('scale below 6pt stops for layout revision without 7pt/6pt redraw',()=>{const h=harness(120),r=h.fit();assert.equal(r.decision.reason,'layout_revision_required');assert.deepEqual(h.calls,[]);});

test('exactly six points is allowed after whole artwork scaling',()=>{const h=harness(80*8/6),r=h.fit();assert.equal(r.decision.fontSize,6);assert.deepEqual(h.calls,['scale']);});
