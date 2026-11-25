// Explicit public engine entry; never inherit an installed Skill's Python module path.
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const [python,...args]=process.argv.slice(2);
if(!python||!args.length){console.error('Usage: node workbench/run-public-pdf.mjs <configured-python> <journal_pdf arguments...>');process.exitCode=2;}
else{
 if(['render','capacity'].includes(args[0])){
  if(args[1])args[1]=path.resolve(args[1]);
  for(let i=2;i<args.length-1;i++)if(['--source-root','--profile','--output'].includes(args[i]))args[++i]=path.resolve(args[i]);
 }
 const engine=fileURLToPath(new URL('../portable-production/direct-pdf/',import.meta.url));
 const bootstrap='import pathlib,runpy,sys; import journal_pdf; expected=pathlib.Path(sys.argv.pop(1)).resolve(); actual=pathlib.Path(journal_pdf.__file__).resolve(); assert actual.parent==expected/"journal_pdf", "Wrong journal_pdf runtime: "+str(actual); print("journal_pdf_module="+str(actual),file=sys.stderr); sys.argv[0]="journal_pdf"; runpy.run_module("journal_pdf",run_name="__main__")';
 const result=spawnSync(python,['-c',bootstrap,engine,...args],{cwd:engine,env:{...process.env,PYTHONPATH:engine,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'},stdio:'inherit',windowsHide:true});
 if(result.error){console.error(result.error.message);process.exitCode=1;}else process.exitCode=result.status??1;
}
