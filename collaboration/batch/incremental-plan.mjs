import {digest, isHash, uniqueMap} from './contracts.mjs';

/** Dependency invalidation, not dirty-pixel rendering. Never writes or deletes accepted artifacts. */
export function planIncremental(nodes, previous = []) {
  const current = uniqueMap(nodes, 'node'), old = uniqueMap(previous, 'previous-node');
  const signatures = new Map(), visiting = new Set();
  function signature(id) {
    if (signatures.has(id)) return signatures.get(id);
    if (visiting.has(id)) throw Error(`Dependency cycle: ${id}`);
    const node = current.get(id);
    if (!node) throw Error(`Missing dependency: ${id}`);
    if (!isHash(node.inputHash)) throw Error(`inputHash required: ${id}`);
    if (!Array.isArray(node.dependencies)) throw Error(`Explicit dependencies required: ${id}`);
    if (new Set(node.dependencies).size !== node.dependencies.length) throw Error(`Duplicate dependency: ${id}`);
    visiting.add(id);
    const result = digest({inputHash: node.inputHash, sharedGroup: node.sharedGroup || null,
      dependencies: [...node.dependencies].sort().map(dep => [dep, signature(dep)])});
    visiting.delete(id); signatures.set(id, result); return result;
  }
  for (const id of current.keys()) signature(id);
  const reasons = new Map([...current.keys()].map(id => [id, new Set()]));
  for (const [id, node] of current) {
    const prior = old.get(id);
    if (!prior || prior.signature !== signatures.get(id)) reasons.get(id).add('input-or-dependency-changed');
    if (!isHash(prior?.outputHash) || node.currentOutputHash !== prior.outputHash) reasons.get(id).add('artifact-unverified');
  }
  let changed;
  do {
    changed = false;
    const dirtyGroups = new Set([...current].filter(([id, n]) => reasons.get(id).size && n.sharedGroup).map(([, n]) => n.sharedGroup));
    for (const [id, node] of current) {
      const reason = node.sharedGroup && dirtyGroups.has(node.sharedGroup) ? 'shared-group-changed' :
        node.dependencies.some(dep => reasons.get(dep).size) ? 'dependency-dirty' : null;
      if (reason && !reasons.get(id).size) { reasons.get(id).add(reason); changed = true; }
    }
  } while (changed);
  const blocked = new Set([...current].filter(([id, node]) => reasons.get(id).size && (node.frozen || old.get(id)?.frozen)).map(([id]) => id));
  do {
    changed = false;
    const groups = new Set([...blocked].map(id => current.get(id).sharedGroup).filter(Boolean));
    for (const [id, node] of current) if (!blocked.has(id) &&
      (node.dependencies.some(dep => blocked.has(dep)) || node.sharedGroup && groups.has(node.sharedGroup))) {
      blocked.add(id); changed = true;
    }
  } while (changed);
  return {items: [...current].map(([id, node]) => ({id, signature: signatures.get(id),
    action: blocked.has(id) ? 'blocked-copy-required' : reasons.get(id).size ? 'rebuild-candidate' : 'reuse',
    reasons: [...reasons.get(id)], frozen: !!(node.frozen || old.get(id)?.frozen)})),
    removed: [...old.keys()].filter(id => !current.has(id)).map(id => ({id, action: 'retain-until-explicit-review'}))};
}
