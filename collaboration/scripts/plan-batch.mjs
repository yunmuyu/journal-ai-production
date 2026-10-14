import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {buildCandidateReports} from '../batch/reports.mjs';
import {bytesHash} from '../batch/contracts.mjs';

const read = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
export function writeCandidateReports(reports, directory) {
  for (const name of Object.keys(reports)) if (!/^[a-z-]+\.json$/.test(name)) throw Error('Invalid report filename');
  fs.mkdirSync(directory);
  for (const [name, report] of Object.entries(reports))
    fs.writeFileSync(path.join(directory, name), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
}
export async function planBatch(argv) {
  const options = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (!['--config', '--input', '--output'].includes(argv[i]) || !argv[i + 1] || options[argv[i]]) throw Error('Usage: plan-batch.mjs --config machine.json --input evidence.json --output NEW_DIRECTORY');
    options[argv[i]] = argv[i + 1];
  }
  if (Object.keys(options).length !== 3) throw Error('config, input and output required');
  const {readMachine, readRelease, repoRoot} = await import('./common.mjs');
  const {mapLocalPath} = await import('../../lib/local-paths.mjs');
  const machine = readMachine(options['--config']), evidence = read(options['--input']);
  const inventoryFile = path.join(machine.recordRoot, 'inventory.json'), recordsFile = path.join(machine.recordRoot, 'production-results.json');
  const inventoryBytes = fs.readFileSync(inventoryFile), recordsBytes = fs.readFileSync(recordsFile);
  const context = {policyHash: bytesHash(fs.readFileSync(path.join(repoRoot, 'knowledge/production-policy.json'))), runtimeHash: readRelease().manifestHash};
  const inventory = JSON.parse(inventoryBytes.toString('utf8').replace(/^\uFEFF/, ''));
  const records = JSON.parse(recordsBytes.toString('utf8').replace(/^\uFEFF/, ''));
  if (evidence.caseReuse) {
    if (!evidence.caseEvidence) throw Error('Current case evidence required to refresh history');
    const {refreshIndex, retrieveCases} = await import('../../knowledge/decision-retrieval.mjs');
    const index = refreshIndex({inventory, production: records, evidence: evidence.caseEvidence});
    evidence.caseReuse.indexFingerprint = index.sourceFingerprint;
    evidence.caseReuse.retrievalByFigure = Object.fromEntries(evidence.observations.map(item => [item.id, retrieveCases(index, item.retrievalQuery || {})]));
  }
  const reports = buildCandidateReports({inventory, records, evidence, context,
    verifyArtifact: (file, expected) => bytesHash(fs.readFileSync(mapLocalPath(file, machine.pathMapFile))) === expected});
  if (!fs.readFileSync(inventoryFile).equals(inventoryBytes) || !fs.readFileSync(recordsFile).equals(recordsBytes)) throw Error('Authority changed during planning');
  writeCandidateReports(reports, path.resolve(options['--output']));
  return {files: Object.keys(reports), executableItems: reports['batch-plan.json'].groups.reduce((n, g) => n + g.items.length, 0),
    excluded: reports['batch-plan.json'].excluded, productionChanged: false};
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { console.log(JSON.stringify(await planBatch(process.argv.slice(2)), null, 2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
