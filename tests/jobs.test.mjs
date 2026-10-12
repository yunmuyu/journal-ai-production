import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync,mkdirSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {addFigure} from '../lib/jobs.mjs';
import {pairReferences} from '../lib/ingest.mjs';
test('content replacement retains object identity and invalidates prior revision',()=>{
 const root=mkdtempSync(path.join(tmpdir(),'jfw-identity-'));
 try{const source=path.join(root,'source.png');writeFileSync(source,'one');const meta={source,author:'A',number:1,article:'article',objectKey:'p:7',identityName:'word/media/image1.png'};const first=addFigure(root,meta);assert.equal(addFigure(root,meta).revision,1);writeFileSync(source,'two');const second=addFigure(root,meta);assert.equal(second.id,first.id);assert.equal(second.revision,2);assert.equal(second.status,'awaiting_plan');assert.notEqual(second.sourceHash,first.sourceHash);const cropped=addFigure(root,{...meta,crop:[0,0.1,0,0]});assert.equal(cropped.revision,3);}finally{rmSync(root,{recursive:true});}
});
test('duplicate author figure numbers are not paired by list order',()=>{
 const root=mkdtempSync(path.join(tmpdir(),'jfw-pair-'));
 try{const source=path.join(root,'source.png');writeFileSync(source,'source');for(const objectKey of ['p:3','p:9'])addFigure(root,{source,author:'Author',number:7,article:'article',objectKey});const ref=path.join(root,'Author-图7.pdf');writeFileSync(ref,'reference');const r=pairReferences(root,[ref]);assert.equal(r.pairs.length,0);assert.equal(r.pending[0].candidates.length,2);}finally{rmSync(root,{recursive:true});}
});

test('caption-only updates preserve a reviewed unchanged render',()=>{
 const root=mkdtempSync(path.join(tmpdir(),'jfw-metadata-'));
 try{
  const source=path.join(root,'source.png');writeFileSync(source,'unchanged artwork');
  const meta={source,author:'A',number:1,article:'article',objectKey:'p:7',caption:'old'};
  const first=addFigure(root,meta);
  const state=JSON.parse(readFileSync(path.join(root,'job.json'),'utf8'));state.figures[0].status='accepted';state.figures[0].render='renders/existing/render.json';state.figures[0].review={decision:'pass',outputHash:'unchanged'};writeFileSync(path.join(root,'job.json'),JSON.stringify(state));
  const updated=addFigure(root,{...meta,caption:'new'});
  assert.equal(updated.caption,'new');assert.equal(updated.revision,first.revision);
  assert.equal(updated.status,'accepted');assert.equal(updated.render,'renders/existing/render.json');assert.deepEqual(updated.review,{decision:'pass',outputHash:'unchanged'});
 }finally{rmSync(root,{recursive:true});}
});
