import {appendFileSync, existsSync, mkdirSync, readFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {preflightPlan} from './plan-preflight.mjs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {parseArgs, readMachine, readRelease, verifyFiles, sha256} from './common.mjs';

const writable = new Set(['init','scan','add','ingest','pair','convert','suggest','doctor','recover','fit','render','adjust-text','review','deliver']);
const readable = new Set(['status','inspect']);

export function run(argv, spawn = spawnSync) {
  const {configFile, rest} = parseArgs(argv);
  const [command, jobArg, ...args] = rest;
  if (!command || !jobArg || !(writable.has(command) || readable.has(command))) throw Error('Usage: run.mjs --config machine.json COMMAND JOB [args]');
  const machine = readMachine(configFile);
  const {release, manifestHash} = readRelease();
  verifyFiles(machine.runtimePath, release.files);
  const job = path.isAbsolute(jobArg) ? path.resolve(jobArg) : path.resolve(machine.workRoot || machine.workspaceRoot, jobArg);
  if (readable.has(command) && !existsSync(job)) throw Error('Read-only command requires an existing job: ' + job);
  const eventFile = path.join(job, 'tool-version-events.jsonl');
  const planPath = ['render','fit'].includes(command) && args[0] ? path.resolve(machine.workspaceRoot, args[0]) : null;
  const planBytes = planPath && existsSync(planPath) ? readFileSync(planPath) : null;
  const started = performance.now();
  const base = {invocationId: randomUUID(), planFileHash: planBytes ? sha256(planBytes) : null, releaseId: release.id, manifestHash, command, job, args, planPath, startedAt: new Date().toISOString()};
  // A writable command must be able to record its provenance before it runs.
  if (writable.has(command)) {
    mkdirSync(job, {recursive: true});
    appendFileSync(eventFile, JSON.stringify({...base, event: 'start'}) + '\n');
  }
  let child, preflight = null;
  try {
    if (['render','fit'].includes(command)) {
      if (!planBytes) throw Error((command==='render'?'Render':'Fit')+' plan file missing: ' + planPath);
      preflight = preflightPlan(JSON.parse(planBytes.toString('utf8').replace(/^﻿/, '')), {generatorFile: path.join(machine.flowchartRoot, 'assets/AI流程图生成器.jsx')});
      if (preflight) console.error(JSON.stringify({event: 'layout_preflight', ...preflight}));
    }
    child = spawn(process.execPath, [path.join(machine.runtimePath, 'scripts/jfw.mjs'), command, job, ...args], {
      stdio: 'inherit', windowsHide: true, cwd: machine.workspaceRoot,
      env: {...process.env, JFW_KEEP_ILLUSTRATOR_DOCUMENTS: machine.keepIllustratorDocuments === false ? '0' : '1', JFW_PATH_MAP_FILE: machine.pathMapFile, JFW_PYTHON: machine.python, JFW_FLOWCHART_ROOT: machine.flowchartRoot, JFW_WORKSPACE_ROOT: machine.workspaceRoot, JFW_RECORD_ROOT: machine.recordRoot}
    });
  } catch (error) {
    child = {error, status: 1};
  }
  const exitCode = child.error ? 1 : (child.status ?? 1);
  if (writable.has(command)) appendFileSync(eventFile, JSON.stringify({...base, event: 'result', durationMs: performance.now()-started, preflight, finishedAt: new Date().toISOString(), exitCode, signal: child.signal ?? null, error: child.error?.message ?? null}) + '\n');
  if (child.error) throw child.error;
  return exitCode;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = run(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
