import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {inspectAcceptance,acceptanceMatches} from './acceptance.mjs';
test('同字节的交付图号、数量、路径变化也使验收绑定失效',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'acceptance-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const file=path.join(dir,'a.pdf'),copy=path.join(dir,'b.pdf');fs.writeFileSync(file,'pdf');fs.copyFileSync(file,copy);
 const figure={subfigures:[{number:'1.1',output:file}]},seen=inspectAcceptance('id',figure);
 assert.ok(seen.token);figure.userAcceptance={artifactToken:seen.token};assert.equal(acceptanceMatches(figure,seen),true);
 for(const parts of [[{number:'1.2',output:file}],[{number:'1.1',output:copy}],[{number:'1.1',output:file},{number:'1.2',output:copy}]]){
  figure.subfigures=parts;assert.equal(acceptanceMatches(figure,inspectAcceptance('id',figure)),false);
 }
 assert.equal(acceptanceMatches({userAcceptance:{accepted:true}},seen),true);
});
