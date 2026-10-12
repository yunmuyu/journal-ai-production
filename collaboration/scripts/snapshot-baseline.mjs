import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {closeSync, copyFileSync, existsSync, lstatSync, mkdirSync, openSync, readFileSync, readSync, realpathSync, readdirSync, statSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs, readMachine, sha256} from './common.mjs';

const stateNames = ['inventory.json', 'production-results.json', 'author-templates.json', 'figure-classification.json'];
const defaultExcludes = ['receive-family-*', 'node_modules', '.git'];
const unix = value => value.split(path.sep).join('/');

function fileFingerprint(file) {
  const before = statSync(file);
  if (lstatSync(file).isSymbolicLink()) throw Error('File is a link: ' + file);
  if (!before.isFile()) throw Error('Not a regular file: ' + file);
  const digest = createHash('sha256');
  const chunk = Buffer.allocUnsafe(1024 * 1024);
  const fd = openSync(file, 'r');
  let size = 0;
  try {
    let count;
    while ((count = readSync(fd, chunk, 0, chunk.length, null)) > 0) {
      digest.update(chunk.subarray(0, count));
      size += count;
    }
  } finally {
    closeSync(fd);
  }
  const after = statSync(file);
  if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs || size !== after.size) throw Error('File changed during hashing: ' + file);
  return {size: after.size, sha256: digest.digest('hex')};
}
function patterns(machine) {
  if (machine.baselineExcludes !== undefined && (!Array.isArray(machine.baselineExcludes) || machine.baselineExcludes.some(x => typeof x !== 'string' || !x))) throw Error('baselineExcludes must be nonempty strings');
  return [...defaultExcludes, ...(machine.baselineExcludes || [])].map(pattern => ({pattern, regex: new RegExp('^' + pattern.replace(/[|\{}()[\]^$+?.]/g, '\$&').replace(/\*/g, '.*') + '$')}));
}
function scan(root, scope, excludes, omittedRoots) {
  if (lstatSync(root).isSymbolicLink() || realpathSync(root).toLowerCase() !== path.resolve(root).toLowerCase()) throw Error('Scanned root crosses a link: ' + root);
  const entries = [];
  function visit(dir) {
    for (const item of readdirSync(dir, {withFileTypes: true}).sort((a, b) => a.name.localeCompare(b.name))) {
      const full = path.join(dir, item.name);
      if (omittedRoots.some(omitted => within(full, omitted))) continue;
      const relative = unix(path.relative(root, full));
      if (excludes.some(({regex}) => regex.test(item.name) || regex.test(relative))) continue;
      if (item.isSymbolicLink()) throw Error('Symlink requires explicit handling: ' + full);
      if (item.isDirectory()) visit(full);
      else if (item.isFile()) entries.push({scope, path: relative, ...fileFingerprint(full)});
      else throw Error('Unsupported filesystem entry: ' + full);
    }
  }
  visit(root);
  return entries;
}
function codeRevision(codeRoot) {
  const head = execFileSync('git', ['-C', codeRoot, 'rev-parse', 'HEAD'], {encoding: 'utf8', windowsHide: true}).trim();
  if (!/^[a-f0-9]{40}$/.test(head)) throw Error('Invalid code commit');
  const dirty = execFileSync('git', ['-C', codeRoot, 'status', '--porcelain'], {encoding: 'utf8', windowsHide: true}).trim();
  if (dirty) throw Error('codeRoot has uncommitted changes; commit before creating a shared baseline');
  return head;
}
function within(target, root) {
  const relative = path.relative(root, target);
  return relative === '' || (relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative));
}
function futureRealPath(target) {
  let ancestor = target;
  while (!existsSync(ancestor)) {
    const parent = path.dirname(ancestor);
    if (parent === ancestor) throw Error('Output drive or root does not exist: ' + target);
    ancestor = parent;
  }
  return path.resolve(realpathSync(ancestor), path.relative(ancestor, target));
}
function ensureOutsideScopes(output, roots) {
  for (const root of roots) {
    if (within(output, root) || within(futureRealPath(output), realpathSync(root))) throw Error('Output must be outside scanned scope: ' + root);
  }
}

function requireNewOutput(output) {
  if (!output) throw Error('Pass --output to a new directory');
  if (existsSync(output)) throw Error('Output already exists: ' + output);
}

export function snapshotBaseline(argv, revision = codeRevision) {
  const {configFile, rest} = parseArgs(argv);
  const outputIndex = rest.indexOf('--output');
  if (outputIndex < 0 || !rest[outputIndex + 1] || rest.some((arg, i) => arg !== '--apply' && arg !== '--output' && i !== outputIndex + 1)) throw Error('Usage: snapshot-baseline.mjs --config machine.json --output NEW_DIR [--apply]');
  const apply = rest.includes('--apply');
  const output = path.resolve(rest[outputIndex + 1]);
  requireNewOutput(output);
  const machine = readMachine(configFile);
  if (!machine.codeRoot || !machine.productionRoot) throw Error('machine.json requires codeRoot and productionRoot');
  const workRoot = path.join(machine.workspaceRoot, 'work');
  const candidates = [
    {scope: 'production', root: path.resolve(machine.productionRoot)},
    {scope: 'workspace-work', root: path.resolve(workRoot)},
    ...(machine.workRoot ? [{scope: 'configured-work', root: path.resolve(machine.workRoot)}] : [])
  ];
  ensureOutsideScopes(output, candidates.map(item => item.root));
  const scopes = [];
  for (const candidate of candidates) if (!scopes.some(previous => within(candidate.root, previous.root))) scopes.push(candidate);
  const releaseFile = path.join(machine.codeRoot, 'RELEASE.json');
  const releaseBytes = readFileSync(releaseFile);
  const release = JSON.parse(releaseBytes.toString('utf8').replace(/^﻿/, ''));
  const commit = revision(machine.codeRoot);
  const state = stateNames.map(name => ({name, file: path.join(machine.recordRoot, name)}));
  const stateBefore = new Map(state.map(item => [item.name, fileFingerprint(item.file)]));
  const excludes = patterns(machine);
  const entries = scopes.flatMap(item => scan(item.root, item.scope, excludes, scopes.filter(other => other !== item && within(other.root, item.root)).map(other => other.root)));
  const stateAfter = new Map(state.map(item => [item.name, fileFingerprint(item.file)]));
  for (const item of state) if (JSON.stringify(stateBefore.get(item.name)) !== JSON.stringify(stateAfter.get(item.name))) throw Error('State changed during scan: ' + item.name);
  const production = JSON.parse(readFileSync(path.join(machine.recordRoot, 'production-results.json'), 'utf8').replace(/^﻿/, ''));
  const references = {
    articleIds: Object.keys(production.articles || {}).sort(),
    figureIds: Object.keys(production.figures || {}).sort()
  };
  const manifest = {
    schemaVersion: 1, status: 'pending-peer-confirmation', createdAt: new Date().toISOString(),
    codeCommit: commit, releaseId: release.id, releaseSha256: sha256(releaseBytes),
    scopes: Object.fromEntries(scopes.map(item => [item.scope, item.root])),
    excludes: excludes.map(x => x.pattern),
    state: state.map(item => ({name: item.name, ...stateBefore.get(item.name)})),
    files: entries
  };
  if (!apply) return {mode: 'dry-run', output, status: manifest.status, codeCommit: commit, releaseSha256: manifest.releaseSha256, fileCount: entries.length, stateCount: state.length};
  requireNewOutput(output);
  mkdirSync(path.join(output, 'state'), {recursive: true});
  for (const item of state) copyFileSync(item.file, path.join(output, 'state', item.name));
  writeFileSync(path.join(output, 'references.json'), JSON.stringify(references, null, 2) + '\n');
  writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  for (const item of state) {
    const final = fileFingerprint(item.file);
    const copied = fileFingerprint(path.join(output, 'state', item.name));
    if (JSON.stringify(final) !== JSON.stringify(stateBefore.get(item.name)) || JSON.stringify(copied) !== JSON.stringify(final)) throw Error('State changed before completion: ' + item.name);
  }
  writeFileSync(path.join(output, 'BASELINE-COMPLETE.json'), JSON.stringify({manifestSha256: fileFingerprint(path.join(output, 'manifest.json')).sha256, status: manifest.status, completedAt: new Date().toISOString()}, null, 2) + '\n');
  return {mode: 'apply', output, status: manifest.status, fileCount: entries.length, stateCount: state.length};
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { console.log(JSON.stringify(snapshotBaseline(process.argv.slice(2)), null, 2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
