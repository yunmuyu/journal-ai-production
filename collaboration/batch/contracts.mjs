import {createHash} from 'node:crypto';

export const VERSION = 'jfw-batch-v1';
export const isHash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export function requireHash(value, name) {
  if (!isHash(value)) throw Error(`${name} requires a lowercase SHA-256`);
  return value;
}
export function nonempty(value, name) {
  if (typeof value !== 'string' || !value.trim()) throw Error(`${name} required`);
  return value;
}
export function canonical(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && Object.getPrototypeOf(value) === Object.prototype) {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  }
  throw Error('Only finite JSON values are supported');
}
export const digest = value => createHash('sha256').update(canonical(value)).digest('hex');
export const bytesHash = value => createHash('sha256').update(value).digest('hex');
export function uniqueMap(items, name) {
  if (!Array.isArray(items)) throw Error(`${name} must be an array`);
  const map = new Map();
  for (const item of items) {
    nonempty(item?.id, `${name}.id`);
    if (map.has(item.id)) throw Error(`Duplicate ${name} id: ${item.id}`);
    map.set(item.id, item);
  }
  return map;
}
export function inventoryMaps(inventory) {
  const articles = uniqueMap(inventory.articles, 'article');
  const figures = uniqueMap(inventory.figures, 'figure');
  for (const figure of figures.values()) {
    if (!articles.has(figure.articleId)) throw Error(`Unknown articleId for ${figure.id}`);
  }
  return {articles, figures};
}
// Conservative execution protection; ambiguous legacy acceptance is NOT permission to remake.
export function protectedRecord(record) {
  return record?.userAcceptance?.accepted === true || /最终验收通过|终检通过/.test(record?.status || '');
}
export function explicitlyAccepted(record) {
  return record?.userAcceptance?.accepted === true && !/待|撤|退|不通过|未通过/.test(record.status || '');
}
export function preflightBinding(item, context) {
  return digest({version: VERSION, id: item.id, articleId: item.articleId,
    sourceHash: item.source.sha256, planHash: item.plan.sha256, route: item.route,
    category: item.category, format: item.source.format, decisionHash: item.decisionHash,
    job: item.job, sourcePath: item.source.path, planPath: item.plan.path, strategy: item.strategy,
    constraints: item.userConstraints || {}, policyHash: context.policyHash, runtimeHash: context.runtimeHash});
}
