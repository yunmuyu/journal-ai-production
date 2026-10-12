import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePlan} from '../lib/core.mjs';
const base={version:1,figureId:'ffont',sourceHash:'a'.repeat(64),route:'vector-reletter',widthMm:80,replacements:[]};
test('Editorial 6 to 8pt sizes include fractions',()=>{
 for(const size of [6,6.5,7,7.96,8])assert.equal(validatePlan({...base,fontSize:size}).fontSize,size);
 for(const size of [5,5.99,8.01,9,NaN])assert.throws(()=>validatePlan({...base,fontSize:size}));
});
test('Graph and outer plan cannot claim different font sizes',()=>{
 assert.throws(()=>validatePlan({...base,route:'rebuild',fontSize:8,graph:{fontSize:7}}));
});
