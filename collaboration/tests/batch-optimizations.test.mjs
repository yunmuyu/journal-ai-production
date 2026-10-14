import test from 'node:test';
import assert from 'node:assert/strict';
import {canonical, digest, preflightBinding, bytesHash} from '../batch/contracts.mjs';
import {buildArticleProfiles} from '../batch/article-profile.mjs';
import {parameterCandidates} from '../batch/case-reuse.mjs';
import {normalizeMeasurements} from '../batch/measurement-evidence.mjs';
import {planIncremental} from '../batch/incremental-plan.mjs';
import {buildBatchPlan, executeBatch, verifyBatchPlan} from '../batch/queue.mjs';
import {articleReadiness} from '../batch/article-readiness.mjs';

const hash = s => bytesHash(String(s));
const clone = structuredClone;
function fixture() {
  const context = {policyHash: hash('policy'), runtimeHash: hash('runtime')};
  const inventory = {articles: [{id: 'a', author: 'Same Name'}, {id: 'b', author: 'Same Name'}],
    figures: [{id: 'a1', articleId: 'a', number: '1'}, {id: 'a2', articleId: 'a', number: '2'}, {id: 'b1', articleId: 'b', number: '1'}]};
  const records = {figures: Object.fromEntries(inventory.figures.map(f => [f.id, {status: '待制作', productionDecision: {state: 'confirmed', revision: 1}}]))};
  const observations = inventory.figures.map(f => {
    const item = {id: f.id, articleId: f.articleId, source: {matched: true, path: `${f.id}.svg`, format: 'svg', sha256: hash(f.id)},
      plan: {path: `${f.id}.json`, sha256: hash(`plan:${f.id}`)}, job: `jobs/${f.articleId}`, category: 'chart', route: 'vector-reletter',
      decisionHash: digest(records.figures[f.id].productionDecision), userConstraints: {},
      strategy: {fontSizePt: 8, widthMm: 80, colorPolicy: 'grayscale'},
      software: {name: 'Matplotlib', evidenceHash: hash('metadata')}, observedStyle: {fontFamily: 'Arial'}};
    item.preflight = {passed: true, binding: preflightBinding(item, context)};
    return item;
  });
  return {inventory, records, observations, context};
}
function measurement() {
  return {sourceHash: hash('source'), engineVersion: 'test-metrics-v1', kind: 'raster', unit: 'px', origin: 'top-left', dpi: 144,
    page: {width: 200, height: 100}, pageIndex: 0, uncertainty: 1,
    objects: [{id: 'ink1', bounds: {x: 10, y: 20, width: 30, height: 40}, editableText: true}]};
}
function reuseFixture() {
  const sourceVersion = hash('source-version'), indexFingerprint = hash('index');
  const target = {source: {matched: true, format: 'svg', sha256: hash('new-source')}, policyHash: hash('p'), runtimeHash: hash('r'),
    structureHash: hash('structure'), route: 'vector-reletter', userConstraints: {}};
  const entry = {caseId: 'old1', sourceVersion, accepted: true, evidenceVerified: true, evidenceHash: hash('evidence'),
    policyHash: target.policyHash, runtimeHash: target.runtimeHash, structureHash: target.structureHash,
    route: target.route, sourceFormat: 'svg', parameters: {fontFamilyMap: {Arial: 'Times New Roman'}, strokeWidthPt: 0.5, widthMm: 160, fontSize: 6, scale: 0.45}};
  return {target, indexFingerprint, retrieval: {matches: [{id: 'old1', sourceVersion}]}, library: {sourceFingerprint: indexFingerprint, entries: [entry]}};
}
function deliveryFixture() {
  const f = fixture();
  for (const figure of f.inventory.figures) Object.assign(f.records.figures[figure.id], {userAcceptance: {accepted: true}, status: '用户最终验收通过',
    number: figure.number, output: `${figure.id}.pdf`, outputHash: hash(`output:${figure.id}`)});
  const expected = f.inventory.figures.map(figure => ({id: figure.id, articleId: figure.articleId, numbers: [figure.number], decisionHash: digest(f.records.figures[figure.id].productionDecision)}));
  return {...f, expected, verifyArtifact: () => true};
}

test('canonical hashing is key-order independent', () => assert.equal(digest({b: 1, a: 2}), digest({a: 2, b: 1})));
for (const value of [NaN, Infinity, undefined, new Date(0), {v: undefined}]) test(`canonical rejects non-JSON ${String(value)}`, () => assert.throws(() => canonical(value)));
test('profiles keep same-name authors in separate articles', () => {
  const f = fixture(), result = buildArticleProfiles(f.inventory, f.observations);
  assert.equal(result.length, 2); assert.deepEqual(result[0].cohorts[0].figureIds, ['a1', 'a2']);
  assert.equal(result[0].automaticOverrides, false);
});
test('mixed software in one article creates separate cohorts', () => {
  const f = fixture(); f.observations[1].software.name = 'Visio';
  const result = buildArticleProfiles(f.inventory, f.observations);
  assert.equal(result[0].cohorts.length, 2); assert.deepEqual(result[0].cohorts[0].sharedObservations, {});
});
test('unknown source remains unknown, no inherited software', () => {
  const f = fixture(); f.observations[0].source.matched = false;
  const p = buildArticleProfiles(f.inventory, f.observations)[0];
  assert.deepEqual(p.unknownFigures, ['a1']); assert.equal(p.members[0].software, null);
});
test('software without metadata evidence is not asserted', () => {
  const f = fixture(); delete f.observations[0].software.evidenceHash;
  assert.equal(buildArticleProfiles(f.inventory, f.observations)[0].members[0].software, null);
});
test('profile fingerprint survives inventory order changes', () => {
  const f = fixture(), a = buildArticleProfiles(f.inventory, f.observations);
  f.inventory.figures.reverse(); f.observations.reverse();
  assert.deepEqual(a, buildArticleProfiles(f.inventory, f.observations));
});
test('profiles preserve explicit fractional font constraint and do not mutate inputs', () => {
  const f = fixture(); f.observations[0].userConstraints.fontSizePt = 7.5; const before = clone(f);
  const p = buildArticleProfiles(f.inventory, f.observations)[0];
  assert.equal(p.members[0].userConstraints.fontSizePt, 7.5); assert.deepEqual(f, before);
});
for (const [name, change] of [['duplicate figure', f => f.inventory.figures.push(clone(f.inventory.figures[0]))],
  ['wrong article', f => f.observations[0].articleId = 'b'], ['missing article', f => f.inventory.figures[0].articleId = 'missing']])
  test(`profile rejects ${name}`, () => { const f = fixture(); change(f); assert.throws(() => buildArticleProfiles(f.inventory, f.observations)); });

test('history transfers only safe parameters, never width/scale/font-size', () => {
  const result = parameterCandidates(reuseFixture());
  assert.deepEqual(Object.keys(result.candidates[0].parameters).sort(), ['fontFamilyMap', 'strokeWidthPt']);
  assert.equal(result.advisoryOnly, true); assert.equal(result.candidates[0].requiresPreflight, true);
});
for (const [name, mutate] of [
  ['stale index', f => f.library.sourceFingerprint = hash('stale')],
  ['unmatched source', f => f.target.source.matched = false],
  ['unaccepted draft', f => f.library.entries[0].accepted = false],
  ['unverified evidence', f => f.library.entries[0].evidenceVerified = false],
  ['stale source version', f => f.library.entries[0].sourceVersion = hash('old')],
  ['different policy', f => f.target.policyHash = hash('new-policy')],
  ['different runtime', f => f.target.runtimeHash = hash('new-runtime')],
  ['different structure', f => f.target.structureHash = hash('other-structure')],
  ['different route', f => f.target.route = 'rebuild'],
  ['different format', f => f.target.source.format = 'pdf'],
  ['duplicate registry case', f => f.library.entries.push(clone(f.library.entries[0]))]
]) test(`history rejects ${name}`, () => { const f = reuseFixture(); mutate(f); assert.equal(parameterCandidates(f).candidates.length, 0); });
test('history never overrides user constraints', () => {
  const f = reuseFixture(); f.target.userConstraints = {fontFamilyMap: {}, strokeWidthPt: 0.5};
  assert.equal(parameterCandidates(f).candidates.length, 0);
});
test('conflicting historical parameters have no automatic winner', () => {
  const f = reuseFixture(), second = {...clone(f.library.entries[0]), caseId: 'old2', parameters: {fontFamilyMap: {Arial: 'Other'}}};
  f.library.entries.push(second); f.retrieval.matches.push({id: 'old2', sourceVersion: second.sourceVersion});
  const result = parameterCandidates(f); assert.deepEqual(result.conflicts, ['fontFamilyMap']);
  assert.equal(result.candidates[0].parameters.fontFamilyMap, undefined);
});

test('pixel evidence normalized to points without inventing editable text', () => {
  const result = normalizeMeasurements(measurement(), hash('source'));
  assert.deepEqual(result.objects[0].boundsPt, {x: 5, y: 10, width: 15, height: 20});
  assert.equal(result.objects[0].editableText, false); assert.equal(result.semanticCompleteness, 'unverified');
});
test('bottom-left evidence is flipped exactly once', () => {
  const f = measurement(); f.origin = 'bottom-left';
  assert.equal(normalizeMeasurements(f, hash('source')).objects[0].boundsPt.y, 20);
});
for (const [name, mutate] of [
  ['stale source', f => f.sourceHash = hash('other')], ['missing DPI', f => delete f.dpi],
  ['unknown origin', f => delete f.origin], ['negative dimensions', f => f.objects[0].bounds.width = -1],
  ['nonfinite coordinates', f => f.objects[0].bounds.x = NaN], ['unproven semantic role', f => f.objects[0].role = 'label'],
  ['unjustified pixel precision', f => f.uncertainty = 0], ['duplicate object id', f => f.objects.push(clone(f.objects[0]))],
  ['missing page index', f => delete f.pageIndex]
]) test(`measurements reject ${name}`, () => { const f = measurement(); mutate(f); assert.throws(() => normalizeMeasurements(f, hash('source'))); });
test('out-of-page evidence is flagged, not silently clamped', () => {
  const f = measurement(); f.objects[0].bounds.x = -10;
  const out = normalizeMeasurements(f, hash('source')).objects[0]; assert.equal(out.clipped, true); assert.equal(out.boundsPt.x, -5);
});

function nodesFixture() {
  const nodes = [{id: 'a', inputHash: hash('a'), dependencies: []}, {id: 'b', inputHash: hash('b'), dependencies: ['a']}, {id: 'c', inputHash: hash('c'), dependencies: []}];
  const previous = planIncremental(nodes).items.map(n => ({id: n.id, signature: n.signature, outputHash: hash(`out:${n.id}`), frozen: false}));
  for (const node of nodes) node.currentOutputHash = hash(`out:${node.id}`);
  return {nodes, previous};
}
test('unchanged verified artifacts are reused', () => { const f = nodesFixture(); assert.ok(planIncremental(f.nodes, f.previous).items.every(n => n.action === 'reuse')); });
test('dependency change invalidates descendants but not unrelated figures', () => {
  const f = nodesFixture(); f.nodes[0].inputHash = hash('changed');
  assert.deepEqual(planIncremental(f.nodes, f.previous).items.map(n => n.action), ['rebuild-candidate', 'rebuild-candidate', 'reuse']);
});
test('tampered output invalidates downstream even when inputs are unchanged', () => {
  const f = nodesFixture(); f.nodes[0].currentOutputHash = hash('tamper');
  assert.equal(planIncremental(f.nodes, f.previous).items[1].action, 'rebuild-candidate');
});
test('frozen dirty node blocks itself and dependent rebuilds', () => {
  const f = nodesFixture(); f.previous[0].frozen = true; f.nodes[0].inputHash = hash('changed');
  assert.deepEqual(planIncremental(f.nodes, f.previous).items.map(n => n.action), ['blocked-copy-required', 'blocked-copy-required', 'reuse']);
});
test('shared group change cannot silently move an accepted sibling', () => {
  const f = nodesFixture(); f.nodes[0].sharedGroup = f.nodes[2].sharedGroup = 'same-artboard'; f.nodes[2].frozen = true;
  assert.ok(planIncremental(f.nodes, f.previous).items.every(n => n.action === 'blocked-copy-required'));
});
test('removed accepted artifacts are retained', () => { const f = nodesFixture(); f.nodes.pop(); assert.equal(planIncremental(f.nodes, f.previous).removed[0].action, 'retain-until-explicit-review'); });
for (const [name, mutate] of [['cycle', f => f.nodes[0].dependencies = ['b']], ['missing', f => f.nodes[0].dependencies = ['missing']], ['duplicate', f => f.nodes[0].dependencies = ['c', 'c']]])
  test(`invalid dependency ${name} rejected`, () => { const f = nodesFixture(); mutate(f); assert.throws(() => planIncremental(f.nodes, f.previous)); });

test('batch crosses article boundaries without losing article identities', () => {
  const p = buildBatchPlan(fixture()); assert.equal(p.groups.length, 1);
  assert.deepEqual(p.groups[0].items.map(i => i.articleId), ['a', 'a', 'b']); verifyBatchPlan(p);
});
test('same category with different formats gets separate batches', () => {
  const f = fixture(); f.observations[1].source.format = 'pdf'; f.observations[1].preflight.binding = preflightBinding(f.observations[1], f.context);
  assert.equal(buildBatchPlan(f).groups.length, 2);
});
test('fractional font size within current 6-8 pt rule is allowed', () => {
  const f = fixture(); f.observations[0].strategy.fontSizePt = 7.5; f.observations[0].preflight.binding = preflightBinding(f.observations[0], f.context);
  assert.equal(buildBatchPlan(f).excluded.length, 0);
});
for (const [name, mutate, reason] of [
  ['accepted', f => f.records.figures.a1.userAcceptance = {accepted: true}, 'accepted-protected'],
  ['pending user review', f => f.records.figures.a1.status = '内部复核通过', 'awaiting-user-review'],
  ['missing source', f => f.observations[0].source.matched = false, 'source-unmatched'],
  ['changed decision', f => f.records.figures.a1.productionDecision.revision++, 'stale-decision'],
  ['draft decision', f => f.records.figures.a1.productionDecision.state = 'draft', 'decision-needs-review'],
  ['missing preflight', f => delete f.observations[0].preflight, 'preflight-missing-or-stale'],
  ['changed source', f => f.observations[0].source.sha256 = hash('new'), 'preflight-missing-or-stale'],
  ['too-small font', f => f.observations[0].strategy.fontSizePt = 5.9, 'invalid-strategy'],
  ['unproven category', f => f.observations[0].category = 'unknown', 'route-or-category-unknown']
]) test(`batch excludes ${name}`, () => { const f = fixture(); mutate(f); assert.equal(buildBatchPlan(f).excluded.find(i => i.id === 'a1').reason, reason); });
test('batch plan tampering is detected', () => { const p = buildBatchPlan(fixture()); p.groups[0].items[0].job = 'other'; assert.throws(() => verifyBatchPlan(p)); });
test('native execution stays serial, isolates item failure and records times', async () => {
  const p = buildBatchPlan(fixture()); let active = 0, max = 0; const events = [];
  const report = await executeBatch(p, {revalidate: async () => true, onEvent: e => events.push(e), execute: async item => {
    active++; max = Math.max(max, active); await new Promise(resolve => setTimeout(resolve, 2)); active--;
    if (item.id === 'a2') throw Error('test failure'); return {ok: true};
  }});
  assert.equal(max, 1); assert.deepEqual(report.results.map(r => r.status), ['succeeded', 'failed', 'succeeded']);
  assert.ok(report.durationMs >= 0); assert.equal(events.filter(e => e.event === 'result').length, 3);
});
test('unconfirmed live-state revalidation never invokes executor', async () => {
  let calls = 0; const result = await executeBatch(buildBatchPlan(fixture()), {revalidate: () => false, execute: () => { calls++; return {ok: true}; }});
  assert.equal(calls, 0); assert.ok(result.results.every(r => r.status === 'failed'));
});
test('native resource blockage stops subsequent native work', async () => {
  const r = await executeBatch(buildBatchPlan(fixture()), {revalidate: () => true, execute: () => { throw Object.assign(Error('modal'), {blockResource: true}); }});
  assert.deepEqual(r.results.map(x => x.status), ['failed', 'blocked', 'blocked']);
});
test('retry skips only hash-revalidated successes, not merely old success labels', async () => {
  const p = buildBatchPlan(fixture()); let calls = 0;
  const previous = p.groups[0].items.map(i => ({id: i.id, inputFingerprint: i.inputFingerprint, status: 'succeeded', evidence: {ok: true}}));
  const options = {previous, revalidate: () => true, execute: () => { calls++; return {ok: true}; }};
  await executeBatch(p, {...options, verifyPrevious: () => true}); assert.equal(calls, 0);
  await executeBatch(p, options); assert.equal(calls, 3);
});
test('event persistence failure aborts execution', async () => {
  let calls = 0;
  await assert.rejects(executeBatch(buildBatchPlan(fixture()), {revalidate: () => true, execute: () => { calls++; return {ok: true}; },
    onEvent: () => { throw Error('disk full'); }})); assert.equal(calls, 0);
});

test('complete accepted articles become ready while same author names remain distinct', () => {
  const r = articleReadiness(deliveryFixture()); assert.deepEqual(r.readyArticleIds, ['a', 'b']); assert.equal(r.automaticPublication, false);
});
for (const [name, mutate, reason] of [
  ['missing expectation', f => f.expected.shift(), 'explicit-output-set-required'],
  ['missing acceptance', f => f.records.figures.a1.userAcceptance.accepted = false, 'explicit-final-acceptance-required'],
  ['stale expected split', f => f.expected[0].decisionHash = hash('old'), 'expected-output-decision-stale'],
  ['missing child', f => f.expected[0].numbers = ['1.1', '1.2'], 'incomplete-or-duplicate-output-set'],
  ['bad hash', f => f.records.figures.a1.outputHash = 'invalid', 'output-path-or-hash-missing'],
  ['file changed', f => f.verifyArtifact = p => p !== 'a1.pdf', 'artifact-missing-or-changed'],
  ['duplicate number', f => { f.records.figures.a2.number = '1'; f.expected[1].numbers = ['1']; }, 'duplicate-article-output-number']
]) test(`article delivery blocks ${name} without blocking unrelated article`, () => {
  const f = deliveryFixture(); mutate(f); const r = articleReadiness(f);
  assert.deepEqual(r.readyArticleIds, ['b']); assert.ok(r.articles[0].issues.some(i => i.reason === reason));
});
test('explicit subfigure set is required and verified in full', () => {
  const f = deliveryFixture(); f.expected[0].numbers = ['1.1', '1.2'];
  f.records.figures.a1.subfigures = ['1.1', '1.2'].map(number => ({number, output: `${number}.pdf`, outputHash: hash(number)}));
  assert.deepEqual(articleReadiness(f).readyArticleIds, ['a', 'b']);
  f.records.figures.a1.subfigures[1].userAcceptance = {accepted: false};
  assert.deepEqual(articleReadiness(f).readyArticleIds, ['b']);
});
test('style checks only compare declared cohorts and honor explicit exceptions', () => {
  const f = deliveryFixture(); f.expected[0].consistencyGroup = f.expected[1].consistencyGroup = 'charts';
  f.expected[0].styleHash = hash('8pt'); f.expected[1].styleHash = hash('7.5pt');
  assert.deepEqual(articleReadiness(f).readyArticleIds, ['b']);
  f.expected[1].explicitStyleException = true;
  assert.deepEqual(articleReadiness(f).readyArticleIds, ['a', 'b']);
});
test('async or truthy artifact verification is not silently treated as a pass', () => {
  const f = deliveryFixture(); f.verifyArtifact = () => Promise.resolve(true);
  assert.equal(articleReadiness(f).readyArticleIds.length, 0);
});
test('batch rejects explicit width conflict even with a fresh preflight stamp', () => {
  const f = fixture(); f.observations[0].userConstraints.widthMm = 160;
  f.observations[0].preflight.binding = preflightBinding(f.observations[0], f.context);
  assert.equal(buildBatchPlan(f).excluded.find(x => x.id === 'a1').reason, 'explicit-user-constraint-conflict');
});
test('batch membership cannot change by rehashing the outer plan', () => {
  const p = buildBatchPlan(fixture()); p.groups[0].signature.format = 'pdf'; p.groups[0].id = digest(p.groups[0].signature);
  const {fingerprint, ...body} = p; p.fingerprint = digest(body);
  assert.throws(() => verifyBatchPlan(p), /membership/);
});
test('history cannot bypass final 0.5 pt rule', () => {
  const f = reuseFixture(); f.library.entries[0].parameters.strokeWidthPt = 2;
  assert.equal(parameterCandidates(f).candidates[0].parameters.strokeWidthPt, undefined);
});
test('article readiness follows publisher number contract', () => {
  const f = deliveryFixture(); f.expected[0].numbers = ['not-a-number'];
  assert.deepEqual(articleReadiness(f).readyArticleIds, ['b']);
});
for (const [name, fields] of [['reviewed output', {reviewedAt: '2026-10-14', review: 'checked'}],
  ['completed stage', {stage: '本图内部复核完成'}], ['completed render', {normalRenderCompleted: true, internalReviewDecision: 'pass'}]])
  test(`batch preserves ${name} instead of repeating production`, () => {
    const f = fixture(); Object.assign(f.records.figures.a1, {output: 'already-produced.pdf', outputHash: hash('output')}, fields);
    assert.equal(buildBatchPlan(f).excluded.find(x => x.id === 'a1').reason, 'awaiting-user-review');
  });
