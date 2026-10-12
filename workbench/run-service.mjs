import fs from 'node:fs';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const log = fileURLToPath(new URL('server-runtime.log', import.meta.url));
const fd = fs.openSync(log, 'a');
fs.writeSync(fd, `${new Date().toISOString()} starting workbench\n`);
const child = spawn(process.execPath, [fileURLToPath(new URL('server.mjs', import.meta.url))], {
  windowsHide: true,
  stdio: ['ignore', fd, fd],
});
child.on('error', error => {
  fs.writeSync(fd, `${new Date().toISOString()} launch failed: ${error.stack}\n`);
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  fs.writeSync(fd, `${new Date().toISOString()} server exited code=${code} signal=${signal}\n`);
  fs.closeSync(fd);
  process.exitCode = code ?? 1;
});
