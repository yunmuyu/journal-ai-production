import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readMachine, parseArgs} from './common.mjs';
import {mapLocalPath} from '../../lib/local-paths.mjs';
import {syncCurrentDelivery} from '../current-delivery.mjs';
import {withCompleteArticles} from '../batch/article-readiness.mjs';
import {bytesHash} from '../batch/contracts.mjs';

export function syncDelivery(machine, {expected, expectedCurrent = () => true} = {}) {
  const recordsFile = path.join(machine.recordRoot, 'production-results.json');
  const inventoryFile = path.join(machine.recordRoot, 'inventory.json');
  const recordsBytes = fs.readFileSync(recordsFile), inventoryBytes = fs.readFileSync(inventoryFile);
  const records = JSON.parse(recordsBytes.toString('utf8').replace(/^\uFEFF/, ''));
  const inventory = JSON.parse(inventoryBytes.toString('utf8').replace(/^\uFEFF/, ''));
  const resolve = p => mapLocalPath(p, machine.pathMapFile);
  const publish = () => syncCurrentDelivery({root: machine.deliveryRoot || path.join(machine.recordRoot, '交付'), records, inventory, resolve,
    isCurrent: () => fs.readFileSync(recordsFile).equals(recordsBytes) && fs.readFileSync(inventoryFile).equals(inventoryBytes) && expectedCurrent()});
  if (expected !== undefined) return withCompleteArticles({inventory, records, expected,
    verifyArtifact: (file, sha256) => bytesHash(fs.readFileSync(resolve(file))) === sha256}, publish);
  return publish();
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const {configFile, rest} = parseArgs(process.argv.slice(2));
    let options = {};
    if (rest.length) {
      if (rest.length !== 2 || rest[0] !== '--require-complete') throw Error('Usage: sync-delivery.mjs --config machine.json [--require-complete expected.json]');
      const file = path.resolve(rest[1]), bytes = fs.readFileSync(file);
      options = {expected: JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/, '')), expectedCurrent: () => fs.readFileSync(file).equals(bytes)};
    }
    const result = syncDelivery(readMachine(configFile), options);
    console.log(JSON.stringify({changed: result.changed, approved: result.items.filter(x => x.state === 'approved').length,
      review: result.items.filter(x => x.state === 'review').length, issues: result.issues, archive: result.archive}, null, 2));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
