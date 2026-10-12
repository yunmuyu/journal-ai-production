import {copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {adobeLock, parseArgs, readMachine, readRelease, repoRoot, sha256, verifyFiles} from './common.mjs';

export function install(argv) {
  const {configFile, rest} = parseArgs(argv);
  const apply = rest.includes('--apply');
  const rootIndex = rest.indexOf('--skills-root');
  if (rest.some((arg, index) => arg !== '--apply' && arg !== '--skills-root' && !(rootIndex >= 0 && index === rootIndex + 1)) || (rootIndex >= 0 && !rest[rootIndex + 1])) throw Error('Usage: install.mjs --config machine.json [--skills-root DIR] [--apply]');
  const machine = readMachine(configFile);
  const skillsRoot = rootIndex >= 0 ? path.resolve(rest[rootIndex + 1]) : machine.skillsRoot;
  if (!skillsRoot) throw Error('Set skillsRoot or pass --skills-root');
  const {release, manifestHash} = readRelease();
  const sourceRuntime = path.join(repoRoot, 'production-runtime');
  verifyFiles(sourceRuntime, release.files);
  const sourceSkill = path.join(repoRoot, 'skill', 'SKILL.md');
  if (sha256(readFileSync(sourceSkill)) !== release.skillSha256) throw Error('Skill hash mismatch');
  if (existsSync(adobeLock)) throw Error('Adobe global lock is occupied: ' + adobeLock);
  const target = path.join(skillsRoot, 'journal-figure-workflow');
  const copies = release.files.map(item => ({source: path.join(sourceRuntime, item.path), target: path.join(target, 'runtime', item.path)}));
  copies.push({source: sourceSkill, target: path.join(target, 'SKILL.md')});
  const plan = {mode: apply ? 'apply' : 'dry-run', releaseId: release.id, manifestHash, target, count: copies.length};
  if (!apply) return plan;
  const backup = path.join(skillsRoot, '.journal-figure-workflow-backups', new Date().toISOString().replace(/[:.]/g, '-') + '-' + process.pid);
  mkdirSync(backup, {recursive: true});
  for (const file of copies) {
    if (!existsSync(file.target)) continue;
    const rel = path.relative(target, file.target);
    const previous = path.join(backup, rel);
    mkdirSync(path.dirname(previous), {recursive: true});
    copyFileSync(file.target, previous);
  }
  for (const file of copies) {
    mkdirSync(path.dirname(file.target), {recursive: true});
    copyFileSync(file.source, file.target);
  }
  verifyFiles(path.join(target, 'runtime'), release.files);
  if (sha256(readFileSync(path.join(target, 'SKILL.md'))) !== release.skillSha256) throw Error('Installed Skill hash mismatch');
  const receipt = {...plan, backup, installedAt: new Date().toISOString(), files: copies.map(file => path.relative(target, file.target))};
  const receiptFile = path.join(target, 'install-receipt.json');
  writeFileSync(receiptFile, JSON.stringify(receipt, null, 2) + '\n');
  return {...plan, backup, receiptFile};
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { console.log(JSON.stringify(install(process.argv.slice(2)), null, 2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
