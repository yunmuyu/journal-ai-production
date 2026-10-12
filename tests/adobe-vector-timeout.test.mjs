import test from 'node:test';
import assert from 'node:assert/strict';
import {executionTimeoutMs,executionUncertain} from '../lib/adobe-state.mjs';
test('observed 465-second vector draw fits the controlled deadline',()=>{
 assert.ok(executionTimeoutMs({mode:'render',plan:{route:'vector-reletter'}})>465048);
});
test('other production deadlines retain the existing limits',()=>{
 assert.equal(executionTimeoutMs({mode:'aggregate'}),360000);
 assert.equal(executionTimeoutMs({mode:'trim'}),180000);
 assert.equal(executionTimeoutMs({mode:'render',plan:{route:'image'}}),180000);
});
test('longer vector deadline does not release uncertain executions',()=>{
 assert.equal(executionUncertain({code:'ETIMEDOUT'},null,false),true);
});
