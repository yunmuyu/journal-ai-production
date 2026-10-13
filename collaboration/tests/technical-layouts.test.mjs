import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {validateTechnical}=require('../../production-runtime/flowchart/scripts/technical-schema.cjs');
const code=fs.readFileSync(new URL('../../production-runtime/flowchart/assets/technical-layouts.jsx',import.meta.url),'utf8');
function draw(g){validateTechnical(g);const calls=[];const ctx={JFW:{}};vm.runInNewContext(code,ctx);const api={measure:s=>({w:Math.max(...s.split('\r').map(x=>x.length*4)),h:s.split('\r').length*8})};for(const k of ['text','node','line','image'])api[k]=(...args)=>calls.push({kind:k,args});ctx.JFW.drawTechnicalLayout(g,api,226);return calls;}
const base={schemaVersion:3,kind:'technical',fontSize:8};
test('memory boundaries reject out-of-order addresses and emit all source labels',()=>{const g={...base,layout:'memoryMap',title:'FLASH',boundaries:[{text:'0x400000',position:0},{text:'0x500000',position:.35},{text:'0x7D4000',position:1}],regions:['BootLoader','APP']};const c=draw(g);for(const text of ['FLASH','0x400000','0x500000','0x7D4000','BootLoader','APP'])assert.equal(c.filter(x=>x.kind==='text'&&x.args[1]===text).length,1);g.boundaries[1].position=1;assert.throws(()=>validateTechnical(g),/order/);});
test('sequence keeps message order and separates adjacent response/request ink',()=>{const g={...base,layout:'sequence',participants:['Client','Server','Flash'],steps:[{name:'one',request:'0x10 03',response:'0x50 03'},{name:'two',request:'0x22 F1',response:'0x62 F1',operation:'write'}]};const c=draw(g);const label=id=>c.find(x=>x.kind==='text'&&x.args[0]===id).args;assert.equal(label('request-0')[1],'0x10 03');assert.equal(label('response-1')[1],'0x62 F1');assert.ok(label('response-0')[3]-label('request-1')[3]>=11);assert.equal(c.filter(x=>x.kind==='line'&&x.args[0]==='operation-1').length,1);});
test('photo comparison preserves source images and requires source hashes',()=>{const image={path:'photo.png',sha256:'a'.repeat(64)};const panel=title=>({title,image,sections:[{title:'feature',text:'original'}]});const g={...base,layout:'photoComparison',title:'Compare',panels:[panel('left'),panel('right')]};assert.equal(draw(g).filter(x=>x.kind==='image').length,2);g.panels[0].image={path:'photo.png'};assert.throws(()=>validateTechnical(g),/SHA-256/);});
test('horizontal photo tree retains left root, stacked photos and six right leaves',()=>{
 const panel=title=>({title,image:{path:title+'.png',sha256:'a'.repeat(64)},sections:['a','b','c'].map(title=>({title,text:'detail'}))});
 const calls=draw({...base,fontSize:6,layout:'photoComparison',orientation:'horizontal',title:'Root',panels:[panel('first'),panel('second')]});
 const root=calls.find(x=>x.kind==='node'&&x.args[0]==='comparison-title').args;
 const photos=calls.filter(x=>x.kind==='image');const leaves=calls.filter(x=>x.kind==='node'&&x.args[0].startsWith('section-'));
 assert.equal(photos.length,2);assert.equal(leaves.length,6);assert.ok(photos[0].args[3]<photos[1].args[3]);
 for(const p of photos){assert.ok(p.args[2]>root[3]);assert.ok(p.args[5]>0);for(const leaf of leaves)assert.ok(leaf.args[3]>p.args[2]);}
});
test('vertical phase labels reserve measured ink plus clearance before bracket',()=>{const c=draw({...base,layout:'sequence',participants:['Client','Server','Flash'],steps:[{name:'one',request:'10',response:'50'}],phases:[{text:'准备阶段',first:0,last:0}]});const t=c.find(x=>x.kind==='text'&&x.args[0]==='phase-label-0').args,b=c.find(x=>x.kind==='line'&&x.args[0]==='phase-0').args[1];assert.ok(b[1][0]-(t[2]+2)>=3,'phase bracket must clear measured text by 3pt');});
