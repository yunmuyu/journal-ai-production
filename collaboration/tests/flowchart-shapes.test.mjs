import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {preflightPlan} from '../scripts/plan-preflight.mjs';
const root=fileURLToPath(new URL('../../production-runtime/flowchart/',import.meta.url));
const generator=path.join(root,'assets/AI流程图生成器.jsx');
test('packaged validator accepts new v3 shapes and rejects them in v2',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jfw-shapes-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const graph={schemaVersion:3,kind:'flowchart',flowShapePolicy:'sourceVisible',fontSize:8,nodes:[{id:'input',shape:'inputOutput',text:'输入',row:0,column:0},{id:'process',shape:'predefinedProcess',text:'处理',row:1,column:0}],edges:[{from:'input',to:'process'}]};
 const file=path.join(dir,'graph.json');fs.writeFileSync(file,JSON.stringify(graph));
 const run=()=>spawnSync(process.execPath,[path.join(root,'scripts/validate_flowchart.js'),file],{encoding:'utf8'});
 let result=run();assert.equal(result.status,0,result.stderr+result.stdout);
 graph.schemaVersion=2;fs.writeFileSync(file,JSON.stringify(graph));assert.notEqual(run().status,0);
});
test('official preflight accepts bundled generator at supported font sizes',()=>{
 for(const fontSize of [6,7,8]){const result=preflightPlan({route:'rebuild',fontSize,widthMm:80,graph:{fontSize,widthClass:'single',nodes:[{id:'input'}]}},{generatorFile:generator});assert.equal(result.fontSizePt,fontSize);assert.ok(result.contentWidthMm>56);}
});
test('text moves by actual outlined ink center while retaining editable original',()=>{
 const source=fs.readFileSync(generator,'utf8');const start=source.indexOf('    function centerText('),end=source.indexOf('\n    function ',start+1);const ctx={};vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 let removed=0,translated;const tf={visibleBounds:[0,50,20,0],duplicate:()=>({createOutline:()=>({visibleBounds:[3,20,13,10],remove:()=>removed++})}),translate:(x,y)=>translated=[x,y]};
 ctx.centerText(tf,30,40);assert.deepEqual(translated,[22,25]);assert.equal(removed,1);assert.equal(typeof tf.translate,'function');
});
