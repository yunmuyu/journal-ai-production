import {buildArticleProfiles} from './article-profile.mjs';
import {parameterCandidates} from './case-reuse.mjs';
import {normalizeMeasurements} from './measurement-evidence.mjs';
import {planIncremental} from './incremental-plan.mjs';
import {buildBatchPlan} from './queue.mjs';
import {articleReadiness} from './article-readiness.mjs';
import {isHash, uniqueMap} from './contracts.mjs';

/** One orchestration layer over existing inventory and records, never another state store. */
export function buildCandidateReports({inventory, records, evidence, context, verifyArtifact}) {
  const observations = evidence.observations;
  const observed = uniqueMap(observations, 'observation');
  const reports = {
    'article-profiles.json': buildArticleProfiles(inventory, observations),
    'batch-plan.json': buildBatchPlan({inventory, records, observations, context})
  };
  if (evidence.expected) reports['article-readiness.json'] = articleReadiness({inventory, records, expected: evidence.expected, verifyArtifact});
  if (evidence.measurements) reports['measurement-evidence.json'] = evidence.measurements.map(input => {
    const target = observed.get(input.figureId);
    if (target?.source?.matched !== true || !isHash(target.source.sha256)) throw Error('Measurement figure has no verified current source');
    return {figureId: target.id, evidence: normalizeMeasurements(input, target.source.sha256)};
  });
  if (evidence.incremental) reports['incremental-plan.json'] = planIncremental(evidence.incremental.nodes, evidence.incremental.previous || []);
  if (evidence.caseReuse) {
    const {library, indexFingerprint, retrievalByFigure} = evidence.caseReuse;
    reports['parameter-candidates.json'] = observations.map(item => ({id: item.id,
      ...parameterCandidates({library, indexFingerprint, retrieval: retrievalByFigure[item.id] || {matches: []},
        target: {...item, policyHash: context.policyHash, runtimeHash: context.runtimeHash}})}));
  }
  return reports;
}
