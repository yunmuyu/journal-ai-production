import {canonical, isHash, requireHash} from './contracts.mjs';

const allowed = new Set(['fontFamilyMap', 'strokeWidthPt', 'labelClearancePt']);
function validParameter(key, value) {
  if (key === 'fontFamilyMap') return value && Object.getPrototypeOf(value) === Object.prototype &&
    Object.keys(value).length > 0 && Object.entries(value).every(([k, v]) => k.trim() && typeof v === 'string' && v.trim());
  if (key === 'strokeWidthPt') return value === 0.5;
  return Number.isFinite(value) && value > 0 && value <= 100;
}
/** Wraps retrieveCases output; does not replace retrieval or learn rules from draft feedback. */
export function parameterCandidates({retrieval, library, indexFingerprint, target}) {
  requireHash(indexFingerprint, 'indexFingerprint');
  const rejected = [], candidates = [];
  if (library?.sourceFingerprint !== indexFingerprint) return {advisoryOnly: true, candidates, rejected: ['stale-case-library']};
  if (target?.source?.matched !== true || !isHash(target.source.sha256)) return {advisoryOnly: true, candidates, rejected: ['source-unmatched']};
  const matches = new Map((retrieval.matches || []).map(m => [m.id, m]));
  const counts = new Map();
  for (const entry of library.entries || []) counts.set(entry.caseId, (counts.get(entry.caseId) || 0) + 1);
  for (const entry of library.entries || []) {
    const match = matches.get(entry.caseId);
    const reason = !match ? 'not-retrieved' : counts.get(entry.caseId) > 1 ? 'duplicate-case' :
      entry.sourceVersion !== match.sourceVersion ? 'stale-source-version' :
      entry.accepted !== true || entry.evidenceVerified !== true || !isHash(entry.evidenceHash) ? 'unverified-case' :
      ['policyHash', 'runtimeHash', 'structureHash'].some(k => !isHash(target[k]) || entry[k] !== target[k]) ? 'incompatible-fingerprint' :
      !target.route || !target.source.format || entry.route !== target.route || entry.sourceFormat !== target.source.format ? 'incompatible-route' : null;
    if (reason) { rejected.push({caseId: entry.caseId, reason}); continue; }
    const parameters = {}, withheld = [];
    for (const [key, value] of Object.entries(entry.parameters || {})) {
      if (!allowed.has(key) || !validParameter(key, value)) { withheld.push({key, reason: 'not-approved-for-transfer'}); continue; }
      if (Object.hasOwn(target.userConstraints || {}, key)) { withheld.push({key, reason: 'explicit-user-constraint'}); continue; }
      parameters[key] = structuredClone(value);
    }
    if (Object.keys(parameters).length) candidates.push({caseId: entry.caseId, sourceVersion: match.sourceVersion,
      evidenceHash: entry.evidenceHash, parameters, withheld, requiresPreflight: true, requiresNativeReview: true});
    else rejected.push({caseId: entry.caseId, reason: 'no-transferable-parameters', withheld});
  }
  // Conflicting precedents must not silently choose a winner.
  const conflicts = [...allowed].filter(key => new Set(candidates.filter(c => Object.hasOwn(c.parameters, key)).map(c => canonical(c.parameters[key]))).size > 1);
  for (const candidate of candidates) for (const key of conflicts) {
    delete candidate.parameters[key]; candidate.withheld.push({key, reason: 'conflicting-precedents'});
  }
  return {advisoryOnly: true, candidates: candidates.filter(c => Object.keys(c.parameters).length), rejected, conflicts};
}
