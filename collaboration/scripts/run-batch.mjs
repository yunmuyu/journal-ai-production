import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {executeBatch, verifyBatchPlan} from '../batch/queue.mjs';
import {createNativeAdapter} from '../batch/native-adapter.mjs';

export async function runBatch(argv) {
  const options = {}; let apply = false, singleWriter = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--apply') { apply = true; continue; }
    if (argv[i] === '--single-writer-ack') { singleWriter = true; continue; }
    const key = argv[i];
    if (!['--config', '--plan', '--report-dir', '--previous'].includes(key) || !argv[i + 1] || options[key]) throw Error('Invalid batch arguments');
    options[key] = argv[++i];
  }
  if (!options['--config'] || !options['--plan']) throw Error('Pass --config machine.json --plan batch-plan.json; dry-run is default');
  const read = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
  const plan = read(options['--plan']); verifyBatchPlan(plan);
  const {readMachine, repoRoot, releaseFile} = await import('./common.mjs');
  const machine = readMachine(options['--config']);
  const adapter = createNativeAdapter({machine, configFile: path.resolve(options['--config']),
    policyFile: path.join(repoRoot, 'knowledge/production-policy.json'), releaseFile,
    run: async args => (await import('./run.mjs')).run(args)});
  if (!apply) {
    const checks = [];
    for (const group of plan.groups) for (const item of group.items) {
      try { adapter.revalidate(item, plan); checks.push({id: item.id, ready: true}); }
      catch (error) { checks.push({id: item.id, ready: false, reason: error.message}); }
    }
    return {dryRun: true, checks, nativeStarted: false, excluded: plan.excluded};
  }
  if (!singleWriter || !options['--report-dir']) throw Error('Execution requires verified current handoff, --single-writer-ack and --report-dir NEW_DIRECTORY');
  const directory = path.resolve(options['--report-dir']); fs.mkdirSync(directory);
  const lock = path.join(machine.recordRoot, '.batch-execution.lock');
  const fd = fs.openSync(lock, 'wx');
  try {
    fs.writeFileSync(fd, JSON.stringify({pid: process.pid, planFingerprint: plan.fingerprint, startedAt: new Date().toISOString()}));
    const previous = options['--previous'] ? read(options['--previous']).results : [];
    const report = await executeBatch(plan, {...adapter, previous,
      onEvent: event => fs.appendFileSync(path.join(directory, 'events.jsonl'), JSON.stringify({...event, at: new Date().toISOString()}) + '\n')});
    fs.writeFileSync(path.join(directory, 'result.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
    return report;
  } finally { fs.closeSync(fd); fs.unlinkSync(lock); }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const report = await runBatch(process.argv.slice(2)); console.log(JSON.stringify(report, null, 2));
    if (report.results?.some(r => r.status !== 'succeeded') || report.checks?.some(c => !c.ready)) process.exitCode = 2;
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
