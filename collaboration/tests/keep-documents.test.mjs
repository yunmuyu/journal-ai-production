import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
const source=readFileSync(new URL('../scripts/run.mjs',import.meta.url),'utf8');
const body=source.slice(source.indexOf('const writable ='),source.indexOf('if (process.argv[1]')).replace('export function run','function run');
function environment(machineOverride){
 const machine={runtimePath:'runtime',workspaceRoot:process.cwd(),recordRoot:'records',pathMapFile:'map.json',python:'python',flowchartRoot:'flowchart',...machineOverride};let captured;
 const context={path,process,performance,randomUUID:()=> 'test-invocation',parseArgs:()=>({configFile:'machine.json',rest:['status','existing-job']}),readMachine:()=>machine,readRelease:()=>({release:{id:'test',files:[]},manifestHash:'manifest'}),verifyFiles(){},existsSync:()=>true,spawnSync(){throw Error('Actual child process prohibited');}};
 vm.runInNewContext(body+';run([],(_exe,_args,options)=>{capture(options);return {status:0};});',Object.assign(context,{capture(value){captured=value;}}));
 return captured.env;
}
test('explicit false disables retaining only the driver-owned Illustrator documents',()=>{
 assert.equal(environment({keepIllustratorDocuments:false}).JFW_KEEP_ILLUSTRATOR_DOCUMENTS,'0');
});
test('missing keepIllustratorDocuments preserves existing keep-open default',()=>{
 assert.equal(environment({}).JFW_KEEP_ILLUSTRATOR_DOCUMENTS,'1');
});
