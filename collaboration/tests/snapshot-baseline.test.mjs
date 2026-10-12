import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {snapshotBaseline} from '../scripts/snapshot-baseline.mjs';

const fixedCommit = 'a'.repeat(40);
function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), 'jfw-baseline-'));
  const codeRoot = path.join(root, 'repo');
  const productionRoot = path.join(root, 'production');
  const workspaceRoot = path.join(root, 'workspace');
  const recordRoot = path.join(root, 'records');
  for (const dir of [codeRoot, productionRoot, path.join(workspaceRoot, 'work', 'receive-family-old'), path.join(workspaceRoot, 'work', 'real-job'), recordRoot]) mkdirSync(dir, {recursive: true});
  writeFileSync(path.join(codeRoot, 'RELEASE.json'), JSON.stringify({id: 'test-release'}));
  writeFileSync(path.join(productionRoot, 'large.bin'), Buffer.alloc(1024 * 1024, 7));
  writeFileSync(path.join(workspaceRoot, 'work', 'receive-family-old', 'cached.txt'), 'exclude');
  writeFileSync(path.join(workspaceRoot, 'work', 'real-job', 'result.txt'), 'keep');
  writeFileSync(path.join(recordRoot, 'inventory.json'), JSON.stringify({figures: [{id: 'A-F1'}]}));
  writeFileSync(path.join(recordRoot, 'production-results.json'), JSON.stringify({articles: {'A': {}}, figures: {'A-F1': {status: '待终检'}}}));
  writeFileSync(path.join(recordRoot, 'author-templates.json'), '{}');
  writeFileSync(path.join(recordRoot, 'figure-classification.json'), '{}');
  const configFile = path.join(root, 'machine.json');
  writeFileSync(configFile, JSON.stringify({codeRoot, productionRoot, workspaceRoot, recordRoot, runtimePath: productionRoot, pathMapFile: path.join(root, 'map.json'), python: process.execPath, flowchartRoot: root}));
  return {root, configFile};
}

test('preview writes nothing; applied baseline keeps state and references without copying large files', () => {
  const f = fixture();
  const output = path.join(f.root, 'baseline');
  const args = ['--config', f.configFile, '--output', output];
  const preview = snapshotBaseline(args, () => fixedCommit);
  assert.equal(preview.mode, 'dry-run');
  assert.equal(existsSync(output), false);
  assert.equal(preview.fileCount, 2);
  const applied = snapshotBaseline([...args, '--apply'], () => fixedCommit);
  assert.equal(applied.status, 'pending-peer-confirmation');
  const manifest = JSON.parse(readFileSync(path.join(output, 'manifest.json'), 'utf8'));
  assert.equal(manifest.codeCommit, fixedCommit);
  assert.deepEqual(manifest.files.map(item => [item.scope, item.path]), [['production', 'large.bin'], ['workspace-work', 'real-job/result.txt']]);
  assert.equal(manifest.state.length, 4);
  assert.equal(JSON.parse(readFileSync(path.join(output, 'state', 'production-results.json'), 'utf8')).figures['A-F1'].status, '待终检');
  assert.deepEqual(JSON.parse(readFileSync(path.join(output, 'references.json'), 'utf8')).figureIds, ['A-F1']);
  assert.equal(JSON.parse(readFileSync(path.join(output, 'BASELINE-COMPLETE.json'), 'utf8')).status, 'pending-peer-confirmation');
  assert.equal(existsSync(path.join(output, 'large.bin')), false);
  assert.deepEqual(readdirSync(output).sort(), ['BASELINE-COMPLETE.json', 'manifest.json', 'references.json', 'state']);
  assert.throws(() => snapshotBaseline([...args, '--apply'], () => fixedCommit), /already exists/);
});

test('configured excludes omit matching work directories', () => {
  const f = fixture();
  const config = JSON.parse(readFileSync(f.configFile, 'utf8'));
  config.baselineExcludes = ['real-job'];
  writeFileSync(f.configFile, JSON.stringify(config));
  const preview = snapshotBaseline(['--config', f.configFile, '--output', path.join(f.root, 'next')], () => fixedCommit);
  assert.equal(preview.fileCount, 1);
});

test('output inside scanned scope is rejected before creation', () => {
  const f = fixture();
  const config = JSON.parse(readFileSync(f.configFile, 'utf8'));
  const output = path.join(config.workspaceRoot, 'work', 'baseline');
  assert.throws(() => snapshotBaseline(['--config', f.configFile, '--output', output, '--apply'], () => fixedCommit), /outside scanned scope/);
  assert.equal(existsSync(output), false);
});

test('independent configured work is included once and BOM JSON is accepted', () => {
  const f = fixture();
  const config = JSON.parse(readFileSync(f.configFile, 'utf8'));
  config.workRoot = path.join(f.root, 'new-work');
  mkdirSync(config.workRoot);
  writeFileSync(path.join(config.workRoot, 'new-result.txt'), 'new job');
  writeFileSync(f.configFile, '\uFEFF' + JSON.stringify(config));
  writeFileSync(path.join(config.codeRoot, 'RELEASE.json'), '\uFEFF' + JSON.stringify({id: 'test-release'}));
  writeFileSync(path.join(config.recordRoot, 'production-results.json'), '\uFEFF' + JSON.stringify({articles: {A: {}}, figures: {'A-F1': {}}}));
  const output = path.join(f.root, 'new-baseline');
  snapshotBaseline(['--config', f.configFile, '--output', output, '--apply'], () => fixedCommit);
  const manifest = JSON.parse(readFileSync(path.join(output, 'manifest.json'), 'utf8'));
  assert.equal(manifest.scopes['configured-work'], config.workRoot);
  assert.deepEqual(manifest.files.filter(item => item.path === 'new-result.txt').map(item => item.scope), ['configured-work']);
  assert.deepEqual(JSON.parse(readFileSync(path.join(output, 'references.json'), 'utf8')).figureIds, ['A-F1']);
  const nestedOutput = path.join(config.workRoot, 'baseline');
  assert.throws(() => snapshotBaseline(['--config', f.configFile, '--output', nestedOutput], () => fixedCommit), /outside scanned scope/);
});

test('configured work inside legacy work does not duplicate files', () => {
  const f = fixture();
  const config = JSON.parse(readFileSync(f.configFile, 'utf8'));
  config.workRoot = path.join(config.workspaceRoot, 'work', 'real-job');
  writeFileSync(f.configFile, JSON.stringify(config));
  const output = path.join(f.root, 'baseline');
  snapshotBaseline(['--config', f.configFile, '--output', output, '--apply'], () => fixedCommit);
  const manifest = JSON.parse(readFileSync(path.join(output, 'manifest.json'), 'utf8'));
  assert.equal(manifest.scopes['configured-work'], undefined);
  assert.deepEqual(manifest.files.filter(item => item.path.endsWith('result.txt')).map(item => item.scope), ['workspace-work']);
});
