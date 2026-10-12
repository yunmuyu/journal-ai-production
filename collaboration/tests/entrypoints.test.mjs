import * as childProcess from 'node:child_process';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, copyFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {repoRoot, readRelease} from '../scripts/common.mjs';
import {run} from '../scripts/run.mjs';
import {install} from '../scripts/install.mjs';

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), 'jfw-collaboration-'));
  const runtimePath = path.join(repoRoot, 'production-runtime');
  const configFile = path.join(root, 'machine.json');
  const workspaceRoot = path.join(root, 'jobs');
  const skillsRoot = path.join(root, 'skills');
  mkdirSync(workspaceRoot);
  writeFileSync(configFile, JSON.stringify({runtimePath, workspaceRoot, recordRoot: root, pathMapFile: path.join(root, 'map.json'), python: process.execPath, flowchartRoot: root, skillsRoot}));
  writeFileSync(path.join(root, 'map.json'), JSON.stringify({mappings: []}));
  return {root, runtimePath, configFile, workspaceRoot, skillsRoot};
}

test('status is read-only and passes configured environment', () => {
  const f = fixture();
  const job = path.join(f.workspaceRoot, 'one');
  mkdirSync(job);
  writeFileSync(path.join(job, 'job.json'), '{}');
  let called;
  assert.equal(run(['--config', f.configFile, 'status', 'one'], (...args) => { called = args; return {status: 0}; }), 0);
  assert.equal(called[1][1], 'status');
  assert.equal(called[1][2], job);
  assert.equal(called[2].env.JFW_KEEP_ILLUSTRATOR_DOCUMENTS, '1');
  assert.equal(called[2].cwd, f.workspaceRoot);
  assert.equal(called[2].env.JFW_PATH_MAP_FILE, path.join(f.root, 'map.json'));
  assert.equal(existsSync(path.join(job, 'tool-version-events.jsonl')), false);
});

test('mutating command records start and result including failure', () => {
  const f = fixture();
  const job = path.join(f.workspaceRoot, 'new-job');
  assert.equal(run(['--config', f.configFile, 'render', 'new-job', 'plan.json'], () => ({status: 3})), 3);
  const events = readFileSync(path.join(job, 'tool-version-events.jsonl'), 'utf8').trimEnd().split(/\r?\n/).map(JSON.parse);
  assert.deepEqual(events.map(e => e.event), ['start', 'result']);
  assert.equal(events[0].releaseId, readRelease().release.id);
  assert.equal(events[0].manifestHash, events[1].manifestHash);
  assert.deepEqual(events[0].args, ['plan.json']);
  assert.equal(events[0].planPath, path.join(f.workspaceRoot, 'plan.json'));
  assert.equal(events[0].job, job);
  assert.equal(events[1].exitCode, 3);
});

test('runtime drift refuses execution before touching job', () => {
  const f = fixture();
  const runtimePath = path.join(f.root, 'runtime');
  const {release} = readRelease();
  for (const item of release.files) {
    const dst = path.join(runtimePath, item.path);
    mkdirSync(path.dirname(dst), {recursive: true});
    copyFileSync(path.join(f.runtimePath, item.path), dst);
  }
  writeFileSync(path.join(runtimePath, release.files[0].path), 'tampered');
  const machine = JSON.parse(readFileSync(f.configFile, 'utf8'));
  machine.runtimePath = runtimePath;
  writeFileSync(f.configFile, JSON.stringify(machine));
  assert.throws(() => run(['--config', f.configFile, 'render', 'new-job', 'plan.json'], () => { throw Error('must not launch'); }), /hash mismatch/);
  assert.equal(existsSync(path.join(f.workspaceRoot, 'new-job')), false);
});

test('installer dry run makes no target; apply copies only release and backs up old file', () => {
  const f = fixture();
  const target = path.join(f.skillsRoot, 'journal-figure-workflow');
  const dry = install(['--config', f.configFile]);
  assert.equal(dry.mode, 'dry-run');
  assert.equal(existsSync(target), false);
  mkdirSync(path.join(target, 'runtime', 'adobe'), {recursive: true});
  writeFileSync(path.join(target, 'runtime', 'adobe', 'common.jsx'), 'old');
  writeFileSync(path.join(target, 'extra.txt'), 'keep');
  const applied = install(['--config', f.configFile, '--apply']);
  assert.equal(applied.mode, 'apply');
  assert.equal(readFileSync(path.join(applied.backup, 'runtime', 'adobe', 'common.jsx'), 'utf8'), 'old');
  assert.equal(readFileSync(path.join(target, 'extra.txt'), 'utf8'), 'keep');
  const receipt = JSON.parse(readFileSync(applied.receiptFile, 'utf8'));
  assert.equal(receipt.releaseId, readRelease().release.id);
  assert.equal(receipt.files.length, dry.count);
  assert.equal(readdirSync(path.join(target, 'runtime')).length > 0, true);
});

test('workRoot takes precedence and direct CLI status leaves no event', () => {
  const f = fixture();
  const workRoot = path.join(f.root, 'new-work');
  const job = path.join(workRoot, 'two');
  mkdirSync(job, {recursive: true});
  writeFileSync(path.join(job, 'job.json'), '{"state":"ready"}');
  const machine = JSON.parse(readFileSync(f.configFile, 'utf8'));
  machine.workRoot = workRoot;
  writeFileSync(f.configFile, JSON.stringify(machine));
  let resolved;
  run(['--config', f.configFile, 'status', 'two'], (_exe, args) => { resolved = args[2]; return {status: 0}; });
  assert.equal(resolved, job);
  const {spawnSync} = childProcess;
  const result = spawnSync(process.execPath, [path.join(repoRoot, 'collaboration', 'scripts', 'run.mjs'), '--config', f.configFile, 'status', 'two'], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /ready/);
  assert.equal(existsSync(path.join(job, 'tool-version-events.jsonl')), false);
});
