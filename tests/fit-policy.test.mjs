import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import path from 'node:path';
const source=readFileSync(new URL('../lib/fit.mjs',import.meta.url),'utf8');
function run(plan,accept=()=>false){
 const calls=[],files=new Map();
 const ctx={path,readJson:()=>({figureId:'example',route:'vector-reletter',fontSize:8,...plan}),writeJson(file,value){files.set(file,value);},logEvent(){},render(root,file){const p=files.get(file);calls.push([p.widthMm,p.fontSize]);return {adobe:{snapshot:{artboard:[0,0,p.widthMm*72/25.4,-100]},mechanicalIssues:accept(p)?[]:[{type:'text_overlap'}]},planHash:'hash'};}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function fitInternal(')),ctx);
 return {result:ctx.fitInternal('job','plan'),calls,files};
}
test('Overflow tries all allowed single-column sizes before requesting layout revision',()=>{
 const r=run({});assert.deepEqual(r.calls,[[80,8],[80,7],[80,6]]);assert.equal(r.result.decision.widthMm,null);
});
test('Single 7pt success stops before 6pt or double column and records chosen size',()=>{
 const r=run({},p=>p.fontSize===7);assert.deepEqual(r.calls,[[80,8],[80,7]]);assert.equal(r.result.decision.fontSize,7);
});
test('Double-column requires evidence and resets to 8pt before shrinking',()=>{
 const r=run({doubleColumnRationale:'readability',singleColumnRevisionEvidence:'compact redraw still fails'},p=>p.widthMm===160&&p.fontSize===7);
 assert.deepEqual(r.calls,[[80,8],[80,7],[80,6],[160,8],[160,7]]);assert.equal(r.result.decision.widthMm,160);assert.equal(r.result.decision.fontSize,7);
 assert.equal([...r.files.values()].filter(p=>p.figureId==='example').length,5);
});
test('Rebuilt graph follows whole-figure size in every trial',()=>{
 const r=run({route:'rebuild',graph:{fontSize:8}});
 for(const p of r.files.values())if(p.graph)assert.equal(p.graph.fontSize,p.fontSize);
});
