import test from 'node:test';
import assert from 'node:assert/strict';
import {catalogFor,belongsToBatch} from './batch-scope.mjs';
test('explicit second catalog never falls back to first batch',()=>{
 const a={batchHash:'a'},b={batchHash:'b'},config={catalog:a,catalogs:{b}};
 assert.equal(catalogFor(config,'b'),b);
 assert.equal(catalogFor(config),a);
 assert.throws(()=>catalogFor(config,'unknown'));
});
test('legacy task key and explicit batch identity isolate selection',()=>{
 assert.equal(belongsToBatch({key:'a:paper:1'},'b'),false);
 assert.equal(belongsToBatch({key:'b:paper:1'},'b'),true);
 assert.equal(belongsToBatch({batchHash:'b',key:'inventory'},'b'),true);
 assert.equal(belongsToBatch({key:'b:paper:1'},undefined),true);
});
