import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePlan} from '../lib/core.mjs';
const plan=replacements=>({version:1,figureId:'f_contract',sourceHash:'a'.repeat(64),route:'vector-reletter',fontSize:8,widthMm:80,replacements});
test('rejects invented from/to mappings before Adobe',()=>{assert.throws(()=>validatePlan(plan([{from:'投影互动',to:'摄影互动'}])),/invalid vector replacement/);});
test('requires valid index and both identity and replacement text',()=>{for(const r of [null,{index:-1,expected:'x',text:'y'},{index:.5,expected:'x',text:'y'},{index:0,text:'y'},{index:0,expected:'x',text:''}])assert.throws(()=>validatePlan(plan([r])),/invalid vector replacement/);});
test('permits overlays with no existing text and exact indexed replacements',()=>{validatePlan(plan([]));validatePlan(plan([{index:0,expected:'original',text:'corrected'}]));});
