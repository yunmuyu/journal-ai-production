import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';
import {inspectFigureInventory} from '../scripts/figure-inventory.mjs';

const entry = fileURLToPath(new URL('../journal.mjs', import.meta.url));
const articles = [{folder: '01 示例作者', author: '示例作者', numbers: ['1', '2.1', '2.2']}];

function fixture(t, names) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jfw-inventory-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  const folder = path.join(root, articles[0].folder);
  fs.mkdirSync(folder);
  for (const name of names) fs.writeFileSync(path.join(folder, name), 'x');
  return root;
}

test('CLI returns an ordered manifest from a numbered author folder', t => {
  const root = fixture(t, ['示例作者-图2.2.JPG', '示例作者-图1.pdf', '示例作者-图2.1.jpeg', '图2.pdf']);
  const expected = path.join(root, 'expected.json');
  fs.writeFileSync(expected, JSON.stringify(articles));
  const result = spawnSync(process.execPath, [entry, 'inventory', '--input', root, '--expected', expected], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.complete, true);
  assert.deepEqual(report.items.map(item => item.relative), [
    '01 示例作者/示例作者-图1.pdf', '01 示例作者/示例作者-图2.1.jpeg', '01 示例作者/示例作者-图2.2.JPG',
  ]);
  assert.equal(report.items[0].sha256, '2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881');
});

test('incomplete or ambiguous deliveries never emit placement items', t => {
  const root = fixture(t, ['示例作者-图1.pdf', '示例作者-图1.jpg', '示例作者-图2.pdf', '示例作者-图2.1.pdf']);
  const expected = path.join(root, 'expected.json');
  fs.writeFileSync(expected, JSON.stringify(articles));
  const result = spawnSync(process.execPath, [entry, 'inventory', '--input', root, '--expected', expected], {encoding: 'utf8'});
  assert.equal(result.status, 1, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.items, []);
  assert.deepEqual(report.issues.map(issue => [issue.kind, issue.number]).sort(), [
    ['duplicate', '1'], ['missing', '2.2'], ['mixed-main-and-subfigure', '2.1'], ['unexpected', '2'],
  ]);
});

test('rejects ambiguous expected numbers and paths outside the root', t => {
  const root = fixture(t, []);
  assert.throws(() => inspectFigureInventory(root, [{...articles[0], folder: '../outside'}]), /invalid.*folder/);
  assert.throws(() => inspectFigureInventory(root, [{...articles[0], numbers: ['2', '2.1']}]), /mixed main/);
});
