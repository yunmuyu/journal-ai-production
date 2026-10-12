import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {updateAggregate} from '../lib/aggregate-update.mjs';
import {fileHash} from '../lib/core.mjs';
function fixture(){const root=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-incremental-'));const ai=root+'/base.ai',pdf=root+'/base.pdf',replacement=root+'/new.ai';fs.writeFileSync(ai,'author with human edits');fs.writeFileSync(pdf,'old pdf');fs.writeFileSync(replacement,'updated figure');return {root,ai,pdf,replacement,base:{ai,pdf,aiHash:fileHash(ai),pdfHash:fileHash(pdf),placements:[{name:'A-图1',page:1,artboardIndex:0}],pages:1},changes:[{name:'A-图1',ai:replacement,sha256:fileHash(replacement)}]};}
test('source version conflicts never enter Adobe or overwrite the author file',()=>{const f=fixture();try{fs.appendFileSync(f.ai,'manual save');const before=fs.readFileSync(f.ai);assert.throws(()=>updateAggregate(f.root,f.base,f.changes,{invoke(){assert.fail('Adobe must not execute');}}),/base.*revision/i);assert.deepEqual(fs.readFileSync(f.ai),before);}finally{fs.rmSync(f.root,{recursive:true});}});
test('unknown figure identity and changed replacement reject before Adobe',()=>{const f=fixture();try{assert.throws(()=>updateAggregate(f.root,f.base,[{...f.changes[0],name:'wrong'}],{invoke(){assert.fail('Adobe must not execute');}}),/identity/);fs.appendFileSync(f.replacement,'changed');assert.throws(()=>updateAggregate(f.root,f.base,f.changes,{invoke(){assert.fail('Adobe must not execute');}}),/replacement.*revision/i);}finally{fs.rmSync(f.root,{recursive:true});}});
