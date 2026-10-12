import {createHash} from 'node:crypto';
import {tmpdir} from 'node:os';
import {readFileSync, statSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const releaseFile = path.join(repoRoot, 'RELEASE.json');
export const adobeLock = path.join(tmpdir(), 'journal-figure-adobe.lock');

export function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}
export function readRelease() {
  const bytes = readFileSync(releaseFile);
  const release = JSON.parse(bytes.toString('utf8').replace(/^﻿/, ''));
  if (!release.id || !Array.isArray(release.files) || !/^[a-f0-9]{64}$/.test(release.skillSha256)) throw Error('Invalid RELEASE.json');
  const names = new Set();
  for (const item of release.files) {
    if (!item.path || path.isAbsolute(item.path) || item.path.split(/[\/]/).includes('..') || names.has(item.path) || !/^[a-f0-9]{64}$/.test(item.sha256)) throw Error('Invalid release file: ' + item.path);
    names.add(item.path);
  }
  return {release, manifestHash: sha256(bytes)};
}
export function readMachine(file) {
  if (!file) throw Error('Pass --config to an external machine.json');
  const configFile = path.resolve(file);
  const config = JSON.parse(readFileSync(configFile, 'utf8').replace(/^﻿/, ''));
  for (const key of ['runtimePath', 'workspaceRoot', 'recordRoot', 'pathMapFile', 'python', 'flowchartRoot']) {
    if (typeof config[key] !== 'string' || !config[key].trim()) throw Error('Missing machine configuration: ' + key);
    config[key] = path.resolve(path.dirname(configFile), config[key]);
  }
  for (const key of ['skillsRoot','codeRoot','productionRoot','workRoot','releaseRoot','handoffRoot','legacyWorkspaceRoot']) { if (config[key] !== undefined) { if (typeof config[key] !== 'string' || !config[key].trim()) throw Error('Invalid machine configuration: ' + key); config[key] = path.resolve(path.dirname(configFile), config[key]); } }
  return config;
}
export function verifyFiles(root, files) {
  for (const item of files) {
    const target = path.resolve(root, item.path);
    if (!target.startsWith(path.resolve(root) + path.sep)) throw Error('Release path escapes runtime: ' + item.path);
    const bytes = readFileSync(target);
    if (sha256(bytes) !== item.sha256 || (item.bytes !== undefined && bytes.length !== item.bytes)) throw Error('Release hash mismatch: ' + item.path);
    if (!statSync(target).isFile()) throw Error('Release path is not a file: ' + item.path);
  }
}
export function parseArgs(argv) {
  let configFile;
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--config') configFile = argv[++i];
    else rest.push(argv[i]);
  }
  return {configFile, rest};
}
