import {VERSION, digest, inventoryMaps, isHash, preflightBinding, protectedRecord, requireHash, uniqueMap} from './contracts.mjs';

const routes = new Set(['vector-reletter', 'raster-reletter', 'rebuild', 'chart-redraw', 'compose', 'image']);
function prepared(record) {
  return /内部复核通过|待终检/.test(record?.status || '') ||
    !!(record?.outputHash && record?.output && (record.reviewedAt && record.review || record.deliveryComplete === true ||
      record.normalRenderCompleted === true && record.internalReviewDecision === 'pass' ||
      /本图内部复核完成|已制作|制作完成|内部复核通过/.test(record.stage || record.status || '')));
}
export function buildBatchPlan({inventory, records, observations, context}) {
  const {figures} = inventoryMaps(inventory), observed = uniqueMap(observations, 'observation');
  for (const key of ['policyHash', 'runtimeHash']) requireHash(context[key], key);
  if (!records?.figures || Array.isArray(records.figures)) throw Error('Authoritative records.figures required');
  const groups = new Map(), excluded = [];
  for (const item of observed.values()) if (!figures.has(item.id) || figures.get(item.id).articleId !== item.articleId)
    throw Error(`Observation identity mismatch: ${item.id}`);
  for (const figure of figures.values()) {
    const item = observed.get(figure.id), record = records.figures[figure.id], decision = record?.productionDecision;
    let reason = protectedRecord(record) ? 'accepted-protected' : prepared(record) ? 'awaiting-user-review' :
      !item ? 'missing-observation' :
      item.source?.matched !== true || !isHash(item.source.sha256) ? 'source-unmatched' :
      !routes.has(item.route) || !item.category || /unknown|待判断|未知/i.test(item.category) ? 'route-or-category-unknown' :
      !item.source.format || !item.source.path || !item.job || !item.plan?.path || !isHash(item.plan.sha256) ? 'missing-execution-binding' :
      !decision || decision.state !== 'confirmed' || decision.stale === true ||
        Object.values(decision.attributes || {}).some(a => a?.state === 'needs-review' || a?.capacityCheck === 'conflict') ? 'decision-needs-review' :
      !isHash(item.decisionHash) || item.decisionHash !== digest(decision) ? 'stale-decision' :
      !item.strategy || !Number.isFinite(item.strategy.fontSizePt) || item.strategy.fontSizePt < 6 || item.strategy.fontSizePt > 8 ||
        !Number.isFinite(item.strategy.widthMm) || item.strategy.widthMm <= 0 || !item.strategy.colorPolicy ? 'invalid-strategy' : null;
    if (!reason) {
      const effective = {route: item.route, fontSizePt: item.strategy.fontSizePt, widthMm: item.strategy.widthMm, colorPolicy: item.strategy.colorPolicy};
      if (Object.keys(effective).some(key => Object.hasOwn(item.userConstraints || {}, key) && digest(item.userConstraints[key]) !== digest(effective[key]))) reason = 'explicit-user-constraint-conflict';
    }
    if (!reason && (item.preflight?.passed !== true || item.preflight.binding !== preflightBinding(item, context))) reason = 'preflight-missing-or-stale';
    if (reason) { excluded.push({id: figure.id, articleId: figure.articleId, reason}); continue; }
    const signature = {category: item.category, route: item.route, format: item.source.format,
      policyHash: context.policyHash, runtimeHash: context.runtimeHash, strategy: item.strategy,
      userConstraints: item.userConstraints || {}};
    const key = digest(signature);
    if (!groups.has(key)) groups.set(key, {id: key, signature, resource: 'adobe', items: []});
    const work = structuredClone(item);
    work.inputFingerprint = preflightBinding(item, context);
    groups.get(key).items.push(work);
  }
  const plan = {version: VERSION, context: structuredClone(context), authorityFingerprint: digest({inventory, records}),
    groups: [...groups.values()].sort((a, b) => a.id.localeCompare(b.id)).map(group =>
      ({...group, items: group.items.sort((a, b) => a.articleId.localeCompare(b.articleId) || a.id.localeCompare(b.id))})),
    excluded: excluded.sort((a, b) => a.id.localeCompare(b.id))};
  return {...plan, fingerprint: digest(plan)};
}
export function verifyBatchPlan(plan) {
  const {fingerprint, ...body} = plan;
  if (plan.version !== VERSION || digest(body) !== fingerprint) throw Error('Batch plan changed');
  const seen = new Set();
  for (const group of plan.groups) {
    if (group.resource !== 'adobe' || digest(group.signature) !== group.id) throw Error('Invalid batch group');
    for (const item of group.items) {
      if (seen.has(item.id)) throw Error('Duplicate work item');
      seen.add(item.id);
      if (digest({category: item.category, route: item.route, format: item.source.format,
        policyHash: plan.context.policyHash, runtimeHash: plan.context.runtimeHash, strategy: item.strategy,
        userConstraints: item.userConstraints || {}}) !== group.id) throw Error('Batch group membership changed');
      if (preflightBinding(item, plan.context) !== item.inputFingerprint || item.preflight?.binding !== item.inputFingerprint || item.preflight?.passed !== true)
        throw Error('Invalid item preflight binding');
    }
  }
}
/** One shared native lane. CPU SVG concurrency lives in the separate headless adapter. */
export async function executeBatch(plan, {execute, revalidate, previous = [], verifyPrevious, onEvent = () => {}, clock = () => performance.now()} = {}) {
  verifyBatchPlan(plan);
  if (typeof execute !== 'function' || typeof revalidate !== 'function') throw Error('Execution and live-state validator required');
  const prior = uniqueMap(previous, 'previous-result'), results = [], start = clock();
  let resourceBlocked = false;
  for (const group of plan.groups) for (const item of group.items) {
    const started = clock();
    let result = {id: item.id, articleId: item.articleId, inputFingerprint: item.inputFingerprint};
    if (resourceBlocked) result = {...result, status: 'blocked', reason: 'native-resource-blocked'};
    else {
      try {
        if (await revalidate(item, plan) !== true) throw Error('Live revalidation did not pass');
        const old = prior.get(item.id);
        if (old?.status === 'succeeded' && old.inputFingerprint === item.inputFingerprint && verifyPrevious && await verifyPrevious(old, item, plan)) {
          result = {...result, status: 'succeeded', reused: true, evidence: old.evidence};
        } else {
          await onEvent({event: 'start', ...result});
          const output = await execute(item, plan);
          if (!output || output.ok !== true) throw Error('Executor did not return a verified success');
          result = {...result, status: 'succeeded', reused: false, evidence: output};
        }
      } catch (error) {
        resourceBlocked = error?.blockResource === true;
        result = {...result, status: 'failed', reason: String(error?.message || error), resourceBlocked};
      }
    }
    result.durationMs = Math.max(0, clock() - started);
    results.push(result);
    await onEvent({event: 'result', ...result});
  }
  return {version: VERSION, planFingerprint: plan.fingerprint, results,
    durationMs: Math.max(0, clock() - start), nativeMaxConcurrency: 1, productionAcceptanceChanged: false};
}
