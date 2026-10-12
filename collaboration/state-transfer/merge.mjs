import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const ABSENT = Symbol('absent');
const KINDS = new Set(['inventory', 'production-results', 'author-templates', 'figure-classification']);
const REVIEW_FIELDS = new Set(['status', 'userFeedback', 'userAcceptance', 'userAcceptedAt', 'userAcceptedSource', 'userAcceptedBy']);
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const at = (object, key) => object && own(object, key) ? object[key] : ABSENT;
const equal = (left, right) => {
  if (left === ABSENT || right === ABSENT) return left === right;
  if (typeof left === 'string' && typeof right === 'string' && /^[A-Z]:[\\/]/i.test(left) && /^[A-Z]:[\\/]/i.test(right)) return left.replaceAll('\\', '/').toLowerCase() === right.replaceAll('\\', '/').toLowerCase();
  if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((value, index) => equal(value, right[index]));
  if (isObject(left) && isObject(right)) {
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every(key => own(right, key) && equal(left[key], right[key]));
  }
  return Object.is(left, right);
};
const display = value => value === ABSENT ? {absent: true} : value;

function assertUniqueRows(rows, label) {
  const map = new Map();
  for (const row of rows) {
    if (!isObject(row) || typeof row.id !== 'string' || !row.id) throw new Error(`${label}: every row needs a nonempty id`);
    if (map.has(row.id)) throw new Error(`${label}: duplicate id ${row.id}`);
    map.set(row.id, row);
  }
  return map;
}

function validate(kind, document, label) {
  if (!KINDS.has(kind)) throw new Error(`unsupported kind: ${kind}`);
  if (!isObject(document)) throw new Error(`${label}: root must be an object`);
  if (kind === 'inventory') {
    for (const field of ['articles', 'figures']) {
      if (!Array.isArray(document[field])) throw new Error(`${label}: ${field} must be an array`);
      assertUniqueRows(document[field], `${label}.${field}`);
    }
  } else if (kind === 'figure-classification') {
    if (!Array.isArray(document.cards)) throw new Error(`${label}: cards must be an array`);
    assertUniqueRows(document.cards, `${label}.cards`);
  } else if (kind === 'production-results') {
    for (const field of ['articles', 'figures']) if (!isObject(document[field])) throw new Error(`${label}: ${field} must be an ID object`);
  } else if (Object.keys(document).some(key => !/^A-[a-z0-9-]+$/i.test(key))) {
    throw new Error(`${label}: author-templates root keys must be article IDs`);
  }
}

function mapIncoming(value, rules) {
  if (typeof value === 'string' && /^[A-Z]:[\\/]/i.test(value)) {
    const normalized = value.replaceAll('\\', '/');
    const rule = rules.find(([old]) => normalized.toLowerCase() === old.toLowerCase() || normalized.toLowerCase().startsWith((old + '/').toLowerCase()));
    return rule ? rule[1] + normalized.slice(rule[0].length) : value;
  }
  if (Array.isArray(value)) return value.map(item => mapIncoming(item, rules));
  if (isObject(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, mapIncoming(item, rules)]));
  return value;
}

export function mergeDocuments(kind, base, local, incoming, {pathMap = []} = {}) {
  for (const [label, value] of [['base', base], ['local', local], ['incoming', incoming]]) validate(kind, value, label);
  incoming = pathMap.length ? mapIncoming(incoming, pathMap) : incoming;
  const conflicts = [];
  const figureKeys = kind === 'production-results' ? new Set([...Object.keys(base.figures), ...Object.keys(local.figures), ...Object.keys(incoming.figures)]) : new Set();
  const keyed = kind === 'inventory' ? new Set(['$.articles', '$.figures']) : kind === 'figure-classification' ? new Set(['$.cards']) : new Set();
  const conflict = (field, before, here, there, reason) => {
    conflicts.push({field, reason, base: display(before), local: display(here), incoming: display(there)});
    return here;
  };
  function merge(field, before, here, there) {
    if (keyed.has(field)) return mergeRows(field, before, here, there);
    if (before !== ABSENT && (here === ABSENT || there === ABSENT)) return conflict(field, before, here, there, 'deletion-requires-review');
    if (isObject(before) && isObject(here) && isObject(there)) {
      const reviewConflict = kind === 'production-results' && field.startsWith('$.figures.') && figureKeys.has(field.slice('$.figures.'.length)) &&
        [...REVIEW_FIELDS].some(key => !equal(at(before, key), at(here, key))) &&
        [...REVIEW_FIELDS].some(key => !equal(at(before, key), at(there, key))) &&
        [...REVIEW_FIELDS].some(key => !equal(at(here, key), at(there, key)));
      if (reviewConflict) conflict(`${field}.[review-state]`, before, here, there, 'acceptance-feedback-semantic-conflict');
      const entries = [];
      for (const key of new Set([...Object.keys(before), ...Object.keys(here), ...Object.keys(there)])) {
        const value = reviewConflict && REVIEW_FIELDS.has(key) ? at(here, key) : merge(`${field}.${key}`, at(before, key), at(here, key), at(there, key));
        if (value !== ABSENT) entries.push([key, value]);
      }
      return Object.fromEntries(entries);
    }
    if (equal(here, there)) return here;
    if (equal(before, here)) return there;
    if (equal(before, there)) return here;
    if (before === ABSENT || here === ABSENT || there === ABSENT) return conflict(field, before, here, there, 'add/delete conflict');
    return conflict(field, before, here, there, Array.isArray(here) || Array.isArray(there) ? 'unkeyed array changed on both sides' : 'same field changed on both sides');
  }
  function mergeRows(field, before, here, there) {
    if (![before, here, there].every(Array.isArray)) return conflict(field, before, here, there, 'keyed array shape changed');
    const maps = [before, here, there].map((rows, index) => assertUniqueRows(rows, `${field}.${['base', 'local', 'incoming'][index]}`));
    const ids = [...new Set([...here.map(row => row.id), ...there.map(row => row.id), ...before.map(row => row.id)])];
    const result = [];
    for (const id of ids) {
      const value = merge(`${field}[id=${id}]`, ...maps.map(map => map.has(id) ? map.get(id) : ABSENT));
      if (value !== ABSENT) result.push(value);
    }
    return result;
  }
  const merged = merge('$', base, local, incoming);
  return {merged, conflicts, conflictCount: conflicts.length};
}

function argumentMap(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (token === '--apply') { options.apply = true; continue; }
    if (token === '--map-prefix') { (options.pathMap ||= []).push(argv[++i]); if (!options.pathMap.at(-1)) throw new Error('--map-prefix needs OLD=NEW'); continue; }
    if (!['--kind', '--base', '--local', '--incoming', '--output'].includes(token) || !argv[i + 1]) throw new Error(`invalid argument: ${token}`);
    options[token.slice(2)] = argv[++i];
  }
  for (const key of ['kind', 'base', 'local', 'incoming']) if (!options[key]) throw new Error(`missing --${key}`);
  if (options.apply && !options.output) throw new Error('--apply requires --output');
  if (!options.apply && options.output) throw new Error('--output requires --apply');
  options.pathMap = (options.pathMap || []).map(value => {
    const offset = value.indexOf('=');
    if (offset < 3 || offset === value.length - 1) throw new Error('--map-prefix must be OLD=NEW');
    return [value.slice(0, offset).replaceAll('\\', '/').replace(/\/$/, ''), value.slice(offset + 1).replaceAll('\\', '/').replace(/\/$/, '')];
  }).sort((a, b) => b[0].length - a[0].length);
  return options;
}

export function runCli(argv) {
  const options = argumentMap(argv);
  const inputs = [options.base, options.local, options.incoming].map(value => path.resolve(value).toLowerCase());
  if (options.output && inputs.includes(path.resolve(options.output).toLowerCase())) throw new Error('output must differ from every input');
  const [base, local, incoming] = [options.base, options.local, options.incoming].map(file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')));
  const result = mergeDocuments(options.kind, base, local, incoming, {pathMap: options.pathMap});
  const report = {kind: options.kind, applied: false, conflictCount: result.conflictCount, conflicts: result.conflicts};
  if (options.apply && result.conflictCount === 0) {
    fs.writeFileSync(options.output, JSON.stringify(result.merged, null, 2) + '\n', {encoding: 'utf8', flag: 'wx'});
    report.applied = true;
    report.output = path.resolve(options.output);
  }
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const report = runCli(process.argv.slice(2));
    console.log(JSON.stringify(report, null, 2));
    if (report.conflictCount) process.exitCode = 2;
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
