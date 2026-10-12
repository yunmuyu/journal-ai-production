import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {mapLocalPath, readLocalJson} from '../lib/local-paths.mjs';
import {readJson} from '../lib/core.mjs';

test('local path mapping is opt in, exact and prefix bounded', () => {
 const root = mkdtempSync(path.join(tmpdir(), 'jfw-map-'));
 const previous = process.env.JFW_PATH_MAP_FILE;
 try {
  const mappingFile = path.join(root, 'mapping.json');
  const mapped = path.join(root, 'item.json');
  writeFileSync(mappingFile, JSON.stringify({mappings:[['E:/family',root],['E:/family/sub',path.join(root,'special')]]}));
  writeFileSync(mapped, JSON.stringify({source:'E:/family/figure.ai', nested:{source:'E:/family/sub/figure.ai'}, hash:'a'.repeat(64), other:'E:/familyish/figure.ai'}));
  delete process.env.JFW_PATH_MAP_FILE;
  assert.equal(mapLocalPath('E:/family/figure.ai'), 'E:/family/figure.ai');
  process.env.JFW_PATH_MAP_FILE = mappingFile;
  assert.equal(mapLocalPath('E:/familyish/figure.ai'), 'E:/familyish/figure.ai');
  assert.equal(mapLocalPath('E:/family/sub/figure.ai'), path.join(root,'special','figure.ai'));
  assert.equal(mapLocalPath(['E:','family','sub','figure.ai'].join(String.fromCharCode(92))), path.join(root,'special','figure.ai'));
  assert.equal(mapLocalPath('e:/FAMILY/figure.ai'), path.join(root,'figure.ai'));
  const value = readLocalJson('E:/family/item.json');
  assert.deepEqual(readJson('E:/family/item.json'), value);
  assert.equal(value.source,path.join(root,'figure.ai'));
  assert.equal(value.nested.source,path.join(root,'special','figure.ai'));
  assert.equal(value.hash,'a'.repeat(64));
  assert.equal(value.other,'E:/familyish/figure.ai');
 } finally {
  if (previous === undefined) delete process.env.JFW_PATH_MAP_FILE;
  else process.env.JFW_PATH_MAP_FILE = previous;
  rmSync(root,{recursive:true,force:true});
 }
});
