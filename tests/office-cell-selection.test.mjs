import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {convertOffice} from '../lib/convert.mjs';

test('explicit cell selection rejects invalid ranges before launching Office',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-cell-selection-'));
 try{
  for(const selection of [{sheet:0,range:'A1:B2'},{sheet:1,range:'A0:B2'},{sheet:1,range:'A1;anything'},{sheet:1.5,range:'A1:B2'}]){
   assert.throws(()=>convertOffice(root,'absent.xlsx',{cellSelection:selection}),/Invalid explicit Excel cell selection/);
  }
  assert.throws(()=>convertOffice(root,'absent.docx',{cellSelection:{sheet:1,range:'A1:B2'}}),/Invalid explicit Excel cell selection/);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
