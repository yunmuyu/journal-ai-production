import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync, existsSync} from 'node:fs';
import http from 'node:http';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {repoRoot} from '../scripts/common.mjs';

const recordRoot = 'F:/2026年10月/_作图工作台';
const workspaceRoot = path.resolve(repoRoot, '../..');
const pathMapFile = path.join(workspaceRoot, 'work/receive-family-20261012/office-paths.json');

function availablePort() {
  return new Promise((resolve, reject) => {
    const server = http.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}
function requestData(port) {
  return new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:${port}/data`, {headers: {Host: `127.0.0.1:${port}`}}, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => resolve({status: response.statusCode, body: JSON.parse(Buffer.concat(chunks).toString('utf8'))}));
    }).once('error', reject);
  });
}

test('isolated workbench reads original authoritative record', {skip: !existsSync(path.join(recordRoot, 'inventory.json')) || !existsSync(pathMapFile)}, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), 'jfw-workbench-launch-'));
  const configFile = path.join(folder, 'machine.json');
  writeFileSync(configFile, JSON.stringify({runtimePath: path.join(repoRoot, 'production-runtime'), workspaceRoot, recordRoot, pathMapFile, python: process.execPath, flowchartRoot: folder}));
  const port = await availablePort();
  const child = spawn(process.execPath, [path.join(repoRoot, 'collaboration/scripts/start-workbench.mjs'), '--config', configFile, '--port', String(port)], {cwd: folder, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true});
  let stdout = '', stderr = '';
  child.stdout.on('data', chunk => { stdout += chunk; });
  child.stderr.on('data', chunk => { stderr += chunk; });
  try {
    const deadline = Date.now() + 15000;
    while (!stdout.includes('"rows"') && Date.now() < deadline && child.exitCode === null) await new Promise(resolve => setTimeout(resolve, 100));
    assert.match(stdout, /"rows"/, stderr);
    const response = await requestData(port);
    assert.equal(response.status, 200);
    const inventory = JSON.parse(readFileSync(path.join(recordRoot, 'inventory.json'), 'utf8'));
    assert.ok(response.body.rows.length > 0);
    assert.ok(response.body.rows.some(row => row.id === inventory.figures[0].id));
  } finally {
    child.kill();
    await new Promise(resolve => child.once('exit', resolve));
  }
});
