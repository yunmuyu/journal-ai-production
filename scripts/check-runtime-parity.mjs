#!/usr/bin/env node
/**
 * Read-only parity report comparing root (lib/, adobe/, scripts/) against
 * production-runtime/ and pinned-releases/2026.10.12-r5-pdf-grid/runtime/.
 * Helps maintainers track intentional divergences without accidental overwrites.
 */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function scanDir(relDir) {
  const base = path.join(root, relDir);
  const map = new Map();
  if (!fs.existsSync(base)) return map;
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
      if (entry.name.startsWith('.') || entry.name === '__pycache__' || entry.name.endsWith('.pyc')) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else {
        const rel = path.relative(base, full).split(path.sep).join('/');
        const data = fs.readFileSync(full);
        map.set(rel, {bytes: data.length, sha256: createHash('sha256').update(data).digest('hex')});
      }
    }
  }
  walk(base);
  return map;
}

function compareTrees(label, left, right) {
  const same = [], diff = [], onlyLeft = [], onlyRight = [];
  for (const [k, v] of left) {
    if (right.has(k)) {
      if (right.get(k).sha256 === v.sha256) same.push(k);
      else diff.push(k);
    } else onlyLeft.push(k);
  }
  for (const k of right.keys()) if (!left.has(k)) onlyRight.push(k);
  return {label, sameCount: same.length, diff, onlyLeft, onlyRight};
}

export function auditRuntimeParity() {
  const runtime = scanDir('production-runtime');
  const pinned = scanDir('pinned-releases/2026.10.12-r5-pdf-grid/runtime');
  const rootGroups = ['lib', 'adobe', 'scripts'].map(sub => {
    const subLeft = scanDir(sub);
    const subRight = new Map([...runtime].filter(([k]) => k.startsWith(sub + '/')).map(([k, v]) => [k.slice(sub.length + 1), v]));
    return compareTrees(`root:${sub} vs production-runtime/${sub}`, subLeft, subRight);
  });
  return {
    rootVsProductionRuntime: rootGroups,
    productionRuntimeVsPinnedR5: compareTrees('production-runtime vs pinned-r5', runtime, pinned),
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log(JSON.stringify(auditRuntimeParity(), null, 2));
}
