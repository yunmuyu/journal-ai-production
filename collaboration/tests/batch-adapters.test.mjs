import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {bytesHash, digest, preflightBinding} from '../batch/contracts.mjs';
import {buildCandidateReports} from '../batch/reports.mjs';
import {createNativeAdapter} from '../batch/native-adapter.mjs';
import {buildBatchPlan, executeBatch} from '../batch/queue.mjs';
import {withCompleteArticles} from '../batch/article-readiness.mjs';
import {writeCandidateReports} from '../scripts/plan-batch.mjs';
import {runBatch} from '../scripts/run-batch.mjs';

const write = (file, value) => fs.writeFileSync(file, JSON.stringify(value));
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const fileHash = file => bytesHash(fs.readFileSync(file));
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jfw-adapter-test-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  const recordsRoot = path.join(root, 'records'), job = path.join(root, 'job');
  fs.mkdirSync(recordsRoot); fs.mkdirSync(job);
  const sourcePath = path.join(root, 'source.svg'); fs.writeFileSync(sourcePath, 'synthetic source bytes, not a production figure');
  const sourceHash = fileHash(sourcePath);
  const policyFile = path.join(root, 'policy.json'), releaseFile = path.join(root, 'release.json');
  write(policyFile, {test: 'policy'}); write(releaseFile, {test: 'release'});
  const context = {policyHash: fileHash(policyFile), runtimeHash: fileHash(releaseFile)};
  const inventory = {articles: [{id: 'article-1', author: 'Synthetic'}], figures: [{id: 'fig-1', articleId: 'article-1', number: '1'}]};
  const records = {figures: {'fig-1': {status: '待制作', productionDecision: {state: 'confirmed', revision: 1}}}};
  write(path.join(recordsRoot, 'inventory.json'), inventory); write(path.join(recordsRoot, 'production-results.json'), records);
  const nativePlan = {figureId: 'fig-1', sourceHash, route: 'vector-reletter', fontSize: 7.5, widthMm: 80, colorPolicy: 'grayscale',
    textGroups: [{id: 'label', lines: ['current label']}]};
  const planPath = path.join(root, 'plan.json'); write(planPath, nativePlan);
  const item = {id: 'fig-1', articleId: 'article-1', source: {matched: true, sha256: sourceHash, path: sourcePath, format: 'svg'},
    category: 'chart', route: nativePlan.route, job, plan: {path: planPath, sha256: fileHash(planPath)},
    strategy: {fontSizePt: 7.5, widthMm: 80, colorPolicy: 'grayscale'}, decisionHash: digest(records.figures['fig-1'].productionDecision)};
  item.preflight = {passed: true, binding: preflightBinding(item, context)};
  write(path.join(job, 'job.json'), {figures: [{id: 'fig-1', sourceHash}]});
  const machine = {workspaceRoot: root, recordRoot: recordsRoot};
  const plan = buildBatchPlan({inventory, records, observations: [item], context});
  function simulateRuntime(args) {
    assert.equal(args[2], 'render'); assert.equal(args[3], job); assert.equal(args[4], planPath);
    const savedPlan = path.join(job, 'saved-plan.json'); write(savedPlan, nativePlan);
    const record = {ok: true, figureId: item.id, sourceHash, planFile: savedPlan, planFileHash: fileHash(savedPlan)};
    for (const role of ['output', 'ai', 'preview']) {
      const file = path.join(job, `simulated-${role}.dat`); fs.writeFileSync(file, `test-only ${role}`);
      record[role] = file; record[role + 'Hash'] = fileHash(file);
    }
    write(path.join(job, 'render.json'), record);
    write(path.join(job, 'job.json'), {figures: [{id: item.id, sourceHash, render: 'render.json'}]});
    return 0;
  }
  return {root, recordsRoot, inventory, records, item, context, plan, nativePlan, policyFile, releaseFile, simulateRuntime,
    adapter: run => createNativeAdapter({machine, configFile: path.join(root, 'machine.json'), policyFile, releaseFile, run: run || simulateRuntime})};
}

test('candidate reports compose profile and queue without state mutation', t => {
  const f = fixture(t), before = structuredClone({inventory: f.inventory, records: f.records});
  const reports = buildCandidateReports({...f, evidence: {observations: [f.item]}});
  assert.equal(reports['article-profiles.json'][0].articleId, 'article-1');
  assert.equal(reports['batch-plan.json'].groups[0].items[0].id, 'fig-1');
  assert.deepEqual({inventory: f.inventory, records: f.records}, before);
});
test('candidate output directories are create-only', t => {
  const f = fixture(t), directory = path.join(f.root, 'reports');
  writeCandidateReports({'batch-plan.json': f.plan}, directory);
  const before = fs.readFileSync(path.join(directory, 'batch-plan.json'));
  assert.throws(() => writeCandidateReports({'batch-plan.json': {}}, directory));
  assert.deepEqual(fs.readFileSync(path.join(directory, 'batch-plan.json')), before);
});
test('adapter checks actual source, plan, job and authority files', t => {
  const f = fixture(t); assert.equal(f.adapter().revalidate(f.item, f.plan), true);
});
for (const [name, change] of [
  ['source bytes changed', f => fs.appendFileSync(f.item.source.path, 'change')],
  ['plan bytes changed', f => fs.appendFileSync(f.item.plan.path, ' ')],
  ['policy changed', f => fs.appendFileSync(f.policyFile, ' ')],
  ['release changed', f => fs.appendFileSync(f.releaseFile, ' ')],
  ['authority changed', f => { f.records.figures['fig-1'].userAcceptance = {accepted: true}; write(path.join(f.recordsRoot, 'production-results.json'), f.records); }],
  ['job identity changed', f => write(path.join(f.item.job, 'job.json'), {figures: []})]
]) test(`adapter refuses ${name}`, t => { const f = fixture(t); change(f); assert.throws(() => f.adapter().revalidate(f.item, f.plan)); });
test('adapter simulation uses fixed render entry and verifies actual artifact bytes', async t => {
  const f = fixture(t), adapter = f.adapter(); const result = await executeBatch(f.plan, adapter);
  assert.equal(result.results[0].status, 'succeeded');
  assert.equal(result.results[0].evidence.userAccepted, false);
  assert.equal(adapter.verifyPrevious(result.results[0], f.item, f.plan), true);
});
test('adapter simulation rejects output corruption during resume', async t => {
  const f = fixture(t), adapter = f.adapter(), result = await executeBatch(f.plan, adapter);
  fs.appendFileSync(result.results[0].evidence.files[0].path, 'modified');
  assert.equal(adapter.verifyPrevious(result.results[0], f.item, f.plan), false);
});
test('adapter rejects duplicate roles and altered render records', async t => {
  const f = fixture(t), adapter = f.adapter(), result = await executeBatch(f.plan, adapter), old = result.results[0];
  const modified = structuredClone(old); modified.evidence.files[2] = modified.evidence.files[0];
  assert.equal(adapter.verifyPrevious(modified, f.item, f.plan), false);
  fs.appendFileSync(old.evidence.recordFile, ' '); assert.equal(adapter.verifyPrevious(old, f.item, f.plan), false);
});
test('native nonzero return blocks lane without pretending host recovery', async t => {
  const f = fixture(t); const result = await executeBatch(f.plan, f.adapter(() => 1));
  assert.equal(result.results[0].status, 'failed'); assert.equal(result.results[0].resourceBlocked, true);
});
test('zero native return without verified result is not success', async t => {
  const f = fixture(t); const result = await executeBatch(f.plan, f.adapter(() => 0));
  assert.equal(result.results[0].status, 'failed');
});
test('completion gate prevents calling publisher for incomplete articles', t => {
  const f = fixture(t); let called = false;
  assert.throws(() => withCompleteArticles({inventory: f.inventory, records: f.records, expected: [], verifyArtifact: () => true}, () => { called = true; }));
  assert.equal(called, false);
});
test('completion gate delegates only after actual artifact hash verification', t => {
  const f = fixture(t), file = path.join(f.root, 'synthetic-output.dat'); fs.writeFileSync(file, 'output bytes');
  Object.assign(f.records.figures['fig-1'], {userAcceptance: {accepted: true}, status: '用户最终验收通过', output: file, outputHash: fileHash(file)});
  const expected = [{id: 'fig-1', articleId: 'article-1', numbers: ['1'], decisionHash: f.item.decisionHash}];
  const input = {inventory: f.inventory, records: f.records, expected, verifyArtifact: (p, h) => fileHash(p) === h};
  assert.equal(withCompleteArticles(input, () => 'existing-publisher'), 'existing-publisher');
  fs.appendFileSync(file, 'edit'); assert.throws(() => withCompleteArticles(input, () => assert.fail('must not publish')));
});
test('invalid CLI arguments rejected before loading machine or native runtime', async () => {
  await assert.rejects(runBatch(['--bad-option', 'x'])); await assert.rejects(runBatch([]));
});
for (const [name, change] of [['old font', p => p.fontSize = 6], ['old label', p => p.textGroups[0].lines[0] = 'old label']])
  test(`zero native return with ${name} record is rejected despite matching source hash`, async t => {
    const f = fixture(t);
    const result = await executeBatch(f.plan, f.adapter(args => {
      f.simulateRuntime(args); const file = path.join(f.item.job, 'render.json'), record = read(file), saved = read(record.planFile);
      change(saved); write(record.planFile, saved); record.planFileHash = fileHash(record.planFile); write(file, record); return 0;
    }));
    assert.equal(result.results[0].status, 'failed'); assert.match(result.results[0].reason, /plan binding/);
  });
test('adapter rejects artifact paths outside the job', async t => {
  const f = fixture(t);
  const result = await executeBatch(f.plan, f.adapter(args => {
    f.simulateRuntime(args); const file = path.join(f.item.job, 'render.json'), record = read(file);
    record.output = f.item.source.path; record.outputHash = f.item.source.sha256; write(file, record); return 0;
  }));
  assert.equal(result.results[0].status, 'failed');
});
test('resume supplies plan context to artifact verifier', async t => {
  const f = fixture(t), adapter = f.adapter(), first = await executeBatch(f.plan, adapter);
  const second = await executeBatch(f.plan, {...adapter, previous: first.results, execute: () => assert.fail('must reuse verified result')});
  assert.equal(second.results[0].reused, true);
});
