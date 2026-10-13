import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {parseArgs, readMachine, repoRoot} from './common.mjs';

export function configureWorkbench(argv) {
  const {configFile, rest} = parseArgs(argv);
  const portIndex = rest.indexOf('--port');
  if (rest.some((arg, index) => arg !== '--port' && !(portIndex >= 0 && index === portIndex + 1)) || (portIndex >= 0 && !rest[portIndex + 1])) {
    throw Error('Usage: start-workbench.mjs --config machine.json [--port PORT]');
  }
  const machine = readMachine(configFile);
  if(machine.pdfjsRoot!==undefined){
    if(typeof machine.pdfjsRoot!=='string'||!machine.pdfjsRoot.trim())throw Error('Invalid machine configuration: pdfjsRoot');
    process.env.JFW_PDFJS_ROOT=path.resolve(path.dirname(path.resolve(configFile)),machine.pdfjsRoot);
  }
  const port = portIndex >= 0 ? Number(rest[portIndex + 1]) : (machine.reviewPort === undefined ? 18741 : Number(machine.reviewPort));
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('Invalid review port');
  process.env.JFW_RECORD_ROOT = machine.recordRoot;
  process.env.JFW_PATH_MAP_FILE = machine.pathMapFile;
  process.env.JFW_WORKSPACE_ROOT = machine.workspaceRoot;
  process.env.JFW_WORK_ROOT = machine.workRoot || machine.workspaceRoot;
  process.env.JFW_REVIEW_PORT = String(port);
  process.env.JFW_RUNTIME_PATH = machine.runtimePath;
  process.env.JFW_DELIVERY_ROOT = machine.deliveryRoot || path.join(machine.recordRoot, '交付');
  process.chdir(machine.workspaceRoot);
  return {port, recordRoot: machine.recordRoot, workspaceRoot: machine.workspaceRoot};
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    configureWorkbench(process.argv.slice(2));
    await import(pathToFileURL(path.join(repoRoot, 'workbench', 'server.mjs')).href);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
