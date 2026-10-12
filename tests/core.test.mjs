import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { figureId, validatePlan, reviewMatches, resolveInside } from '../lib/core.mjs';

const plan = () => ({version:1,figureId:'f123',sourceHash:'a'.repeat(64),route:'raster-reletter',widthMm:80,fontSize:8,rasterEditRationale:"white margin outside plot",masks:[],texts:[],protectedRegions:[[0.1,0.2,0.8,0.5]]});
test('duplicate figure captions have distinct stable identities by object position',()=>{
 assert.notEqual(figureId('article.docx',15,'same'),figureId('article.docx',99,'same'));
 assert.equal(figureId('article.docx',15,'same'),figureId('article.docx',15,'same'));
});
test('mask touching protected plot fails before Adobe execution',()=>{
 const p=plan(); p.masks=[{rect:[0.2,0.3,0.1,0.1],gray:100}];
 assert.throws(()=>validatePlan(p),/protected/);
 p.masks=[{rect:[0,0,0.1,0.1],gray:100}]; assert.doesNotThrow(()=>validatePlan(p));
});
test('a stale visual approval does not authorize a different revision',()=>{
 assert.equal(reviewMatches({planHash:'a',outputHash:'b',decision:'pass'},'a','b'),true);
 assert.equal(reviewMatches({planHash:'a',outputHash:'b',decision:'pass'},'a','c'),false);
});
test('paths outside a job and absolute paths are rejected',()=>{
 const root=mkdtempSync(join(tmpdir(),'jfw-test-'));
 try{writeFileSync(join(root,'a.png'),'fixture');assert.equal(resolveInside(root,'a.png'),join(root,'a.png'));assert.throws(()=>resolveInside(root,'../a.png'),/outside/);assert.throws(()=>resolveInside(root,'C:/other.png'),/absolute/);}finally{rmSync(root,{recursive:true});}
});
test('invalid typography is rejected and fractional sizes are allowed',()=>{
 const p=plan();p.fontSize=0;assert.throws(()=>validatePlan(p),/6 to 8 pt/);
 for(const size of [6,6.2911,7.96,8]){p.fontSize=size;assert.doesNotThrow(()=>validatePlan(p));}
 for(const size of [5.99,8.01]){p.fontSize=size;assert.throws(()=>validatePlan(p),/6 to 8 pt/);}p.fontSize=8;p.texts=[{text:'x',x:NaN,y:0.5}];assert.throws(()=>validatePlan(p),/finite/);
});
test('source formula labels support finite oblique rotation before rendering',()=>{
 const p=plan();p.texts=[{text:'w·x-b=0',x:0.5,y:0.5,rotation:45}];
 assert.doesNotThrow(()=>validatePlan(p));
 for(const rotation of [NaN,Infinity,-181,181,'45']){p.texts[0].rotation=rotation;assert.throws(()=>validatePlan(p),/rotation/);}
});
