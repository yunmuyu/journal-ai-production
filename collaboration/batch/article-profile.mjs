import {VERSION, digest, inventoryMaps, isHash, uniqueMap} from './contracts.mjs';

/** Read-only, rebuildable projection. Software and font roles are never inferred from author identity. */
export function buildArticleProfiles(inventory, observations) {
  const {articles, figures} = inventoryMaps(inventory);
  const observed = uniqueMap(observations, 'observation');
  for (const item of observed.values()) {
    const figure = figures.get(item.id);
    if (!figure || item.articleId !== figure.articleId) throw Error(`Observation identity mismatch: ${item.id}`);
  }
  return [...articles.values()].sort((a, b) => a.id.localeCompare(b.id)).map(article => {
    const members = [...figures.values()].filter(f => f.articleId === article.id)
      .sort((a, b) => a.id.localeCompare(b.id)).map(figure => {
        const item = observed.get(figure.id);
        const sourceKnown = item?.source?.matched === true && isHash(item.source.sha256);
        const software = sourceKnown && isHash(item.software?.evidenceHash) && item.software?.name
          ? {name: item.software.name, evidenceHash: item.software.evidenceHash} : null;
        return {id: figure.id, number: String(figure.number ?? ''), sourceKnown,
          sourceHash: sourceKnown ? item.source.sha256 : null,
          sourceFormat: sourceKnown ? item.source.format || null : null, software,
          category: sourceKnown ? item.category || null : null, route: sourceKnown ? item.route || null : null,
          observedStyle: sourceKnown ? structuredClone(item.observedStyle || {}) : {},
          userConstraints: structuredClone(item?.userConstraints || {})};
      });
    const cohorts = new Map();
    for (const member of members.filter(m => m.sourceKnown)) {
      const signature = {format: member.sourceFormat, software: member.software?.name || null,
        category: member.category, route: member.route};
      const key = digest(signature);
      if (!cohorts.has(key)) cohorts.set(key, {key, signature, members: []});
      cohorts.get(key).members.push(member);
    }
    const profile = {version: VERSION, articleId: article.id, members,
      unknownFigures: members.filter(m => !m.sourceKnown).map(m => m.id),
      cohorts: [...cohorts.values()].sort((a, b) => a.key.localeCompare(b.key)).map(cohort => {
        const sharedObservations = {};
        if (cohort.members.length > 1) {
          for (const [key, value] of Object.entries(cohort.members[0].observedStyle)) {
            if (cohort.members.every(m => Object.hasOwn(m.observedStyle, key) && digest(m.observedStyle[key]) === digest(value)))
              sharedObservations[key] = structuredClone(value);
          }
        }
        return {key: cohort.key, signature: cohort.signature, figureIds: cohort.members.map(m => m.id), sharedObservations};
      }), automaticOverrides: false};
    return {...profile, fingerprint: digest(profile)};
  });
}
