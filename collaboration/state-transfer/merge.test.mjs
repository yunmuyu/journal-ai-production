import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {mergeDocuments, runCli} from './merge.mjs';

const production = figures => ({articles: {}, figures});
const inventory = figures => ({articles: [{id: 'A-1', author: '甲'}], figures});

test('Given distinct fields When two sides edit Then both changes survive by figure ID', () => {
  const base = production({'A-1-F1': {status: '待制作', review: ''}});
  const local = production({'A-1-F1': {status: '待制作', review: '用户意见'}});
  const incoming = production({'A-1-F1': {status: '内部复核通过', review: ''}});
  const result = mergeDocuments('production-results', base, local, incoming);
  assert.equal(result.conflictCount, 0);
  assert.deepEqual(result.merged.figures['A-1-F1'], {status: '内部复核通过', review: '用户意见'});
});

test('Given same field edits When values diverge Then conflict keeps local draft value', () => {
  const base = production({'A-1-F1': {output: 'old.pdf'}});
  const local = production({'A-1-F1': {output: 'local.pdf'}});
  const incoming = production({'A-1-F1': {output: 'incoming.pdf'}});
  const result = mergeDocuments('production-results', base, local, incoming);
  assert.equal(result.conflictCount, 1);
  assert.equal(result.conflicts[0].field, '$.figures.A-1-F1.output');
  assert.equal(result.merged.figures['A-1-F1'].output, 'local.pdf');
});

test('Given new figure and reordered rows When incoming adds Then identity wins over array order', () => {
  const base = inventory([{id: 'A-1-F1', caption: '旧'}, {id: 'A-1-F2', caption: '旧2'}]);
  const local = inventory([{id: 'A-1-F2', caption: '旧2'}, {id: 'A-1-F1', caption: '旧'}]);
  const incoming = inventory([{id: 'A-1-F1', caption: '旧'}, {id: 'A-1-F2', caption: '旧2'}, {id: 'A-1-F3', caption: '新增'}]);
  const result = mergeDocuments('inventory', base, local, incoming);
  assert.equal(result.conflictCount, 0);
  assert.deepEqual(result.merged.figures.map(row => row.id), ['A-1-F2', 'A-1-F1', 'A-1-F3']);
});

test('Given locally saved feedback When incoming changes production Then local feedback survives', () => {
  const base = production({'A-1-F1': {status: '待制作', output: 'old.pdf', userFeedback: {text: '', revision: 1}}});
  const local = production({'A-1-F1': {status: '待制作', output: 'old.pdf', userFeedback: {text: '请改单栏', revision: 2}}});
  const incoming = production({'A-1-F1': {status: '待制作', output: 'new.pdf', userFeedback: {text: '', revision: 1}}});
  const result = mergeDocuments('production-results', base, local, incoming);
  assert.equal(result.conflictCount, 0);
  assert.deepEqual(result.merged.figures['A-1-F1'].userFeedback, local.figures['A-1-F1'].userFeedback);
  assert.equal(result.merged.figures['A-1-F1'].output, 'new.pdf');
});

test('Given local acceptance and incoming new problem When different review fields change Then semantic conflict blocks apply', () => {
  const base = production({'A-1-F1': {status: '待终检', userFeedback: {text: '', accepted: false, revision: 1}, output: 'old.pdf'}});
  const local = production({'A-1-F1': {status: '用户最终验收通过', userFeedback: {text: '', accepted: true, revision: 2}, output: 'old.pdf'}});
  const incoming = production({'A-1-F1': {status: '待修订', userFeedback: {text: '仍有错字', accepted: false, revision: 2}, output: 'new.pdf'}});
  const result = mergeDocuments('production-results', base, local, incoming);
  assert.equal(result.conflicts.some(item => item.reason === 'acceptance-feedback-semantic-conflict'), true);
  assert.equal(result.merged.figures['A-1-F1'].status, '用户最终验收通过');
  assert.deepEqual(result.merged.figures['A-1-F1'].userFeedback, local.figures['A-1-F1'].userFeedback);
  assert.equal(result.merged.figures['A-1-F1'].output, 'new.pdf');
});

test('Given Word figure number F4-1 When acceptance and feedback diverge Then semantic conflict still applies', () => {
  const key = 'A-1-F4-1';
  const base = production({[key]: {status: '待终检', userFeedback: {text: ''}}});
  const local = production({[key]: {status: '用户最终验收通过', userFeedback: {text: ''}}});
  const incoming = production({[key]: {status: '待终检', userFeedback: {text: '需修图号'}}});
  const result = mergeDocuments('production-results', base, local, incoming);
  assert.equal(result.conflicts.some(item => item.reason === 'acceptance-feedback-semantic-conflict'), true);
});

test('Given incoming deletes an old figure When merging Then deletion needs review', () => {
  const base = production({'A-1-F1': {status: '待制作'}});
  const local = structuredClone(base);
  const incoming = production({});
  const result = mergeDocuments('production-results', base, local, incoming);
  assert.equal(result.conflicts[0].reason, 'deletion-requires-review');
  assert.deepEqual(result.merged.figures['A-1-F1'], local.figures['A-1-F1']);
});

test('Given duplicate IDs When inventory parsed Then reject before merge', () => {
  const duplicate = inventory([{id: 'A-1-F1'}, {id: 'A-1-F1'}]);
  assert.throws(() => mergeDocuments('inventory', duplicate, duplicate, duplicate), /duplicate id A-1-F1/);
});

test('Given classification cards When reordered and one added Then merge by card ID', () => {
  const base = {cards: [{id: 'F1', type: '统计'}, {id: 'F2', type: '框图'}], revision: 1};
  const local = {cards: [{id: 'F2', type: '框图'}, {id: 'F1', type: '统计'}], revision: 1};
  const incoming = {cards: [{id: 'F1', type: '统计'}, {id: 'F2', type: '框图'}, {id: 'F3', type: '截图'}], revision: 1};
  assert.deepEqual(mergeDocuments('figure-classification', base, local, incoming).merged.cards.map(card => card.id), ['F2', 'F1', 'F3']);
});

test('Given mapped family path When comparing the same artifact Then no false path conflict', () => {
  const base = production({'A-1-F1': {output: 'F:\\2026年10月\\old.pdf'}});
  const local = production({'A-1-F1': {output: 'C:/office/work/new.pdf'}});
  const incoming = production({'A-1-F1': {output: 'E:/family/work/new.pdf'}});
  const result = mergeDocuments('production-results', base, local, incoming, {pathMap: [['E:/family/work', 'C:/office/work']]});
  assert.equal(result.conflictCount, 0);
  assert.equal(result.merged.figures['A-1-F1'].output, local.figures['A-1-F1'].output);
});

test('Given unknown nested array changed on both sides When merging Then report conflict', () => {
  const base = {'A-1': {extra: ['old']}};
  const local = {'A-1': {extra: ['local']}};
  const incoming = {'A-1': {extra: ['incoming']}};
  const result = mergeDocuments('author-templates', base, local, incoming);
  assert.equal(result.conflictCount, 1);
  assert.match(result.conflicts[0].reason, /unkeyed array/);
});

test('Given conflicting change When apply requested Then no output is written', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'state-transfer-'));
  try {
    const inputs = [production({'A-1-F1': {status: 'old'}}), production({'A-1-F1': {status: 'local'}}), production({'A-1-F1': {status: 'incoming'}})];
    const names = ['base', 'local', 'incoming'].map((name, index) => {const file = path.join(dir, name + '.json'); fs.writeFileSync(file, JSON.stringify(inputs[index])); return file;});
    const output = path.join(dir, 'merged.json');
    const report = runCli(['--kind', 'production-results', '--base', names[0], '--local', names[1], '--incoming', names[2], '--apply', '--output', output]);
    assert.equal(report.applied, false);
    assert.equal(fs.existsSync(output), false);
    assert.throws(() => runCli(['--kind', 'production-results', '--base', names[0], '--local', names[1], '--incoming', names[2], '--apply', '--output', names[1]]), /output must differ/);
  } finally {fs.rmSync(dir, {recursive: true, force: true});}
});

test('Given UTF8 BOM JSON inputs When dry-run Then parse successfully without writing output', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'state-transfer-bom-'));
  try {
    const files = ['base', 'local', 'incoming'].map(name => {const file = path.join(dir, name + '.json'); fs.writeFileSync(file, '\uFEFF' + JSON.stringify(production({}))); return file;});
    const report = runCli(['--kind', 'production-results', '--base', files[0], '--local', files[1], '--incoming', files[2]]);
    assert.equal(report.conflictCount, 0);
    assert.equal(report.applied, false);
  } finally {fs.rmSync(dir, {recursive: true, force: true});}
});
