import {digest, explicitlyAccepted, inventoryMaps, isHash, uniqueMap} from './contracts.mjs';

/** Checks explicit expected outputs. No implicit single-figure fallback or author-name join. */
export function articleReadiness({inventory, records, expected, verifyArtifact}) {
  const {articles, figures} = inventoryMaps(inventory), specifications = uniqueMap(expected, 'expected-figure');
  if (typeof verifyArtifact !== 'function') throw Error('Actual artifact verifier required');
  for (const spec of specifications.values()) if (!figures.has(spec.id) || spec.articleId !== figures.get(spec.id).articleId)
    throw Error(`Expected-output identity mismatch: ${spec.id}`);
  const results = [];
  for (const article of articles.values()) {
    const issues = [], outputs = [], numbers = new Set(), cohortStyles = new Map();
    const members = [...figures.values()].filter(f => f.articleId === article.id);
    if (!members.length) issues.push({reason: 'article-has-no-registered-figures'});
    for (const figure of members) {
      const spec = specifications.get(figure.id), record = records.figures?.[figure.id];
      const issue = reason => issues.push({id: figure.id, reason});
      if (!spec || !Array.isArray(spec.numbers) || !spec.numbers.length || spec.numbers.some(n => typeof n !== 'string' || !/^(?:4-1|\d+(?:\.\d+)?)$/.test(n)) || new Set(spec.numbers).size !== spec.numbers.length) {
        issue('explicit-output-set-required'); continue;
      }
      if (!isHash(spec.decisionHash) || !record?.productionDecision || spec.decisionHash !== digest(record.productionDecision)) {
        issue('expected-output-decision-stale'); continue;
      }
      if (!explicitlyAccepted(record)) { issue('explicit-final-acceptance-required'); continue; }
      const parts = record.subfigures?.length ? record.subfigures : [record];
      const actual = parts.map(p => String(p.number ?? figure.number));
      if (new Set(actual).size !== actual.length || digest([...actual].sort()) !== digest([...spec.numbers].sort())) {
        issue('incomplete-or-duplicate-output-set'); continue;
      }
      for (const [index, part] of parts.entries()) {
        const number = actual[index];
        if (numbers.has(number)) { issue('duplicate-article-output-number'); continue; }
        numbers.add(number);
        if (part.userAcceptance?.accepted === false) { issue('child-acceptance-revoked'); continue; }
        if (!part.output || !isHash(part.outputHash)) { issue('output-path-or-hash-missing'); continue; }
        let verified = false;
        try { verified = verifyArtifact(part.output, part.outputHash, {id: figure.id, articleId: article.id, number}) === true; }
        catch { verified = false; }
        if (!verified) { issue('artifact-missing-or-changed'); continue; }
        outputs.push({id: figure.id, articleId: article.id, number, output: part.output, sha256: part.outputHash});
      }
      if (spec.consistencyGroup) {
        if (!isHash(spec.styleHash)) issue('consistency-style-evidence-missing');
        else if (spec.explicitStyleException !== true) {
          const prior = cohortStyles.get(spec.consistencyGroup);
          if (prior && prior !== spec.styleHash) issue('same-cohort-style-conflict');
          cohortStyles.set(spec.consistencyGroup, spec.styleHash);
        }
      }
    }
    results.push({articleId: article.id, ready: issues.length === 0, issues, outputs});
  }
  return {articles: results, readyArticleIds: results.filter(r => r.ready).map(r => r.articleId),
    blockedArticleIds: results.filter(r => !r.ready).map(r => r.articleId),
    authorityFingerprint: digest({inventory, records}), automaticPublication: false};
}
export function withCompleteArticles(input, publish) {
  const report = articleReadiness(input);
  if (report.blockedArticleIds.length) throw Object.assign(Error('Incomplete articles: ' + report.blockedArticleIds.join(', ')), {readiness: report});
  if (typeof publish !== 'function') throw Error('Existing delivery publisher required');
  return publish(report);
}
