import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync, spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {pythonRuntime} from '../lib/ingest.mjs';

const script=fileURLToPath(new URL('../scripts/prepare_visio_svg.py',import.meta.url));
const svg='http://www.w3.org/2000/svg';

test('Given a Visio marker path, when prepared, then line body is independent and source content survives',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'visio-prepare-'));
 try{
  const source=path.join(dir,'source.svg'),out=path.join(dir,'out.svg'),report=path.join(dir,'report.json');
  fs.writeFileSync(source,`<?xml version="1.0"?><!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd"><svg xmlns="${svg}" xmlns:xlink="http://www.w3.org/1999/xlink"><style>.arrow {marker-end:url(#a);stroke:blue;stroke-width:2;stroke-dasharray:1,2;stroke-linecap:round}.hidden {visibility:hidden;marker-end:url(#a);stroke:red}</style><defs><marker id="a"><path id="head" d="M0 0L1 1"/></marker></defs><g transform="translate(2,3)"><path id="wire" d="M0 0L10 10" class="arrow" transform="rotate(10)"/><path id="hide" d="M1 1L2 2" class="hidden"/><text>测试<tspan>123</tspan></text><image xlink:href="data:image/png;base64,AA=="/></g></svg>`);
  execFileSync(pythonRuntime(),['-X','utf8',script,source,out,report]);
  const result=JSON.parse(fs.readFileSync(report,'utf8'));
  assert.equal(result.prepared.length,1);
  assert.equal(result.prepared[0].sourceId,'wire');
  assert.equal(result.skippedHidden.length,1);
  const output=fs.readFileSync(out,'utf8');
  assert.match(output,/测试/);
  assert.match(output,/data:image\/png;base64,AA==/);
  assert.doesNotMatch(output,/DOCTYPE/);
  assert.match(output,/marker-end:none/);
  assert.match(output,/stroke-dasharray:1,2/);
  const second=path.join(dir,'second.svg'),secondReport=path.join(dir,'second.json');
  execFileSync(pythonRuntime(),['-X','utf8',script,out,second,secondReport]);
  assert.equal(JSON.parse(fs.readFileSync(secondReport,'utf8')).prepared.length,0);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});

test('Given unsupported CSS, when prepared, then risk is explicit and no speculative body is made',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'visio-prepare-'));
 try{
  const source=path.join(dir,'source.svg'),out=path.join(dir,'out.svg'),report=path.join(dir,'report.json');
  fs.writeFileSync(source,`<svg xmlns="${svg}"><style>g path {marker-end:url(#a);stroke:blue}</style><g><path id="p" d="M0 0L1 1"/></g></svg>`);
  execFileSync(pythonRuntime(),['-X','utf8',script,source,out,report]);
  const result=JSON.parse(fs.readFileSync(report,'utf8'));
  assert.equal(result.prepared.length,0);
  assert.ok(result.risks.some(r=>r.code==='unsupported-css'));
  assert.equal(fs.existsSync(out),true);
  const overwrite=spawnSync(pythonRuntime(),['-X','utf8',script,source,source,report]);
  assert.notEqual(overwrite.status,0);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});

test('Given comments, gradients and partial opacity, when prepared, then risky geometry is skipped and review is required',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'visio-prepare-'));
 try{
  const source=path.join(dir,'source.svg'),out=path.join(dir,'out.svg'),report=path.join(dir,'report.json');
  fs.writeFileSync(source,`<svg xmlns="${svg}"><!-- exported comment --><style>.arrow {marker-end:url(#a);stroke:#123;stroke-opacity:.5}</style><defs><linearGradient id="grad"/></defs><g><path id="p" class="arrow" stroke="none" d="M0 0L1 1"/></g></svg>`);
  execFileSync(pythonRuntime(),['-X','utf8',script,source,out,report]);
  const result=JSON.parse(fs.readFileSync(report,'utf8'));
  assert.equal(result.prepared.length,0);
  assert.equal(result.productionCompatibility,'needs_review');
  assert.ok(result.risks.some(r=>r.code==='partial-opacity'));
  assert.ok(result.risks.some(r=>r.code==='unsupported-structure'));
  assert.match(fs.readFileSync(out,'utf8'),/exported comment/);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
