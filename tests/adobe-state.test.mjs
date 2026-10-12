import test from 'node:test';
import assert from 'node:assert/strict';
import {executionUncertain} from '../lib/adobe-state.mjs';
test('COM failure after a result was written still retains the lease',()=>{
 assert.equal(executionUncertain({}, {stage:'failed',detail:{during:'executing',number:-2147417851}},true),true);
});
test('A returned business error with a result permits normal release',()=>{
 assert.equal(executionUncertain({}, {stage:'failed',detail:{during:'returned'}},true),false);
});
test('Missing results, timeout and unclassified failures remain uncertain',()=>{
 assert.equal(executionUncertain({}, {stage:'failed',detail:{during:'returned'}},false),true);
 assert.equal(executionUncertain({code:'ETIMEDOUT'}, {stage:'failed',detail:{during:'returned'}},true),true);
 assert.equal(executionUncertain({},undefined,true),true);
});
