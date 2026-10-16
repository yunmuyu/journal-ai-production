// Thin integration adapter. No shell, no provider SDK, no API key.
// JFW_PYTHON selects a previously configured environment; source files never set it.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const args=process.argv.slice(2);
if(!['prepare','complete','status','review'].includes(args[0])){
  console.error('Usage: node bridge/run-agent-entry.mjs prepare|complete|status|review ...');
  process.exit(2);
}
const cwd=fileURLToPath(new URL('../',import.meta.url));
const child=spawn(process.env.JFW_PYTHON||'python',['-m','journal_pdf','agent',...args],{cwd,stdio:'inherit',shell:false});
child.on('error',e=>{console.error(JSON.stringify({status:'blocked',code:'python_start_failed',message:e.message}));process.exitCode=2;});
child.on('exit',code=>{process.exitCode=code??2;});
