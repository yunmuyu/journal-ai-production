import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {pythonRuntime} from '../lib/ingest.mjs';
const packageRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const python=pythonRuntime();
test('one-pixel export rounding preserves dense source pixels without stretching',()=>{
 const output=execFileSync(python,['-c',[
  'from PIL import Image',
  'from scripts.audit_pdf import native_grid',
  'source=Image.new("L",(99,81),255)',
  'for x in range(0,99,2):',
  ' for y in range(81): source.putpixel((x,y),0)',
  'aligned=native_grid(source,(100,80))',
  'assert aligned.size==(100,80)',
  'assert aligned.crop((0,0,99,80)).tobytes()==source.crop((0,0,99,80)).tobytes()',
  'assert aligned.getpixel((99,40))==255',
  'assert source.size==(99,81)',
  'print("pixel-preserved")'
 ].join('\n')],{cwd:packageRoot,encoding:'utf8'});
 assert.equal(output.trim(),'pixel-preserved');
});
test('larger resolution differences keep the existing proportional resampling',()=>{
 const output=execFileSync(python,['-c',[
  'from PIL import Image',
  'from scripts.audit_pdf import native_grid',
  'source=Image.new("L",(40,30),128)',
  'assert native_grid(source,(80,60)).tobytes()==source.resize((80,60)).tobytes()',
  'print("resolution-preserved")'
 ].join('\n')],{cwd:packageRoot,encoding:'utf8'});
 assert.equal(output.trim(),'resolution-preserved');
});
test('three-pixel page-edge rounding preserves dense signal ink',()=>{
 const output=execFileSync(python,['-c',[
  'from PIL import Image',
  'from scripts.audit_pdf import native_grid',
  'source=Image.new("L",(928,742),255)',
  'for x in range(10,920,7):',
  ' for y in range(20,720): source.putpixel((x,y),0)',
  'aligned=native_grid(source,(925,742))',
  'assert aligned.tobytes()==source.crop((0,0,925,742)).tobytes()',
  'print("dense-ink-preserved")'
 ].join('\n')],{cwd:packageRoot,encoding:'utf8'});
 assert.equal(output.trim(),'dense-ink-preserved');
});
