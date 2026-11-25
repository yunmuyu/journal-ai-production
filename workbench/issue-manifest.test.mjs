import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {loadNovemberData, loadWorkbenchInventory, scanIssueFolder} from './issue-manifest.mjs';

test('a november-data.js file still loads', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'nov-'));
  fs.writeFileSync(path.join(root, 'november-data.js'), 'window.NOVEMBER_DATA={authors:[{author:"甲",main:2,files:[{number:"1",url:"file:///a.pdf"}]}]}');
  const loaded = loadWorkbenchInventory({workbenchRoot: root, issueRoot: root});
  assert.equal(loaded.source, 'november-data.js');
  assert.equal(loaded.data.authors[0].main, 2);
  assert.equal(loadNovemberData(path.join(root, 'november-data.js')).authors[0].author, '甲');
});

test('an issue folder scan builds the same author list without november-data.js', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'issue-'));
  const author = path.join(root, '张三');
  fs.mkdirSync(author);
  fs.writeFileSync(path.join(author, '稿件.docx'), 'word');
  fs.writeFileSync(path.join(author, '张三-图1.pdf'), '%PDF');
  fs.writeFileSync(path.join(author, '张三-图1.2.jpg'), 'jpg');
  fs.writeFileSync(path.join(author, 'notes.txt'), 'skip');
  const scanned = scanIssueFolder(root);
  assert.equal(scanned.authors.length, 1);
  assert.equal(scanned.authors[0].author, '张三');
  assert.equal(scanned.authors[0].main, 1);
  assert.deepEqual(scanned.authors[0].files.map(file => file.number).sort(), ['1', '1.2']);
  const loaded = loadWorkbenchInventory({workbenchRoot: path.join(root, 'missing'), issueRoot: root});
  assert.equal(loaded.source, 'scan');
});
