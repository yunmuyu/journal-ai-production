import fs from 'node:fs';
import path from 'node:path';
import {bytesHash, digest, protectedRecord} from './contracts.mjs';

const read = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
const hashFile = file => bytesHash(fs.readFileSync(file));
const stop = message => Object.assign(Error(message), {blockResource: true});
function inside(root, file) {
  const relative = path.relative(fs.realpathSync(root), fs.realpathSync(file));
  if (!relative || relative === '..' || relative.startsWith('..' + path.sep) || path.isAbsolute(relative)) throw Error('Artifact escapes job');
  return file;
}
export function createNativeAdapter({machine, configFile, policyFile, releaseFile, run}) {
  const resolve = file => path.resolve(machine.workspaceRoot, file);
  const jobPath = item => path.isAbsolute(item.job) ? item.job : path.resolve(machine.workRoot || machine.workspaceRoot, item.job);
  const revalidate = (item, plan) => {
    const inventory = read(path.join(machine.recordRoot, 'inventory.json'));
    const records = read(path.join(machine.recordRoot, 'production-results.json'));
    if (digest({inventory, records}) !== plan.authorityFingerprint) throw stop('Authoritative inventory/records changed; rebuild batch plan');
    if (protectedRecord(records.figures[item.id])) throw stop('Figure became accepted; preserve it');
    if (hashFile(policyFile) !== plan.context.policyHash || hashFile(releaseFile) !== plan.context.runtimeHash) throw stop('Policy or release changed');
    if (hashFile(resolve(item.source.path)) !== item.source.sha256 || hashFile(resolve(item.plan.path)) !== item.plan.sha256) throw Error('Source or plan file changed');
    if (path.extname(resolve(item.source.path)).slice(1).toLowerCase() !== item.source.format) throw Error('Source format evidence mismatch');
    const p = read(resolve(item.plan.path));
    if (p.figureId !== item.id || p.sourceHash !== item.source.sha256 || p.route !== item.route ||
      p.fontSize !== item.strategy.fontSizePt || p.widthMm !== item.strategy.widthMm ||
      (typeof p.colorPolicy === 'object' ? p.colorPolicy?.mode : p.colorPolicy) !== item.strategy.colorPolicy) throw Error('Native plan identity/strategy mismatch');
    const job = read(path.join(jobPath(item), 'job.json'));
    const figure = job.figures?.find(f => f.id === item.id);
    if (!figure || figure.sourceHash !== item.source.sha256) throw Error('Native job figure binding mismatch');
    return true;
  };
  function recordMatches(record, item) {
    if (record.ok !== true || record.figureId !== item.id || record.sourceHash !== item.source.sha256 ||
      !record.planFile || hashFile(inside(jobPath(item), record.planFile)) !== record.planFileHash) return false;
    const actual = read(record.planFile), supplied = read(resolve(item.plan.path));
    return Object.entries(supplied).every(([key, value]) => {
      if (key === 'widthDecision') return true;
      if (key === 'colorPolicy' && value && typeof value === 'object') return actual.colorPolicy === value.mode &&
        (!Object.hasOwn(value, 'approval') || digest(record.colorPolicy?.approval ?? null) === digest(value.approval));
      return Object.hasOwn(actual, key) && digest(actual[key]) === digest(value);
    });
  }
  function verifyEvidence(evidence, item, plan) {
    if (evidence?.ok !== true || evidence.figureId !== item.id || evidence.sourceHash !== item.source.sha256 ||
      evidence.runtimeHash !== plan.context.runtimeHash || !Array.isArray(evidence.files) || evidence.files.length !== 3) return false;
    try {
      const job = read(path.join(jobPath(item), 'job.json')), current = job.figures?.find(f => f.id === item.id);
      if (!current?.render || path.resolve(jobPath(item), current.render) !== evidence.recordFile ||
        hashFile(inside(jobPath(item), evidence.recordFile)) !== evidence.recordHash) return false;
      const record = read(evidence.recordFile);
      if (!recordMatches(record, item)) return false;
      return ['output', 'ai', 'preview'].every(role => {
        const files = evidence.files.filter(f => f.role === role);
        return files.length === 1 && files[0].path === record[role] && files[0].sha256 === record[role + 'Hash'] &&
          typeof files[0].path === 'string' && /^[a-f0-9]{64}$/.test(files[0].sha256) &&
          hashFile(inside(jobPath(item), files[0].path)) === files[0].sha256;
      });
    } catch { return false; }
  }
  const execute = async (item, plan) => {
    const code = await run(['--config', configFile, 'render', jobPath(item), resolve(item.plan.path)]);
    if (code !== 0) throw stop('Native render failed; inspect host health before continuing this lane');
    revalidate(item, plan);
    const job = read(path.join(jobPath(item), 'job.json')), figure = job.figures.find(f => f.id === item.id);
    if (!figure.render) throw stop('Native render did not publish its job result reference');
    const recordFile = inside(jobPath(item), path.resolve(jobPath(item), figure.render)), record = read(recordFile);
    if (!recordMatches(record, item)) throw stop('Native result plan binding mismatch');
    const files = ['output', 'ai', 'preview'].map(key => ({role: key, path: record[key], sha256: record[`${key}Hash`]}));
    const evidence = {ok: true, figureId: item.id, sourceHash: item.source.sha256, runtimeHash: plan.context.runtimeHash, files,
      recordFile, recordHash: hashFile(recordFile), requiresUserReview: true, userAccepted: false};
    if (!verifyEvidence(evidence, item, plan)) throw stop('Native output artifacts failed hash verification');
    return evidence;
  };
  return {revalidate, execute, verifyPrevious: (old, item, plan) => verifyEvidence(old.evidence, item, plan)};
}
